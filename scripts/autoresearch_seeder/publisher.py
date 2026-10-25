"""Publisher: machine-checkable acceptance gates and immutable seed export.

A seed requires, without exception:
  * unchanged task/protocol identity (registry hashes),
  * full development PASS and confirmation PASS under distinct configured salts,
  * the same complete frozen source bundle and submission content across both
    checks, verified by hashes — and equal to the CURRENT bundle, so a receipt
    for candidate A can never qualify candidate B,
  * improvement over the stated baseline under the existing normalization with
    both measured results retained (conservative: both salts must exceed the
    baseline; the more favorable salt is never picked silently),
  * reproducible generation instructions and necessary helper files,
  * source attribution with explicit license status; unresolved reuse questions
    stay visible in the package.

Publishing a package never installs it into a campaign. Model-printed scores
are not an input to any gate.
"""
import json
import shutil
from pathlib import Path

from .models import bundle_hash, digest, file_digest, utc


def _receipt_of(store, kind):
    latest = None
    for experiment in store.list_experiments(kind):
        if latest is None or experiment.get('created_utc', '') >= latest.get('created_utc', ''):
            latest = experiment
    return latest


def evaluate_gates(controller) -> dict:
    """Return {'accepted': bool, 'reasons': [...], 'evidence': {...}}."""
    store = controller.store
    adapter = controller.adapter
    config = controller.config
    reasons = []

    # 1. Task and protocol identity unchanged.
    identity = adapter.identity()
    if identity['manifest_sha256'] != controller.job_state().get('task_manifest_sha256'):
        reasons.append('Task manifest hash changed since job creation')
    if identity['protocol_sha256'] != controller.job_state().get('task_protocol_sha256'):
        reasons.append('Task protocol hash changed since job creation')

    # 2. Both official checks, PASS, distinct salts.
    development = _receipt_of(store, 'development_validation')
    confirmation = _receipt_of(store, 'confirmation_validation')
    if not development or development.get('status') != 'pass':
        reasons.append('No PASSing full development validation receipt')
        development = development or {}
    if not confirmation or confirmation.get('status') != 'pass':
        reasons.append('No PASSing confirmation validation receipt')
        confirmation = confirmation or {}
    if development and confirmation:
        salts = {development.get('params', {}).get('salt')
                 or development.get('receipt', {}).get('salt'),
                 confirmation.get('params', {}).get('salt')
                 or confirmation.get('receipt', {}).get('salt')}
        if len(salts) != 2 or None in salts:
            reasons.append('Development and confirmation salts are not distinct recorded values')

    # 3. Same frozen bundle and submission across checks, and equal to the
    #    current artifact state.
    current_bundle = None
    try:
        current_bundle = bundle_hash(controller.dispatcher.artifact)
    except ValueError as exc:
        reasons.append(f'Current artifact bundle invalid: {exc}')
    for label, experiment in (('development', development), ('confirmation', confirmation)):
        if not isinstance(experiment, dict) or not experiment:
            continue
        recorded = experiment.get('input_bundle_sha256')
        if not recorded:
            reasons.append(f'{label} receipt has no recorded bundle hash')
        elif current_bundle is not None and recorded != current_bundle:
            reasons.append(f'{label} receipt bundle hash does not match the current '
                           'artifact bundle (receipt for a different candidate)')
        program = experiment.get('receipt', {}).get('source_sha256')
        current_program = None
        from pathlib import PurePosixPath
        program_path = (controller.dispatcher.artifact
                        / PurePosixPath(adapter.candidate_file).name)
        if program_path.is_file():
            current_program = file_digest(program_path)
        if program and current_program and program != current_program:
            reasons.append(f'{label} receipt source hash does not match current program.py')
    if development and confirmation:
        submissions = []
        for experiment in (development, confirmation):
            manifest = (experiment.get('receipt') or {}).get('submission_files_sha256')
            submissions.append(digest(manifest) if manifest else None)
        if len(set(submissions)) != 1 or submissions[0] is None:
            reasons.append('Frozen submission content differs between the two checks')

    # 4. Improvement over baseline, conservatively on both salts.
    baseline = adapter.baseline_score()
    margin = float(config.get('validation', {}).get('improvement_margin', 0.0))
    scores = {}
    for label, experiment in (('development', development), ('confirmation', confirmation)):
        if isinstance(experiment, dict) and experiment:
            score = (experiment.get('metrics') or {}).get('combined_score')
            scores[label] = score
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                reasons.append(f'{label} receipt carries no measured combined score')
            elif score <= baseline + margin:
                reasons.append(f'{label} score {score} does not exceed baseline '
                               f'{baseline} + margin {margin}')
    # Trust envelope: receipts must validate through the task's own adapter.
    if isinstance(development, dict) and development:
        try:
            adapter.validate_receipt(development.get('receipt', {}), 'development_verified')
        except Exception as exc:
            reasons.append(f'Development receipt rejected by task adapter: {exc}')
    if isinstance(confirmation, dict) and confirmation:
        try:
            adapter.validate_receipt(confirmation.get('receipt', {}), 'independently_verified')
        except Exception as exc:
            reasons.append(f'Confirmation receipt rejected by task adapter: {exc}')

    # 5. Reproducible generation instructions.
    generation = controller.dispatcher.artifact / 'GENERATION.md'
    if not generation.is_file() or len(generation.read_text().strip()) < 40:
        reasons.append('artifact/GENERATION.md with reproducible generation '
                       'instructions is required')

    # 6. Provenance: at least one recorded accessed source with explicit
    #    license status; unresolved questions stay visible in the package.
    sources = [source for source in store.list_sources('accessed')]
    if not sources:
        reasons.append('No accessed primary sources recorded; provenance required')
    for source in sources:
        if not source.get('license'):
            reasons.append(f"Source without license status: {source['url']}")

    return {'accepted': not reasons, 'reasons': reasons,
            'evidence': {'identity': identity, 'baseline': baseline, 'scores': scores,
                         'current_bundle': current_bundle,
                         'development': development if isinstance(development, dict) else {},
                         'confirmation': confirmation if isinstance(confirmation, dict) else {},
                         'sources': sources, 'generation': str(generation)}}


