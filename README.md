# Radiology Reporting Harness — minimal template-editing pipeline

Turn a short, telegraphic radiologist dictation into a complete structured report by
**minimally editing the supplied normal template** — not by writing a new report.

The leaderboard metric (RES, *Radiology Edit Score*, lower is better) rewards template-edit
fidelity. The pipeline here is therefore built as a **precision editor**: it copies the
template, changes only the statements the dictation contradicts, and leaves everything else
byte-identical.

```
                     template_content            dictation
                            │                        │
                            │                        ▼
                            │                 ┌──────────────┐
                            │                 │  SEGMENT     │ sentences, "Bones shows …" cues,
                            │                 │              │ technique/history boilerplate,
                            │                 │              │ trailing dictated summary
                            │                 └──────┬───────┘
                            │                        ▼
                            │                 ┌──────────────┐
                            │                 │  NORMALISE   │ shorthand + corpus spell repair
                            │                 └──────┬───────┘
                            │                        ▼
                            │                 ┌──────────────┐
                            │                 │  SPLIT       │ "No acute fracture or dislocation"
                            │                 │              │  → two routable clauses
                            │                 └──────┬───────┘
                            ▼                        ▼
                     ┌─────────────┐         ┌──────────────┐
                     │  PARSE      │────────▶│  ROUTE       │ cue ▸ field label ▸ curated anatomy
                     │  fields     │         │              │ ▸ template overlap ▸ mined stats
                     └──────┬──────┘         └──────┬───────┘
                            │                       ▼
                            │                ┌──────────────┐
                            └───────────────▶│  EDIT        │ replace only contradicted normals;
                                             │  TEMPLATE    │ untouched fields stay identical
                                             └──────┬───────┘
                                                    ▼
                                             ┌──────────────┐
                                             │  IMPRESSION  │ reuse dictated summary, else
                                             │              │ condense abnormal findings
                                             └──────┬───────┘
                                                    ▼
                                             ┌──────────────┐
                                             │  VALIDATE    │ negation · laterality · measurements
                                             │              │ · no invented content · no omissions
                                             └──────┬───────┘
                                                    ▼
                                              FINDINGS + IMPRESSION
```

## Results (5-fold cross-validation on `train.csv`, 636 rows)

RES is not published, so the pipeline is tuned against a family of edit-based proxies. All are
"lower is better" except the last two.

| system | RES_word | RES_char | RES_raw | FINDINGS | IMPRESSION | field-exact | content recall | content precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| copy the template unchanged | 0.6393 | 0.5740 | 0.5723 | 0.5656 | 0.8910 | 0.401 | 0.533 | 0.817 |
| **structured pipeline** | **0.3908** | **0.3317** | **0.3325** | **0.3612** | **0.6045** | **0.412** | **0.921** | **0.920** |
| *relative improvement* | *-38.9%* | *-42.2%* | *-41.9%* | *-36.1%* | *-32.2%* | *+2.7%* | *+72.8%* | *+12.6%* |

* `RES_word` / `RES_char` — normalised Levenshtein distance to the reference report
  (word- and character-level).
* `FINDINGS` / `IMPRESSION` — the same distance computed per section.
* `field-exact` — fraction of reference fields reproduced verbatim.
* `RES_raw` — the same distance on the raw text, so formatting (blank lines, numbering)
  counts too.
* `content recall / precision` — content-word overlap with the reference.

The pipeline is bit-identical across processes and hash seeds
(`python scripts/check_determinism.py`).

Field routing is evaluated separately against the field each finding occupies in the reference
report: **83.0% accuracy** (5-fold, statistics re-mined per fold).

## Ablation (5-fold CV, one change at a time)

Every design decision below was kept or dropped on measured evidence, not taste.
`-` removes a component from the tuned pipeline; `+` adds an idea that was tried and
**rejected** because it scored worse.

