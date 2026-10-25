"""Trusted fixture validator: ATTEMPT [--smoke|--diagnostic|--held-out]."""
import argparse
import json
import sys
import uuid
from pathlib import Path

import evaluator

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt', type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--smoke', action='store_true')
    group.add_argument('--diagnostic', action='store_true')
    group.add_argument('--held-out', action='store_true')
    args = parser.parse_args()
    attempt = args.attempt.resolve()
    name = 'diagnostic.py' if args.diagnostic else 'program.py'
    source = attempt / 'artifact' / name
    if not attempt.name.startswith('attempt_') or source.is_symlink() \
            or not source.is_file() or source.stat().st_nlink != 1:
        parser.error('Expected an attempt with artifact/' + name)
    if args.diagnostic:
        from diagnose import diagnose
        print(json.dumps(diagnose(attempt)))
        raise SystemExit(0)
    output = evaluator.ROOT / 'outputs' / f'seed-demo-{uuid.uuid4().hex}'
    result = evaluator.evaluate_program(attempt / 'artifact/program.py', output,
                                        smoke=args.smoke,
                                        salt=evaluator.PROTOCOL['final_salt']
                                        if args.held_out else None)
    if args.held_out:
        result.pop('combined_score', None)
        result.update(held_out=True, scope='full-local-final')
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