def _seed_id(controller, gates) -> str:
    core = {'task': controller.adapter.task_id,
            'manifest': gates['evidence']['identity']['manifest_sha256'],
            'protocol': gates['evidence']['identity']['protocol_sha256'],
            'bundle': gates['evidence']['current_bundle'],
            'development': gates['evidence']['development'].get('receipt_sha256'),
            'confirmation': gates['evidence']['confirmation'].get('receipt_sha256')}
    return 'seed-' + controller.adapter.task_id + '-' + digest(core)[:16]


def seal_export(seed_dir) -> dict:
    """Hash-seal every file by its path RELATIVE to the seed directory.

    Relative paths are required: different subdirectories legitimately contain
    files with the same basename (e.g. submission/development/submission.npz
    and submission/confirmation/submission.npz), and a basename-keyed seal
    silently loses the duplicates. SEAL.json itself is written after the
    enumeration and therefore seals every other file.
    """
    seed_dir = Path(seed_dir)
    files = {path.relative_to(seed_dir).as_posix(): file_digest(path)
             for path in sorted(seed_dir.rglob('*'))
             if path.is_file() and path.name != 'SEAL.json'}
    seal = {'files': files, 'file_count': len(files), 'sealed_utc': utc(),
            'note': 'Keys are paths relative to the seed directory.'}
    (seed_dir / 'SEAL.json').write_text(json.dumps(seal, indent=2, sort_keys=True) + '\n')
    return seal


def verify_export(seed_dir) -> dict:
    """Independently verify a sealed export: every current file matches its
    sealed hash, no unexpected files exist, and the required members are
    present. Publication only succeeds when this passes."""
    seed_dir = Path(seed_dir)
    seal_path = seed_dir / 'SEAL.json'
    if not seal_path.is_file():
        return {'ok': False, 'issues': ['SEAL.json missing (interrupted publication?)']}
    seal = json.loads(seal_path.read_text())
    issues = []
    expected = {'MANIFEST.json', 'SOURCES.json', 'LICENSE-STATUS.md'}
    for member in expected:
        if member not in seal['files']:
            issues.append(f'sealed export is missing {member}')
    if 'source-bundle/' not in ''.join(seal['files']):
        issues.append('sealed export is missing the source bundle')
    current = {path.relative_to(seed_dir).as_posix()
               for path in seed_dir.rglob('*')
               if path.is_file() and path.name != 'SEAL.json'}
    for relative in sorted(current):
        if relative not in seal['files']:
            issues.append(f'unsealed file present: {relative}')
            continue
        if file_digest(seed_dir / relative) != seal['files'][relative]:
            issues.append(f'file tampered or changed after sealing: {relative}')
    for relative in seal['files']:
        if relative not in current:
            issues.append(f'sealed file deleted: {relative}')
    if len(current) != len(seal['files']):
        issues.append(f"file count mismatch: {len(current)} present, "
                      f"{len(seal['files'])} sealed")
    return {'ok': not issues, 'issues': issues}


