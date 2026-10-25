"""Export sealing: relative-path seals keep duplicate basenames, verification
catches tampering, and interrupted publications are completed, not trusted."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.publisher import publish, seal_export, \
    verify_export
from scripts.autoresearch_seeder.testing import E2E_SCRIPT, build_job


def _completed_job(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    controller.run()
    assert controller.job_state()['stage'] == 'seed_ready'
    return controller


def test_seal_keys_are_relative_and_keep_duplicate_basenames(tmp_path):
    directory = tmp_path / 'seed'
    for relative in ('submission/development/submission.npz',
                     'submission/confirmation/submission.npz',
                     'receipts/development.json'):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    (directory / 'MANIFEST.json').write_text('{}')
    seal = seal_export(directory)
    keys = set(seal['files'])
    # Regression: a basename-keyed seal collapsed these to one entry.
    assert 'submission/development/submission.npz' in keys
    assert 'submission/confirmation/submission.npz' in keys
    assert len(keys) == 4
    assert 'SEAL.json' not in keys
    verification = verify_export(directory)
    # The fixture directory intentionally lacks SOURCES/LICENSE members;
    # hash integrity itself must still be verified clean.
    assert all('tampered' not in issue and 'count' not in issue
               for issue in verification['issues'])


def test_published_export_verifies_and_survives_tampering_detection(tmp_path):
    controller = _completed_job(tmp_path)
    outcome = publish(controller, export=True)
    assert outcome['accepted'] and outcome.get('verified') is True
    seed_dir = Path(outcome['export'])
    seal = json.loads((seed_dir / 'SEAL.json').read_text())
    file_count = len([p for p in seed_dir.rglob('*')
                      if p.is_file() and p.name != 'SEAL.json'])
    assert file_count == seal['file_count'] == len(seal['files'])

    # Tampering is detected, not silently accepted.
    victim = seed_dir / 'MANIFEST.json'
    original = victim.read_text()
    victim.write_text(original + 'tampered\n')
    broken = verify_export(seed_dir)
    assert broken['ok'] is False
    assert any('MANIFEST.json' in issue for issue in broken['issues'])
    victim.write_text(original)
    assert verify_export(seed_dir)['ok'] is True


def test_interrupted_publication_is_completed_not_trusted(tmp_path):
    controller = _completed_job(tmp_path)
    outcome = publish(controller, export=True)
    seed_dir = Path(outcome['export'])
    # Simulate a crash right before the seal was written.
    (seed_dir / 'SEAL.json').unlink()
    assert verify_export(seed_dir)['ok'] is False
    again = publish(controller, export=True)
    assert again['accepted'] is True and again.get('verified') is True
    assert verify_export(seed_dir)['ok'] is True
    events = [event['kind'] for event in controller.store.list_events()]
    assert 'publish_interrupted_recovered' in events


def test_existing_verified_export_is_immutable(tmp_path):
    controller = _completed_job(tmp_path)
    first = publish(controller, export=True)
    second = publish(controller, export=True)
    assert second['existing'] is True and second['verified'] is True
    assert first['export'] == second['export']
