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

| system | RES_word | RES_char | RES_raw | RES_sent | FINDINGS | IMPRESSION | content recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| copy the template unchanged | 0.6393 | 0.5740 | 0.5723 | 0.6805 | 0.5656 | 0.8910 | 0.533 |
| **structured pipeline** | **0.3748** | **0.3185** | **0.3193** | **0.5439** | **0.3514** | **0.5573** | **0.931** |
| *relative improvement* | *-41.4%* | *-44.5%* | *-44.2%* | *-20.1%* | *-37.9%* | *-37.5%* | *+74.7%* |

* `RES_word` / `RES_char` — normalised Levenshtein distance to the reference report
  (word- and character-level).
* `FINDINGS` / `IMPRESSION` — the same distance computed per section.
* `field-exact` — fraction of reference fields reproduced verbatim.
* `RES_raw` — the same distance on the raw text, so formatting (blank lines, numbering)
  counts too.
* `RES_sent` — edit distance counted in whole *sentences*, the unit a radiologist actually
  edits, and the closest analogue to an "edit score".
* `content recall / precision` — content-word overlap with the reference.

The pipeline is bit-identical across processes and hash seeds
(`python scripts/check_determinism.py`).

Field routing is evaluated separately against the field each finding occupies in the reference
report: **84.9% accuracy** (5-fold, statistics re-mined per fold).

## Ablation (5-fold CV, one change at a time)

Every design decision below was kept or dropped on measured evidence, not taste.
`-` removes a component from the tuned pipeline; `+` adds an idea that was tried and
**rejected** because it scored worse. Nine ideas were measured and rejected, including two
that were *more* accurate on their own sub-task.

| variant                                        | RES_word | RES_char | RES_raw | RES_sent | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.6805 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| - coordinated-clause splitting                 |   0.3804 |   0.3225 |  0.3234 |   0.5471 |   0.3589 |     0.5575 |   0.933 |
| - sequence continuity in routing               |   0.3780 |   0.3214 |  0.3223 |   0.5445 |   0.3559 |     0.5573 |   0.931 |
| - abnormal findings first in a field           |   0.3844 |   0.3268 |  0.3277 |   0.5506 |   0.3644 |     0.5573 |   0.931 |
| - within-field de-duplication                  |   0.3757 |   0.3197 |  0.3205 |   0.5469 |   0.3529 |     0.5573 |   0.932 |
| - shorthand expansion                          |   0.3817 |   0.3252 |  0.3260 |   0.5550 |   0.3540 |     0.5768 |   0.927 |
| - corpus spell repair                          |   0.3774 |   0.3203 |  0.3212 |   0.5424 |   0.3543 |     0.5592 |   0.931 |
| - cue-mismatch penalty                         |   0.3761 |   0.3198 |  0.3206 |   0.5445 |   0.3531 |     0.5573 |   0.931 |
| - trailing paragraph for unroutable findings (drops content) |   0.3722 |   0.3168 |  0.3173 |   0.5353 |   0.3470 |     0.5573 |   0.923 |
| - dictated-summary reuse (impression)          |   0.4146 |   0.3597 |  0.3602 |   0.5713 |   0.3514 |     0.6787 |   0.905 |
| - detail trimming (impression)                 |   0.3811 |   0.3246 |  0.3254 |   0.5441 |   0.3514 |     0.5880 |   0.931 |
| + drop negatives from impression (rejected)    |   0.3803 |   0.3248 |  0.3255 |   0.5415 |   0.3514 |     0.5633 |   0.922 |
| - template closing line (impression)           |   0.3874 |   0.3287 |  0.3295 |   0.5742 |   0.3514 |     0.5957 |   0.922 |
| - numbered impression                          |   0.3790 |   0.3208 |  0.3221 |   0.5799 |   0.3514 |     0.5664 |   0.931 |
| - blank line between fields                    |   0.3748 |   0.3185 |  0.3222 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + existential framing (rejected)               |   0.3783 |   0.3195 |  0.3204 |   0.5448 |   0.3556 |     0.5573 |   0.931 |
| + 'is present' framing (rejected)              |   0.3947 |   0.3330 |  0.3338 |   0.5566 |   0.3783 |     0.5573 |   0.931 |
| + soften blanket normals (rejected)            |   0.3794 |   0.3242 |  0.3250 |   0.5457 |   0.3580 |     0.5573 |   0.933 |
| + reference-phrasing transfer (rejected)       |   0.3804 |   0.3219 |  0.3227 |   0.5525 |   0.3592 |     0.5569 |   0.927 |
| + suppress redundant negatives (rejected)      |   0.3823 |   0.3241 |  0.3250 |   0.5526 |   0.3612 |     0.5573 |   0.926 |
| + severity-ranked impression (rejected)        |   0.3757 |   0.3192 |  0.3201 |   0.5437 |   0.3514 |     0.5621 |   0.931 |
| + recover summary into findings (rejected)     |   0.3894 |   0.3318 |  0.3326 |   0.5575 |   0.3685 |     0.5573 |   0.933 |
| + learned conditional-logit router (rejected)  |   0.3818 |   0.3251 |  0.3258 |   0.5527 |   0.3608 |     0.5574 |   0.931 |
| + template field-edit prior (rejected)         |   0.3811 |   0.3236 |  0.3244 |   0.5463 |   0.3599 |     0.5578 |   0.931 |
| + Viterbi sequence decoding (no change)        |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + summary starts after last cue (rejected)     |   0.3866 |   0.3279 |  0.3288 |   0.5597 |   0.3588 |     0.6126 |   0.927 |
| + merge unrouted findings into one para        |   0.3748 |   0.3185 |  0.3192 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| - abnormality gate on the impression           |   0.3836 |   0.3246 |  0.3254 |   0.5628 |   0.3514 |     0.6437 |   0.931 |