| variant                                        | RES_word | RES_char | RES_raw | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3908 |   0.3317 |  0.3325 |   0.3612 |     0.6045 |   0.921 |
| - coordinated-clause splitting                 |   0.3972 |   0.3367 |  0.3374 |   0.3695 |     0.6057 |   0.923 |
| - abnormal findings first in a field           |   0.3999 |   0.3394 |  0.3403 |   0.3734 |     0.6045 |   0.921 |
| - within-field de-duplication                  |   0.3921 |   0.3330 |  0.3338 |   0.3632 |     0.6045 |   0.922 |
| - shorthand expansion                          |   0.3944 |   0.3344 |  0.3351 |   0.3638 |     0.6113 |   0.917 |
| - corpus spell repair                          |   0.3932 |   0.3331 |  0.3339 |   0.3636 |     0.6077 |   0.921 |
| - cue-mismatch penalty                         |   0.3918 |   0.3327 |  0.3335 |   0.3622 |     0.6045 |   0.921 |
| - trailing paragraph for unroutable findings   |   0.3873 |   0.3292 |  0.3297 |   0.3550 |     0.6045 |   0.912 |
| - dictated-summary reuse (impression)          |   0.4180 |   0.3613 |  0.3619 |   0.3612 |     0.6884 |   0.902 |
| - detail trimming (impression)                 |   0.3967 |   0.3371 |  0.3378 |   0.3612 |     0.6321 |   0.921 |
| - drop negatives from impression               |   0.3959 |   0.3339 |  0.3348 |   0.3612 |     0.6711 |   0.932 |
| - template closing line (impression)           |   0.4055 |   0.3439 |  0.3445 |   0.3612 |     0.6449 |   0.910 |
| - numbered impression                          |   0.3963 |   0.3345 |  0.3358 |   0.3612 |     0.6166 |   0.921 |
| - blank line between fields                    |   0.3908 |   0.3317 |  0.3354 |   0.3612 |     0.6045 |   0.921 |
| + existential framing (rejected)               |   0.3946 |   0.3328 |  0.3336 |   0.3657 |     0.6045 |   0.921 |
| + 'is present' framing (rejected)              |   0.4111 |   0.3462 |  0.3470 |   0.3888 |     0.6045 |   0.921 |
| + soften blanket normals (rejected)            |   0.3954 |   0.3375 |  0.3383 |   0.3678 |     0.6045 |   0.923 |
| + reference-phrasing transfer (rejected)       |   0.3965 |   0.3351 |  0.3359 |   0.3693 |     0.6036 |   0.916 |
| + suppress redundant negatives (rejected)      |   0.3985 |   0.3373 |  0.3381 |   0.3712 |     0.6045 |   0.916 |
| + severity-ranked impression (rejected)        |   0.3916 |   0.3326 |  0.3334 |   0.3612 |     0.6093 |   0.921 |
| + recover summary into findings (rejected)     |   0.4086 |   0.3470 |  0.3478 |   0.3838 |     0.6045 |   0.931 |

Two rows deserve comment.

* **`- trailing paragraph for unroutable findings` scores better (0.3873) than keeping it.**
  Dropping a dictated finding that matches no template field is cheaper for the metric but
  silently loses content, so the pipeline keeps it as a trailing paragraph — which is also
  what the reference reports do. The 0.0035 RES cost buys +0.9 pt of content recall.
* **`+ recover summary into findings` raises content recall to 0.931** but costs 0.018 RES:
  the reference reports do not repeat summary-only lines in FINDINGS either, so the recovery
  is available (`recover_summary`) but off.

## What the pipeline does

1. **Template parsing** (`src/rrh/template.py`) — the template *is* the starting report. Field
   labels and their order are preserved exactly; labels are upper-cased and fields separated by a
   blank line, matching the reference formatting. `OTHER FINDINGS:` is always left empty (56/56
   training reports do). `[left/right]` / `[generic]` placeholders are resolved from
   `study_description` / `body_part`.
2. **Dictation segmentation** (`src/rrh/dictation.py`) — splits telegraphic prose into sentences
   (recovering missing full stops), detects section cues (`Bones shows …`, `L4-L5:`), removes
   technique/history/recommendation boilerplate, and detects the trailing **dictated summary**
   that the reference reports reuse as the impression.
3. **Normalisation** (`src/rrh/lexicon.py`) — a small explicit shorthand table (`degen` →
   `degenerative`, `rt` → `right`) plus spell repair against the corpus vocabulary built from the
   training reports and templates. Only words absent from that vocabulary are ever touched.
