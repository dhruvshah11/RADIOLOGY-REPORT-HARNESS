"""Verify the pipeline is bit-identical across processes and hash seeds."""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = """
import os, sys, json, hashlib
sys.path.insert(0, os.path.join(%r, "src"))
import pandas as pd
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_router
train = pd.read_csv(os.path.join(%r, "data", "train.csv"))
test = pd.read_csv(os.path.join(%r, "data", "test.csv"))
cfg = Config(**json.load(open(os.path.join(%r, "artifacts", "best_config.json"))))
gen = ReportGenerator(fit_router(train.to_dict("records")), cfg)
blob = "\\n\\x00\\n".join(gen.generate(r)[0] for r in test.to_dict("records"))
print(hashlib.sha256(blob.encode()).hexdigest())
""" % (ROOT, ROOT, ROOT, ROOT)

digests = []
for seed in ("0", "1", "12345"):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run([sys.executable, "-c", RUN], env=env, capture_output=True, text=True)
    if out.returncode:
        print(out.stderr[-2000:])
        raise SystemExit(1)
    digest = out.stdout.strip()
    print(f"PYTHONHASHSEED={seed:>5}  sha256={digest}")
    digests.append(digest)

if len(set(digests)) == 1:
    print("\nDETERMINISTIC: identical output across hash seeds and processes.")
else:
    print("\nNON-DETERMINISTIC output")
    raise SystemExit(1)