Rows that deserve comment:

* **`- trailing paragraph for unroutable findings` scores better (0.3722) than keeping it.**
  Dropping a dictated finding that matches no template field is cheaper for the metric but
  silently loses content. Checking what the reference actually does with those clauses
  settled it: of 181 such clauses, the reference keeps **126** as a trailing paragraph and
  25 in a labelled field, and drops only 30 — nearly all of which were history/technique
  boilerplate my filter was missing. So the fix was to tighten the boilerplate filter (worth
  0.004 RES on its own), not to throw findings away. The remaining 0.0026 gap is the price of
  not dropping content, and it buys +0.8 pt of content recall.
* **`+ learned conditional-logit router` is *more accurate* (84.9% vs 84.2% at the time) yet
  scores worse.** The mined gold labels are noisy — the reference itself is inconsistent about
  where, say, "Alignment is anatomic" belongs — and the learned router stopped abstaining, so
  it forced findings into fields where no field fits. Label accuracy is not the objective; RES is.
* **`+ Viterbi sequence decoding` changes nothing.** The order-preserving transition model is
  real (85% of consecutive findings never move backwards), but greedy decoding already finds
  the same path, so the simpler code stays.

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
8. **De-duplication** — a dictated per-level summary that restates a clause already in the
   field is dropped, except when it carries a measurement the field does not have yet.
9. **Validation** (`src/rrh/validate.py`) — every generated report is checked for negation flips,
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
python scripts/tune.py --rounds 2    # coordinate descent over the configuration
python scripts/oracle.py             # headroom analysis (perfect routing / impression)
python scripts/eval_routing.py       # field-routing accuracy
python scripts/check_determinism.py  # byte-identical output across hash seeds
python -m pytest tests -q            # 24 unit tests
python scripts/build_notebook.py     # regenerate the Kaggle notebook from src/rrh
```

Running `scripts/predict.py` also writes `artifacts/validation_report.txt`. On the 132 test
cases the validator reports **no errors** — no invented terms, no negation flips, no lost
laterality, no dropped measurements, no modified untouched fields, no unresolved placeholders
— and 4 warnings, all of them summary-block restatements that the reference reports omit too.

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
