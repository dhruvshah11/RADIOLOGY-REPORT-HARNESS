# Radiology Reporting Harness — minimal template-editing pipeline

Turn a short, telegraphic radiologist dictation into a complete structured report by
**minimally editing the supplied normal template** — not by writing a new report.

The leaderboard metric (RES, *Radiology Edit Score*, lower is better) rewards template-edit
fidelity. The pipeline here is therefore built as a **precision editor**: it copies the
template, changes only the statements the dictation contradicts, and leaves everything else
byte-identical.

It runs in two stages. **Stage 1** is a fully deterministic editor (no network, no keys) that
reaches RES_word 0.3742 on 5-fold cross-validation. **Stage 2** hands that draft, the template
and the dictation to a language model under one fixed instruction set, which corrects
mis-routed clauses, dictation typos and impression ordering without adding content; on
held-out training cases it cuts RES_word a further **41%**, to 0.2318.

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
| **stage 1 — structured pipeline** | **0.3742** | **0.3184** | **0.3193** | **0.5423** | **0.3506** | **0.5574** | **0.931** |
| *relative improvement* | *-41.5%* | *-44.5%* | *-44.2%* | *-20.3%* | *-38.0%* | *-37.4%* | *+74.7%* |

### Stage 2 — LLM refinement (24 held-out training cases)

The refinement stage was validated on a held-out sample before being run on the test set. The
work packet given to the model contained the `case_id`, study description, template, dictation
and the deterministic draft — **the reference reports were withheld**, so the comparison below
is honest rather than a fit to the answers.

| system | RES_word | RES_char | RES_sent | FINDINGS | IMPRESSION | field-exact | content prec. |
|---|---:|---:|---:|---:|---:|---:|---:|
| stage 1 only | 0.3937 | 0.3354 | 0.6156 | 0.3729 | 0.5324 | 0.3325 | 0.911 |
| **stage 1 + LLM refinement** | **0.2318** | **0.1973** | **0.4386** | **0.2097** | **0.3472** | **0.4583** | **0.959** |
| *relative improvement* | *-41.1%* | *-41.2%* | *-28.8%* | *-43.8%* | *-34.8%* | *+37.8%* | *+5.3%* |

Better on **21 of the 24** cases. Reproduce with `python scripts/llm_score.py`.

The gains come from four recurring failure modes of the deterministic router, all of which the
instruction set names explicitly: a clause filed under the wrong label (a PCL finding under
`ANTERIOR CRUCIATE LIGAMENT`), a section header leaking in from the dictation's own layout
(`Findings`, `Brain Parenchyma`), a template normal left standing next to the finding that
contradicts it (`Lungs are clear.` beside bibasilar opacities), and an impression built from
the wrong sentences. It also repairs dictation typos the corpus spell-checker got wrong
(`os peritoneum` → `os peroneum`, `salivary kidney` → `solitary kidney`).

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
report: **85.8% accuracy** (5-fold, statistics re-mined per fold).

## Ablation (5-fold CV, one change at a time)

Every design decision below was kept or dropped on measured evidence, not taste.
`-` removes a component from the tuned pipeline; `+` adds an idea that was tried and
**rejected** because it scored worse. Fourteen ideas were measured and rejected, including
three that were better on their own sub-task but worse on the report.

