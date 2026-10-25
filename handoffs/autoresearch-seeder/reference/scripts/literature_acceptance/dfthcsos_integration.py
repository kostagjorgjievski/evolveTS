"""Longer component diagnostics; never an official score."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tasks/dfthcsos'))
from diagnose import diagnose
if __name__=='__main__':
    attempt=Path(sys.argv[1]).resolve()
    if not attempt.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('DFTHC-SOS attempt required')
    print(json.dumps(diagnose(attempt,timeout=600,memory_gib=8)))
