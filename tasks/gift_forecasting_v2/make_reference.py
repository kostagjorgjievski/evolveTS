"""Score the seasonal-naive seed on the development windows; the objective is relative to it.

Run once after any development-protocol change, inside a GPU slot like any evaluation:
  .gift-venv/bin/python tasks/gift_forecasting_v2/make_reference.py
"""
import hashlib
import json

from evaluator import HERE, PROTOCOL, gpu_turn, run

program = HERE / "init_program.py"
with gpu_turn():
    result = run(program, "validation", score=False)
reference = {"program": "init_program.py", "program_sha256": hashlib.sha256(program.read_bytes()).hexdigest(),
             "data_revision": PROTOCOL["data_revision"], "development": PROTOCOL["development"],
             "rows": result["rows"], "details": result["details"], "seconds": result["seconds"]}
(HERE / PROTOCOL["reference_file"]).write_text(json.dumps(reference, indent=2) + "\n")
print(json.dumps({"configurations": len(result["rows"]), "seconds": round(result["seconds"])}))
