"""Fit on the full training set and write submission.csv for the test set."""
import os, sys, json, argparse, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_router
from rrh.validate import validate

ROOT = os.path.join(os.path.dirname(__file__), "..")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=os.path.join(ROOT, "artifacts", "best_config.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "submission.csv"))
    args = ap.parse_args()

    train = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    test = pd.read_csv(os.path.join(ROOT, "data", "test.csv"))
    sample = pd.read_csv(os.path.join(ROOT, "data", "sample_submission.csv"))

    cfg_dict = json.load(open(args.cfg)) if os.path.exists(args.cfg) else {}
    cfg = Config(**cfg_dict)
    gen = ReportGenerator(fit_router(train.to_dict("records")), cfg)

    reports, issues, details = {}, {}, []
    for row in test.to_dict("records"):
        report, trace = gen.generate(row)
        reports[row["case_id"]] = report.strip()
        for k, v in validate(row, report, trace, vocab=gen.model.vocab).counts().items():
            issues[k] = issues.get(k, 0) + v
        for i in validate(row, report, trace, vocab=gen.model.vocab).issues:
            details.append((row["case_id"], i.kind, i.detail))

    order = sample["case_id"].tolist()
    assert set(order) == set(reports), "case_id mismatch with sample_submission"
    assert len(order) == len(set(order)) == len(test), "duplicate or missing case_id"

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["case_id", "report"])
        for cid in order:
            w.writerow([cid, reports[cid]])
    print(f"wrote {args.out}: {len(order)} rows")
    print("validation issues:", json.dumps(issues, sort_keys=True) or "{}")
    with open(os.path.join(ROOT, "artifacts", "validation_report.txt"), "w") as fh:
        for cid, kind, detail in details:
            fh.write(f"{cid}\t{kind}\t{detail}\n")
    for cid, kind, detail in details:
        print(f"  {kind:18s} {detail[:110]}")


if __name__ == "__main__":
    main()
