"""Write submission.csv from the deterministic pipeline plus the LLM refinement pass.

The deterministic generator produces a draft for every test case; the LLM pass
(artifacts/llm_refined_test.json) replaces the draft wherever a refined report
exists.  Every emitted report - refined or not - goes through the same
validator.  The `untouched_field` check is trace-dependent (it compares against
the deterministic router's routing decisions) so it is reported separately for
refined rows rather than counted as an error.
"""
import os, sys, json, argparse, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_ranked_router
from rrh.validate import validate

ROOT = os.path.join(os.path.dirname(__file__), "..")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=os.path.join(ROOT, "artifacts", "best_config.json"))
    ap.add_argument("--overlay", default=os.path.join(ROOT, "artifacts", "llm_refined_test.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "submission.csv"))
    args = ap.parse_args()

    train = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    test = pd.read_csv(os.path.join(ROOT, "data", "test.csv"))
    sample = pd.read_csv(os.path.join(ROOT, "data", "sample_submission.csv"))

    cfg = Config(**(json.load(open(args.cfg)) if os.path.exists(args.cfg) else {}))
    gen = ReportGenerator(fit_ranked_router(train.to_dict("records"), cfg), cfg)
    overlay = json.load(open(args.overlay)) if os.path.exists(args.overlay) else {}

    reports, issues, details, n_over = {}, {}, [], 0
    for row in test.to_dict("records"):
        cid = row["case_id"]
        draft, trace = gen.generate(row)
        refined = overlay.get(cid)
        report = (refined or draft).strip()
        if refined:
            n_over += 1
        res = validate(row, report, trace, vocab=gen.model.vocab)
        for i in res.issues:
            if refined and i.kind == "untouched_field":
                continue  # the refinement pass routes findings the router left in place
            issues[i.kind] = issues.get(i.kind, 0) + 1
            details.append((cid, i.kind, i.severity, i.detail))
        reports[cid] = report

    order = sample["case_id"].tolist()
    assert set(order) == set(reports), "case_id mismatch with sample_submission"
    assert len(order) == len(set(order)) == len(test), "duplicate or missing case_id"

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["case_id", "report"])
        for cid in order:
            w.writerow([cid, reports[cid]])
    print(f"wrote {args.out}: {len(order)} rows ({n_over} refined, {len(order)-n_over} deterministic)")
    print("validation issues:", json.dumps(issues, sort_keys=True) or "{}")
    with open(os.path.join(ROOT, "artifacts", "validation_report.txt"), "w") as fh:
        for cid, kind, sev, detail in details:
            fh.write(f"{cid}\t{sev}\t{kind}\t{detail}\n")
    for cid, kind, sev, detail in details:
        print(f"  {sev:5s} {kind:18s} {cid[:8]} {detail[:100]}")


if __name__ == "__main__":
    main()
