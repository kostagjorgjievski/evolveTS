"""Generate sample handback artifacts offline: a prepared-context document,
a successful seed manifest, and a rejected-manifest record.

Runs the same deterministic fixture flow as the tests; no credentials, no
model sessions, no production effect.
"""
import json
import shutil
import tempfile
from pathlib import Path

from .context import build_prepared_context
from .publisher import publish
from .testing import E2E_SCRIPT, build_job


def generate_samples(output: Path) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='seeder-samples-') as temporary:
        # 1) Prepared context after a failed first diagnostic (mid-research).
        job = build_job(Path(temporary) / 'mid', E2E_SCRIPT)
        job.run(max_sessions=1)
        context = build_prepared_context(job.job_state(), job.store, job.adapter,
                                        job.config, job_dir=job.job_dir)
        (output / 'prepared-context.md').write_text(context)

        # 2) Successful seed manifest from the full flow.
        success = build_job(Path(temporary) / 'success', E2E_SCRIPT)
        success.run()
        outcome = publish(success, export=True)
        assert outcome['accepted'], outcome['reasons']
        seed_dir = Path(outcome['export'])
        shutil.copyfile(seed_dir / 'MANIFEST.json',
                        output / 'seed-manifest-success.json')
        shutil.copyfile(seed_dir / 'SEAL.json', output / 'seed-seal-success.json')
        shutil.copyfile(seed_dir / 'LICENSE-STATUS.md',
                        output / 'seed-license-status.md')

        # 3) Rejected record: development PASS but independent confirmation FAIL.
        rejected = build_job(Path(temporary) / 'rejected', E2E_SCRIPT)
        rejected.run()
        experiment = rejected.store.list_experiments('confirmation_validation')[0]
        experiment['status'] = 'fail'
        experiment['receipt'] = {'status': 'FAIL',
                                 'error': 'independent confirmation check failed'}
        rejected.store.record_experiment(experiment)
        refusal = publish(rejected, export=True)
        assert not refusal['accepted']
        shutil.copyfile(refusal['rejection'], output / 'seed-manifest-rejected.json')

    print(json.dumps({'samples': sorted(p.name for p in output.iterdir()),
                      'production_enabled': False}, indent=2))