4. **Clause splitting** (`src/rrh/splitting.py`) — a dictated sentence is decomposed only when its
   parts genuinely belong to different fields, mirroring the reference behaviour
   (`No acute fracture or dislocation.` → `BONES: No acute fracture.` + `JOINTS: No dislocation.`).
5. **Field routing** (`src/rrh/routing.py`) — five signals, combined: the explicit cue, the field
   label, curated anatomy→field concepts, overlap with the field's own normal statement (weighted
   by rarity within the template), and a k-NN vote over `(sentence → field)` pairs mined from the
   training reports. Findings that match no field of this template become a trailing paragraph, as
   in the references — they are never forced into a wrong field.
6. **Template editing** (`src/rrh/editor.py`) — for a field that received findings, a template
   negative such as `No pleural effusion or pneumothorax.` is *rewritten to keep only the entities
   that are still negative* (`No pneumothorax.`); statements the dictation covers are dropped; all
   other template text is copied verbatim.
7. **Impression** (`src/rrh/impression.py`) — the dictated summary when there is one, otherwise the
   abnormal findings condensed by removal only (copulas and trailing detail clauses stripped),
   closed with the template's normal line **only when that line is itself a negative statement**,
   so a "Normal MRI of the shoulder" line is never printed next to a rotator-cuff tear.
8. **Validation** (`src/rrh/validate.py`) — every generated report is checked for negation flips,
   lost laterality, dropped measurements, invented terms, modified untouched fields, structural
   drift and omitted dictated findings.

## Reproducing the submission

Place the competition CSVs (`train.csv`, `test.csv`, `sample_submission.csv`) in `data/` — they
are not committed here — then:

```bash
pip install -r requirements.txt

python scripts/predict.py            # -> submission.csv (132 rows) + validation report
python scripts/evaluate.py --overrides "$(cat artifacts/best_config.json)"   # 5-fold CV
python scripts/ablation.py           # the ablation table above
python scripts/eval_routing.py       # field-routing accuracy
python scripts/check_determinism.py  # byte-identical output across hash seeds
python -m pytest tests -q            # 24 unit tests
python scripts/build_notebook.py     # regenerate the Kaggle notebook from src/rrh
```

Running `scripts/predict.py` also writes `artifacts/validation_report.txt`. On the 132 test
cases the validator reports **no errors** — no invented terms, no negation flips, no lost
laterality, no dropped measurements, no modified untouched fields, no unresolved placeholders
— and 13 warnings, all of them summary-block restatements that the reference reports omit too.

`submission.csv` is produced entirely by the code in this repository. There is **no per-case manual
editing anywhere**, and no network access or API key is required.

## Kaggle notebook

`notebooks/radiology-reporting-harness.ipynb` is generated from `src/rrh/` by
`scripts/build_notebook.py`, so it can never drift from the code that produced the submission. It
writes each module with `%%writefile`, fits the routing model, prints the cross-validated score
table, and regenerates `submission.csv`.

The notebook contains **no API keys**. An optional hybrid LLM-refinement cell is included at the
end (Approach D in the brief); it reads `ANTHROPIC_API_KEY` from the environment / Kaggle Secrets
and is a no-op when no key is present, so the notebook reproduces the submitted CSV exactly either
way.

### Remaining manual Kaggle steps

1. Upload `notebooks/radiology-reporting-harness.ipynb` and save a version.
2. Share the private notebook with **Natoe AI Dev** (`natoeaidev`).
3. Paste the notebook URL into the **Submission Description** when uploading `submission.csv`.

## Repository layout

```
src/rrh/            pipeline package (stdlib + pandas; rapidfuzz optional accelerator)
scripts/            predict, evaluate, sweep, diagnostics, notebook builder
tests/              unit tests for parsing, editing, routing and the validators
notebooks/          generated Kaggle notebook
artifacts/          tuned configuration, ablation table, sweep + validation logs
data/               train.csv, test.csv, sample_submission.csv (not committed)
```

## Data use

The dataset is de-identified (random `case_id`, five-year age bands, no dates or identifiers) and
is a benchmark. Nothing here is intended for clinical decision-making.