| variant                                        | RES_word | RES_char | RES_raw | RES_sent | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.6805 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| - coordinated-clause splitting                 |   0.3793 |   0.3224 |  0.3232 |   0.5476 |   0.3574 |     0.5575 |   0.932 |
| - sequence continuity in routing               |   0.3780 |   0.3216 |  0.3224 |   0.5442 |   0.3559 |     0.5574 |   0.930 |
| - abnormal findings first in a field           |   0.3841 |   0.3267 |  0.3276 |   0.5496 |   0.3639 |     0.5574 |   0.931 |
| - within-field de-duplication                  |   0.3753 |   0.3197 |  0.3205 |   0.5453 |   0.3523 |     0.5574 |   0.932 |
| - shorthand expansion                          |   0.3809 |   0.3250 |  0.3258 |   0.5531 |   0.3531 |     0.5768 |   0.927 |
| - corpus spell repair                          |   0.3765 |   0.3200 |  0.3208 |   0.5411 |   0.3532 |     0.5592 |   0.931 |
| - cue-mismatch penalty                         |   0.3755 |   0.3197 |  0.3205 |   0.5429 |   0.3523 |     0.5574 |   0.931 |
| - trailing paragraph for unroutable findings (drops content) |   0.3715 |   0.3166 |  0.3171 |   0.5337 |   0.3461 |     0.5574 |   0.923 |
| - dictated-summary reuse (impression)          |   0.4140 |   0.3595 |  0.3600 |   0.5698 |   0.3506 |     0.6789 |   0.904 |
| - detail trimming (impression)                 |   0.3805 |   0.3245 |  0.3254 |   0.5425 |   0.3506 |     0.5881 |   0.931 |
| + drop negatives from impression (rejected)    |   0.3798 |   0.3247 |  0.3255 |   0.5399 |   0.3506 |     0.5634 |   0.922 |
| - template closing line (impression)           |   0.3868 |   0.3286 |  0.3294 |   0.5730 |   0.3506 |     0.5955 |   0.922 |
| - numbered impression                          |   0.3784 |   0.3208 |  0.3221 |   0.5786 |   0.3506 |     0.5664 |   0.931 |
| - blank line between fields                    |   0.3742 |   0.3184 |  0.3221 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| + existential framing (rejected)               |   0.3780 |   0.3196 |  0.3205 |   0.5433 |   0.3552 |     0.5574 |   0.931 |
| + 'is present' framing (rejected)              |   0.3941 |   0.3329 |  0.3337 |   0.5550 |   0.3774 |     0.5574 |   0.931 |
| + soften blanket normals (rejected)            |   0.3787 |   0.3240 |  0.3248 |   0.5440 |   0.3570 |     0.5574 |   0.933 |
| + reference-phrasing transfer (rejected)       |   0.3806 |   0.3225 |  0.3233 |   0.5506 |   0.3594 |     0.5574 |   0.927 |
| + suppress redundant negatives (rejected)      |   0.3821 |   0.3241 |  0.3250 |   0.5516 |   0.3608 |     0.5574 |   0.926 |
| + severity-ranked impression (rejected)        |   0.3751 |   0.3192 |  0.3200 |   0.5422 |   0.3506 |     0.5622 |   0.931 |
| + recover summary into findings (rejected)     |   0.3888 |   0.3317 |  0.3325 |   0.5560 |   0.3676 |     0.5574 |   0.932 |
| + learned conditional-logit router (rejected)  |   0.3815 |   0.3250 |  0.3257 |   0.5516 |   0.3601 |     0.5575 |   0.931 |
| + template field-edit prior (rejected)         |   0.3803 |   0.3233 |  0.3241 |   0.5447 |   0.3588 |     0.5578 |   0.931 |
| + Viterbi sequence decoding (no change)        |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| + summary starts after last cue (rejected)     |   0.3861 |   0.3279 |  0.3287 |   0.5584 |   0.3581 |     0.6127 |   0.927 |
| + merge unrouted findings into one para        |   0.3742 |   0.3184 |  0.3192 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| - abnormality gate on the impression           |   0.3830 |   0.3244 |  0.3253 |   0.5612 |   0.3506 |     0.6433 |   0.930 |
| - stricter mining threshold                    |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + body-region-conditioned statistics (rejected) |   0.3765 |   0.3201 |  0.3209 |   0.5423 |   0.3536 |     0.5572 |   0.931 |
| + bigram routing features (rejected)           |   0.3757 |   0.3195 |  0.3204 |   0.5435 |   0.3529 |     0.5578 |   0.931 |
| + conjunction splitting (rejected)             |   0.3750 |   0.3189 |  0.3198 |   0.5435 |   0.3516 |     0.5574 |   0.931 |
| + trim detail in dictated summary (rejected)   |   0.3840 |   0.3279 |  0.3288 |   0.5493 |   0.3506 |     0.5847 |   0.926 |
| + cost-sensitive impression chooser (no change) |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |

Rows that deserve comment:

* **`- trailing paragraph for unroutable findings` scores better (0.3715) than keeping it.**
  Dropping a dictated finding that matches no template field is cheaper for the metric but
  silently loses content. Checking what the reference actually does with those clauses
  settled it: of 181 such clauses, the reference keeps **126** as a trailing paragraph and
  25 in a labelled field, and drops only 30 — nearly all of which were history/technique
  boilerplate the filter was missing. So the fix was to tighten the boilerplate filter (worth
  0.004 RES on its own), not to throw findings away. The remaining gap is the price of not
  dropping content, and it buys +0.8 pt of content recall.
* **`+ learned conditional-logit router` is *more accurate* on the mined labels yet scores
  worse.** The labels are noisy — the reference itself is inconsistent about where, say,
  "Alignment is anatomic" belongs — and the learned router stopped abstaining, forcing
  findings into fields where no field fits. Label accuracy is not the objective; RES is.
* **`+ cost-sensitive impression chooser` changes nothing.** A depth-2 decision rule fitted
  directly on whole-report edit cost reproduces the existing rule exactly, which is evidence
  the rule is already optimal over these three strategies. (Fitted on *impression-only* cost
  it looked better on that component and was worse on the report — per-section means
  over-weight cases whose reference impression is a single short line.)
