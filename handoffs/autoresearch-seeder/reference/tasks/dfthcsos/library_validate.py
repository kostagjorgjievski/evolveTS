"""Trusted task validator: ATTEMPT [--smoke|--held-out]."""
import argparse
import json
from pathlib import Path
import uuid
import evaluator

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('attempt',type=Path)
    g=p.add_mutually_exclusive_group()
    g.add_argument('--smoke',action='store_true')
    g.add_argument('--diagnostic',action='store_true')
    g.add_argument('--held-out',action='store_true')
    a=p.parse_args();attempt=a.attempt.resolve()
    name='diagnostic.py' if a.diagnostic else 'program.py'
    source=attempt/'artifact'/name
    if not attempt.name.startswith('attempt_') or source.is_symlink() or not source.is_file() or source.stat().st_nlink!=1:
        p.error('Expected an attempt with artifact/program.py')
    if a.diagnostic:
        from diagnose import diagnose
        print(json.dumps(diagnose(attempt)))
        raise SystemExit(0)
    output=evaluator.ROOT/'outputs/dfthcsos'/uuid.uuid4().hex
    result=evaluator.evaluate_program(attempt/'artifact/program.py',output,
        smoke=a.smoke,salt=evaluator.PROTOCOL['final_salt'] if a.held_out else None)
    if a.held_out:
        result.pop('combined_score',None);result.update(held_out=True,scope='full-local-final')
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
