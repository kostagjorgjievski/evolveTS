"""Generate and fully verify the pinned baseline, then pin the trusted receipt."""
import argparse
import json
from pathlib import Path
import evaluator


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=evaluator.ROOT/'outputs/dfthcsos-calibration')
    a=p.parse_args();receipt=a.output/'result.json';seed=evaluator.HERE/'init_program.py'
    if receipt.exists():
        result=json.loads(receipt.read_text())
        if result.get('source_sha256')!=evaluator.digest(seed):raise RuntimeError('Calibration seed mismatch')
        evaluator.score_result(result)
    else:
        if a.output.exists():raise RuntimeError('Calibration directory exists without a completed receipt; wait for it or select a new output')
        result=evaluator.evaluate_program(seed,a.output)
    official=result['official']
    evaluator.PROTOCOL.update(reference_cost=official['score'],reference_cost_source='Full local official verifier calibration',
        reference_program_sha256=evaluator.digest(seed),reference_result_sha256=evaluator.digest(receipt),
        reference_result_path=str(receipt.relative_to(evaluator.ROOT)))
    (evaluator.HERE/'protocol.json').write_text(json.dumps(evaluator.PROTOCOL,indent=2)+'\n')
    print(json.dumps({'status':official['status'],'cost':official['score'],'verified_shots':official['verified_shots'],
                      'reward':1.0,'seconds':result['seconds'],'receipt':str(receipt)},indent=2))


if __name__=='__main__':main()
