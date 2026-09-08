"""Scripted stage 2: refine reports with an LLM, few-shot on same-template examples.

    export ANTHROPIC_API_KEY=...
    python scripts/refine_llm.py --split train --limit 120 --out artifacts/r_v1.json
    python scripts/prompt_ab.py artifacts/r_v1.json          # measure, SE ~ 0.014 at n=120
    ...edit PROMPTS, re-run, keep what measurably wins...
    python scripts/refine_llm.py --split test --out artifacts/llm_refined_test.json

Runs concurrently, is resumable (existing keys in --out are skipped), and works
without a key via --mock so the plumbing can be tested first.
"""
import os, sys, json, time, argparse, random, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.fewshot import FewShotIndex
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_ranked_router
from rrh.textutil import levenshtein

ROOT = os.path.join(os.path.dirname(__file__), "..")

# ---------------------------------------------------------------- prompts
PROMPTS = {}

PROMPTS["v1"] = """You are a precision report editor. You are given a normal template, a
radiologist's telegraphic dictation, a deterministic draft built by editing that template, and
worked examples of how THIS SAME TEMPLATE was turned into a finished report. Return the
corrected report and nothing else.

Match the phrasing, length and level of detail of the worked examples - they are the house
style and are the most important guide you have.

Rules, each measured against 636 reference reports:
1.  Keep the template's field labels, uppercased, in the template's order, one blank line
    between fields. Never add, drop, rename or reorder a label.
2.  A field the dictation does not mention keeps the template text verbatim (references keep
    92% of those).
3.  Route each dictated finding to the field it belongs to; move anything the draft misfiled.
4.  Replace or trim only the normal statement the dictation contradicts. In a field it edits,
    the reference still keeps 57% of the template's sentences - delete only on a real
    contradiction. If a negated list loses one member ("No A or B", A now positive), write "No B".
5.  Never write a field shorter than both the template's and the dictation's wording; where they
    conflict prefer the dictation's (it wins 6:1). Do not compress "Intact and normal in course
    and signal intensity." to "Intact."
6.  Drop technique, clinical history, contrast dose and recommendation boilerplate, and section
    headers leaked from the dictation's layout ("Findings", "Kidneys", "Brain Parenchyma").
    Keep statements about study limitations (references keep 85%).
7.  Repair dictation typos and expand shorthand into standard radiology terms ("degen chnges"
    -> "Degenerative changes", "s/o" -> "suggestive of"). Never repair into a different entity.
8.  Within a field the abnormal statement comes first (85%).
9.  IMPRESSION: if the dictation has its own summary, reuse it in its order and near-verbatim
    (references run 1.07x its length). Otherwise condense the abnormal findings, about 6 words
    an item. The closing negative goes LAST (325 references against 34). Number the items when
    there is more than one and leave a single item unnumbered.
10. Preserve negation, laterality and every measurement exactly. Never introduce a finding,
    diagnosis, measurement or laterality the dictation does not support.
11. Output only FINDINGS: ... IMPRESSION: ... - nothing else."""

# Add variants here and A/B them; v2 is a placeholder to be edited.
PROMPTS["v2"] = PROMPTS["v1"]


def user_message(row, draft, examples):
    parts = []
    for i, e in enumerate(examples, 1):
        parts.append(f"### WORKED EXAMPLE {i} (same template) - study: {e.study}\n"
                     f"DICTATION:\n{e.dictation}\n\nFINISHED REPORT:\n{e.report}\n")
    parts.append(f"### NOW DO THIS ONE\nSTUDY: {row.get('modality')} {row.get('body_part')} - "
                 f"{row.get('study_description')}\n\nTEMPLATE:\n{row['template_content']}\n\n"
                 f"DICTATION:\n{row['dictation']}\n\nDRAFT:\n{draft}")
    return "\n".join(parts)


def medoid(cands):
    """The most central candidate - variance reduction without needing a reference."""
    if len(cands) == 1:
        return cands[0]
    best, bs = cands[0], None
    for a in cands:
        tot = sum(levenshtein(a.split(), b.split()) for b in cands if b is not a)
        if bs is None or tot < bs:
            bs, best = tot, a
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", default="v1", choices=sorted(PROMPTS))
    ap.add_argument("--shots", type=int, default=4)
    ap.add_argument("--n-best", type=int, default=1, help=">1 samples n times and keeps the medoid")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--mock", action="store_true", help="no API call; echoes the draft")
    a = ap.parse_args()

    train = pd.read_csv(os.path.join(ROOT, "data", "train.csv")).to_dict("records")
    rows = train if a.split == "train" else pd.read_csv(
        os.path.join(ROOT, "data", f"{a.split}.csv")).to_dict("records")
    if a.limit:
        rows = rows[:a.limit]

    cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
    gen = ReportGenerator(fit_ranked_router(train, cfg), cfg)
    index = FewShotIndex(train)
    print(f"few-shot coverage: {index.coverage(rows)}")

    out_path = a.out
    done = json.load(open(out_path)) if os.path.exists(out_path) else {}
    todo = [r for r in rows if str(r["case_id"]) not in done]
    print(f"{len(done)} already refined, {len(todo)} to do, prompt={a.prompt}, "
          f"shots={a.shots}, n_best={a.n_best}, mock={a.mock}")

    client = None
    if not a.mock:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY is not set (use --mock to test the plumbing)")
        import anthropic
        client = anthropic.Anthropic(api_key=key)

    lock = threading.Lock()
    system = PROMPTS[a.prompt]
    errors = []

    def work(row):
        cid = str(row["case_id"])
        draft, _ = gen.generate(row)
        ex = index.examples(row, k=a.shots, exclude_case=cid)   # never leak its own reference
        msg = user_message(row, draft.strip(), ex)
        if a.mock:
            return cid, draft.strip()
        cands = []
        for i in range(a.n_best):
            for attempt in range(4):
                try:
                    r = client.messages.create(
                        model=a.model, max_tokens=a.max_tokens,
                        temperature=0.0 if a.n_best == 1 else 1.0,
                        system=system, messages=[{"role": "user", "content": msg}])
                    cands.append(r.content[0].text.strip())
                    break
                except Exception as e:                      # rate limit / transient
                    if attempt == 3:
                        with lock:
                            errors.append((cid, repr(e)[:120]))
                        break
                    time.sleep(2 ** attempt + random.random())
        return (cid, medoid(cands)) if cands else (cid, None)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(work, r): r for r in todo}
        for n, f in enumerate(as_completed(futs), 1):
            cid, text = f.result()
            if text:
                with lock:
                    done[cid] = text
            if n % 20 == 0 or n == len(todo):
                with lock:
                    json.dump(done, open(out_path, "w"), indent=1)
                print(f"  {n}/{len(todo)}  {time.time()-t0:.0f}s  refined={len(done)}")
    json.dump(done, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}: {len(done)} reports")
    if errors:
        print(f"{len(errors)} cases failed:")
        for cid, e in errors[:10]:
            print("   ", cid[:8], e)


if __name__ == "__main__":
    main()