* **`+ body-region-conditioned statistics` does not help**, even though "effusion" means
  PLEURA in a chest study and JOINT in a knee study. Restricting candidates to the template's
  own fields already performs that disambiguation.
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
10. **LLM refinement** (stage 2, `scripts/llm_sample.py` → `scripts/apply_overlay.py`) — the
    draft, the template and the dictation go to a language model under one fixed instruction
    set: keep every label and its order, leave unmentioned fields verbatim, move mis-routed
    clauses to the right field, drop technique/history/recommendation boilerplate and leaked
    section headers, repair typos into standard radiology terms, rebuild the impression
    (dictated summary first, abnormal items before the closing negative), and never introduce a
    finding, measurement or laterality the dictation does not support. Its output is re-checked
    by the same validator before it reaches the CSV.

## Reproducing the submission

Place the competition CSVs (`train.csv`, `test.csv`, `sample_submission.csv`) in `data/` — they
are not committed here — then:

```bash
pip install -r requirements.txt

python scripts/predict.py            # stage 1 only -> submission.csv + validation report
python scripts/apply_overlay.py      # stage 1 + stage 2 -> the submitted submission.csv
python scripts/llm_sample.py --split test --out artifacts/llm_packet_test.json   # stage-2 work packet
python scripts/llm_score.py          # stage-2 validation on held-out train cases
python scripts/evaluate.py --overrides "$(cat artifacts/best_config.json)"   # 5-fold CV
python scripts/ablation.py           # the ablation table above
python scripts/tune.py --rounds 2    # coordinate descent over the configuration
python scripts/oracle.py             # headroom analysis (perfect routing / impression)
python scripts/eval_routing.py       # field-routing accuracy
python scripts/check_determinism.py  # byte-identical output across hash seeds
python -m pytest tests -q            # 24 unit tests
python scripts/build_notebook.py     # regenerate the Kaggle notebook from src/rrh
```

Both scripts write `artifacts/validation_report.txt`. On the 132 submitted reports the
validator reports **no structural errors**: every template label sequence is reproduced
exactly, no placeholder is left unresolved, no measurement is dropped, no negation is flipped
and no laterality is lost. The remaining flags are the `unsupported_term` heuristic firing on
the typo and shorthand repairs the task asks for (`degen chnges` → `Degenerative changes`,
`s/o` → `suggestive of`, `VR spaces` → `Virchow-Robin spaces`) — every one was triaged by
hand against its dictation — plus omission warnings on technique, history and recommendation
boilerplate that the reference reports drop too.

**Where the remaining headroom is.** `scripts/oracle.py` measures it: perfect field routing
would reach RES_word 0.3398 (0.034 away) and an oracle per-case choice of impression strategy
would reach 0.4613 on that component. Neither is reachable with the signals available — six
distinct attempts at each are in the ablation above.

`submission.csv` is produced by the code in this repository plus one instruction set applied
uniformly to all 132 cases. There is **no per-case manual editing anywhere** — no case is given
its own rule, and the stage-2 outputs are cached (`artifacts/llm_refined_test.json`) so the CSV
regenerates offline with no network access and no API key.

## Kaggle notebook

`notebooks/radiology-reporting-harness.ipynb` is generated from `src/rrh/` by
`scripts/build_notebook.py`, so it can never drift from the code that produced the submission. It
writes each module with `%%writefile`, fits the routing model, prints the cross-validated score
table, runs stage 1, runs stage 2, and regenerates `submission.csv`.

Running the notebook top to bottom reproduces the submitted `submission.csv`
**byte-for-byte** (verified by SHA-256 against the file in this repository).

The notebook contains **no API keys**. Stage 2 reads `ANTHROPIC_API_KEY` from the environment /
Kaggle Secrets and runs live only when `RRH_RUN_LLM=1`; with no key it reads the cached
refinement outputs written by Section 6.2, so the notebook is self-contained and offline. Its
Section 6.1 shows the full instruction set and the exact API call, so the stage is auditable and
re-runnable.

### Remaining manual Kaggle steps

1. Upload `notebooks/radiology-reporting-harness.ipynb` and save a version.
2. Share the private notebook with **Natoe AI Dev** (`natoeaidev`).
3. Paste the notebook URL into the **Submission Description** when uploading `submission.csv`.

## Repository layout

```
src/rrh/            pipeline package (stdlib + pandas; rapidfuzz optional accelerator)
scripts/            predict, LLM refinement pass, evaluate, sweep, diagnostics, notebook builder
tests/              unit tests for parsing, editing, routing and the validators
notebooks/          generated Kaggle notebook
artifacts/          tuned config, ablation table, sweep/validation logs, stage-2 refinements
data/               train.csv, test.csv, sample_submission.csv (not committed)
```

## Data use

The dataset is de-identified (random `case_id`, five-year age bands, no dates or identifiers) and
is a benchmark. Nothing here is intended for clinical decision-making.