def publish(controller, export: bool = True, force: bool = False) -> dict:
    """Evaluate gates; when accepted, write an immutable export under exports/.

    A failed gate evaluation is recorded as a rejection receipt (sample-able),
    never as a published claim. Success is returned only after the sealed
    export passes independent verification; an existing-but-unsealed directory
    (interrupted publication) is completed rather than trusted.
    """
    gates = evaluate_gates(controller)
    exports = controller.job_dir / 'exports'
    exports.mkdir(parents=True, exist_ok=True)
    if not gates['accepted']:
        rejection = {'status': 'rejected', 'reasons': gates['reasons'], 'utc': utc(),
                     'evidence': {key: gates['evidence'][key]
                                  for key in ('identity', 'baseline', 'scores')}}
        path = exports / f"rejection-{digest(gates['reasons'])[:12]}.json"
        if not path.exists():
            path.write_text(json.dumps(rejection, indent=2) + '\n')
        controller.store.event('publish_rejected', {'reasons': gates['reasons'],
                                                    'receipt': str(path)})
        return {'accepted': False, 'reasons': gates['reasons'], 'rejection': str(path)}

    seed_id = _seed_id(controller, gates)
    seed_dir = exports / seed_id
    interrupted = seed_dir.exists() and not verify_export(seed_dir)['ok']
    if seed_dir.exists() and not interrupted and not force:
        verification = verify_export(seed_dir)
        if verification['ok']:
            return {'accepted': True, 'seed_id': seed_id, 'export': str(seed_dir),
                    'existing': True, 'verified': True,
                    'reasons': ['Seed already exported; immutable and verified']}
        interrupted = True
    if interrupted:
        controller.store.event('publish_interrupted_recovered',
                               {'seed_id': seed_id,
                                'issues': verify_export(seed_dir)['issues']})
        shutil.rmtree(seed_dir)
    if not seed_dir.exists():
        seed_dir.mkdir()
        evidence = gates['evidence']
        # Frozen copies: source bundle, both receipts, frozen submission content.
        shutil.copytree(controller.dispatcher.artifact, seed_dir / 'source-bundle')
        for label in ('confirmation', 'development'):
            experiment = evidence.get(label) or {}
            log_path = experiment.get('log_path')
            if log_path and Path(log_path).is_file():
                (seed_dir / 'receipts').mkdir(exist_ok=True)
                shutil.copyfile(log_path, seed_dir / 'receipts' / f'{label}.json')
            submission = Path(str(log_path)).parent / 'submission' if log_path else None
            if submission and submission.is_dir():
                (seed_dir / 'submission').mkdir(exist_ok=True)
                shutil.copytree(submission, seed_dir / 'submission' / label,
                                dirs_exist_ok=True)
        sources = {'sources': evidence['sources'],
                   'note': 'Every reused source keeps URL, revision/content hash, '
                           'attribution and license status. Unresolved reuse '
                           'questions are visible here, not hidden.'}
        (seed_dir / 'SOURCES.json').write_text(json.dumps(sources, indent=2) + '\n')
        (seed_dir / 'LICENSE-STATUS.md').write_text(
            '# License status\n\n'
            + '\n'.join(f"- `{source['url']}` — license: {source.get('license', 'unknown')}; "
                        f"attribution: {source.get('attribution', '') or 'not recorded'}"
                        for source in evidence['sources']) + '\n')
        manifest = {
            'seed_id': seed_id,
            'task': evidence['identity']['task_id'],
            'task_manifest_sha256': evidence['identity']['manifest_sha256'],
            'task_protocol_sha256': evidence['identity']['protocol_sha256'],
            'parent_baseline': {'identity': 'official frozen starting artifact',
                                'sha256': evidence['identity']['seed_program_sha256'],
                                'normalized_score': evidence['baseline']},
            'candidate_bundle_sha256': evidence['current_bundle'],
            'development': {'receipt_sha256': evidence['development'].get('receipt_sha256'),
                            'score': evidence['scores'].get('development'),
                            'salt': evidence['development'].get('receipt', {}).get('salt')},
            'confirmation': {'receipt_sha256': evidence['confirmation'].get('receipt_sha256'),
                             'score': evidence['scores'].get('confirmation'),
                             'salt': evidence['confirmation'].get('receipt', {}).get('salt')},
            'measured_improvement': {
                'development_ratio': evidence['scores'].get('development'),
                'confirmation_ratio': evidence['scores'].get('confirmation'),
                'comparison': 'both salts must exceed the baseline; no favorable pick'},
            'provenance': [source['url'] for source in evidence['sources']],
            'resource_accounting': controller.store.totals(),
            'production_enabled': False,
            'installed_into_campaign': False,
            'created_utc': utc(),
        }
        (seed_dir / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        seal_export(seed_dir)
    verification = verify_export(seed_dir)
    if not verification['ok']:
        controller.store.event('seed_publish_failed', {'seed_id': seed_id,
                                                        'issues': verification['issues']})
        return {'accepted': False, 'seed_id': seed_id, 'export': str(seed_dir),
                'reasons': verification['issues']}
    controller.store.event('seed_published', {'seed_id': seed_id,
                                              'export': str(seed_dir),
                                              'verified': True})
    return {'accepted': True, 'seed_id': seed_id, 'export': str(seed_dir),
            'verified': True}
