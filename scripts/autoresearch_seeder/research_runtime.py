"""Materialized, durable scout/reproducer jobs behind the autonomous agenda."""
import argparse
import contextlib
import copy
import io
import json
import shutil
from pathlib import Path

from .models import digest


def _close(controller):
    controller.store.close()
    if controller.dispatcher.store is not controller.store:
        controller.dispatcher.store.close()


def _follow_up_requirements(root, record, task):
    if not record['origin'].startswith('public_hypothesis_follow_up:'):
        return {}, None
    from .publisher import verify_export
    from math import isfinite
    checkpoint = record['checkpoint']
    handoff = Path(checkpoint['public_inputs'][0]['path']).resolve()
    if not handoff.is_relative_to(root.resolve()/'follow-up-inputs'):
        raise ValueError('Follow-up handoff outside own research root')
    data = json.loads((handoff/'RESEARCH-HANDOFF.json').read_text())
    export = Path(data['parent_export']).resolve()
    parent_root = root.resolve()/'jobs/autoresearch-seeder'/task/checkpoint['parent_investigation']/'exports'
    if not export.is_relative_to(parent_root) or not verify_export(export)['ok']:
        raise ValueError('Follow-up requires its exact certified public parent')
    manifest = json.loads((export/'MANIFEST.json').read_text())
    scores = [manifest[k]['score'] for k in ('development', 'confirmation')]
    if manifest['task'] != task or any(isinstance(s, bool) or not isinstance(s, (int,float))
                                     or not isfinite(s) or s <= 0 for s in scores):
        raise ValueError('Follow-up parent score/task invalid')
    return {'research_parent_score': min(scores), 'research_parent_export': str(export),
            'research_target_hypothesis': data['hypothesis']['id']}, data['hypothesis']


def _create_job(root, record, research):
    from . import ROOT
    from .__main__ import cmd_init
    task = research.get('task', 'dfthcsos')
    follow_up_validation, inherited_hypothesis = _follow_up_requirements(root, record, task)
    job = root / 'jobs/autoresearch-seeder' / task / record['id']
    if (job / 'job.json').exists():
        # Upgrade the initial accepted scout's execution routing only at a
        # session boundary. Candidate/source/verifier/protocol bytes stay intact.
        data=json.loads((job/'job.json').read_text())
        config_path=Path(data['config_path'])
        existing=json.loads(config_path.read_text())
        target_budgets = {'model_session_seconds': record['budgets']['max_model_seconds'],
                          'max_total_cost_usd': record['budgets']['max_usd']}
        budget_changed = any(existing['budgets'].get(k) != v for k, v in target_budgets.items())
        follow_up_changed = any(existing['validation'].get(k) != v for k,v in follow_up_validation.items())
        if not existing.get('validation',{}).get('deferred_development') or budget_changed or follow_up_changed or not existing.get('research',{}).get('defer_provider_retries'):
            from .controller import _process_alive
            lease_path=job/'private/lease.json'
            lease=json.loads(lease_path.read_text()) if lease_path.exists() else {}
            if not lease.get('released') and _process_alive(lease.get('owner',{})):
                raise RuntimeError('Routing migration waits for the active session boundary')
            from .models import atomic_write
            from .store import ResearchStore
            before=digest(existing)
            existing.setdefault('validation',{})['deferred_development']=True
            existing.setdefault('research',{})['defer_provider_retries']=True
            existing['validation'].update(follow_up_validation)
            existing['budgets'].update(target_budgets)
            existing['budgets']['job_wall_clock_seconds'] = max(
                existing['budgets']['job_wall_clock_seconds'], record['budgets']['max_model_seconds'] * 4)
            atomic_write(config_path,json.dumps(existing,indent=2))
            data['config_digest']=digest(existing)
            atomic_write(job/'job.json',json.dumps(data,indent=2))
            store=ResearchStore(job/'private/research.sqlite')
            if inherited_hypothesis and not store.get_hypothesis(inherited_hypothesis['id']):
                store.record_hypothesis(inherited_hypothesis)
            store.event('infrastructure_routing_migration',{'before':before,'after':digest(existing),
                        'change':'align trusted agenda budgets/routing at idle boundary; consumption and official protocol unchanged'})
            store.close()
        return job
    base = json.loads((ROOT / 'configs/autoresearch_seeder.example.json').read_text())
    total = record['budgets']
    base.update(enabled=True, task=task)
    base['provider'] = research.get('reproducer', research['provider'])
    base['validation']['deferred_development'] = True
    base['validation'].update(follow_up_validation)
    base['budgets'].update(model_session_seconds=total['max_model_seconds'],
                           job_wall_clock_seconds=max(14400, total['max_model_seconds'] * 4),
                           max_total_cost_usd=total['max_usd'])
    base['research'].update(research.get('research',{}))
    base['research']['defer_provider_retries']=True
    base['research']['search_credential_file'] = research.get('search_credential_file', '')
    config = root / 'job-configs' / (record['id'] + '.json')
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(base, indent=2))
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_init(argparse.Namespace(config=str(config), task=task,
                                    task_root=research.get('task_root', str(ROOT)),
                                    run_root=str(root / 'jobs'), job_id=record['id']))
    # Only operator-configured public inputs are imported. Never scan runs for
    # scientific results. Preserve the supplied bundle audit and qualifications.
    public_inputs = record.get('checkpoint', {}).get('public_inputs', research.get('public_inputs', []))
    if public_inputs:
        from .store import ResearchStore
        from .models import bundle_hash, utc
        store = ResearchStore(job / 'private/research.sqlite')
        try:
            for index, item in enumerate(public_inputs):
                source = Path(item['path']).resolve()
                if not source.is_dir() or source.is_symlink():
                    raise ValueError('Public input must be an explicit directory')
                files = [p for p in source.rglob('*') if p.is_file()]
                if len(files) > 4096 or sum(p.stat().st_size for p in files) > 128*2**20:
                    raise ValueError('Public input exceeds bundle limit')
                if any(p.is_symlink() or (p.is_file() and p.stat().st_nlink != 1) for p in source.rglob('*')):
                    raise ValueError('Public input contains links')
                destination = job / 'sources' / ('provided-' + str(index))
                shutil.copytree(source, destination)
                store.record_source({'url': item['url'], 'status': 'accessed',
                    'kind': 'user-provided-public-bundle', 'content_sha256': bundle_hash(destination),
                    'local_path': str(destination), 'license': item.get('license', 'unknown'),
                    'attribution': item['attribution'], 'retrieved_utc': utc(),
                    'relevance': 'Operator-provided public research material. Read BUNDLE_AUDIT.json; '
                                 'source claims and author scores are not local measurements.'})
        finally:
            store.close()
    if inherited_hypothesis:
        from .store import ResearchStore
        store=ResearchStore(job/'private/research.sqlite')
        store.record_hypothesis(inherited_hypothesis)
        store.close()
    return job


def _finding(controller, record, knowledge, facts, job, role):
    """Model text cannot grant verified-seed status; only the publisher can."""
    from .publisher import publish
    state = controller.job_state()
    if record['origin'].startswith('public_hypothesis_follow_up:') and state['stage'] != 'seed_ready':
        # Parent diagnostics may pass without testing the new mechanism.
        # Preserve them as memory, but never advertise them as positive advice.
        return None
    store = controller.store
    hypotheses = store.list_hypotheses()
    sources = store.list_sources('accessed')
    experiments = store.list_experiments()
    if not sources or not hypotheses:
        return None
    evidence = None
    if state['stage'] == 'seed_ready':
        published = publish(controller)
        if published['accepted']:
            evidence = {'level': 'verified_seed', 'export': published['export'],
                        'receipt_ids': [e['id'] for e in experiments if e['status'] == 'pass'
                                        and e['kind'] in ('development_validation', 'confirmation_validation')],
                        'task_protocol_sha256': controller.adapter.identity()['protocol_sha256']}
    elif role == 'reproducer':
        if (store.last_decision() or {}).get('action') == 'reject':
            return None
        # A passing diagnostic is a limited result, never an official score.
        passing = {e['id']: e for e in experiments if e['kind'] == 'diagnostic' and e['status'] == 'pass'}
        decisions = [d for d in store.list_decisions() if d['action'] in ('continue', 'refine')
                     and set(d.get('experiment_ids', [])) & set(passing)]
        if decisions:
            ids = sorted(set(decisions[-1]['experiment_ids']) & set(passing))
            evidence = {'level': 'diagnostic_supported', 'receipt_ids': ids,
                        'interpretation': decisions[-1].get('notes', ''),
                        'limits': 'Sandboxed diagnostic passed; relevance is the reproducer interpretation. '
                                  'No official score or full correctness claim.'}
    if not evidence:
        return None
    decision=store.last_decision() or {}
    selected=[h for h in hypotheses if h['id']==decision.get('hypothesis_id')]
    if len(hypotheses)>1 and not selected:return None
    hypothesis = selected[-1] if selected else hypotheses[-1]
    if not set(hypothesis.get('source_urls', [])) & {s['url'] for s in sources}:
        if evidence['level'] != 'verified_seed':
            return None
        # Optional hypothesis citation fields must not discard an already
        # certified export. Its publisher-gated, sealed source manifest is the
        # authoritative provenance for this exact artifact, not inferred prose.
        from .publisher import verify_export
        export = Path(evidence['export'])
        if not verify_export(export)['ok']:
            return None
        sealed_sources = json.loads((export / 'SOURCES.json').read_text()).get('sources', [])
        if not sealed_sources or not {x['url'] for x in sealed_sources} <= {x['url'] for x in sources}:
            return None
        sources = sealed_sources
    package = {'mechanism': hypothesis['mechanism'], 'sources': sources,
               'compatibility': {'task': controller.adapter.task_id, 'applies_to_parents': True},
               'evidence': evidence, 'opportunity': hypothesis['expected_opportunity'],
               'first_experiment': hypothesis['first_test'],
               'research_memory': {'hypotheses': hypotheses, 'decisions': store.list_decisions()}}
    # Idempotent across interrupted publication/checkpoint writes.
    evidence_key = digest({'job': str(job), 'evidence': evidence})
    for row in knowledge.db.execute("SELECT id FROM records WHERE kind='package'"):
        old = knowledge.get(row[0])
        if old['payload'].get('research_evidence_key') == evidence_key:
            return old
    package['research_evidence_key'] = evidence_key
    return knowledge.add_finding(package, branch=record.get('branch'), level=record['level'],
                                 inputs=[x['id'] for x in facts], ready=True)


def run_materialized_investigation(agenda, record, knowledge, research):
    from . import ROOT
    from .__main__ import _load_controller
    from .backends import HermesBackend
    from .investigations import eligible_knowledge
    if record['status'] not in ('queued','active'):return record
    root = Path(research['root'])
    job = _create_job(root, record, research)
    controller, _, _ = _load_controller(job)
    # The scout gets one saved window, then hands its complete durable state
    # to the reproducer even if it omitted a structured hypothesis call.
    # Otherwise an exploratory scout can monopolize every checkpoint and
    # prevent the stronger implementation/checking role from ever starting.
    scout_window_finished = (record['consumed']['sessions'] > 0
                             and record.get('checkpoint', {}).get('role') in ('scout', 'reproducer'))
    prepared_follow_up = (record['origin'].startswith('public_hypothesis_follow_up:')
                          and record.get('checkpoint', {}).get('start_role') == 'reproducer')
    role = 'reproducer' if controller.store.list_hypotheses() or scout_window_finished or prepared_follow_up else 'scout'
    _close(controller)
    provider = copy.deepcopy(research['provider'] if role == 'scout'
                             else research.get('reproducer', research['provider']))

    def factory(config):
        backend = HermesBackend(provider, job, app_root=ROOT)

        class Routed:
            def metadata(self):
                return {**backend.metadata(), 'research_role': role}

            def run(self, prompt, tools, workspace, budget):
                brief = ('Research agenda: ' + record['topic'] + '\n'
                         'Read worker/research-agenda.json and worker/task-api/description.txt. '
                         'Use only job-relative file tools; write code to worker/attempt_00/artifact/.\n')
                if record.get('checkpoint', {}).get('public_inputs', research.get('public_inputs', [])):
                    brief += ('Operator-provided public materials are under sources/provided-*/. '
                              'Inspect the bundle audit/provenance before reusing code or data; '
                              'these are external sources, not private RSI discoveries.\n')
                if role == 'scout':
                    brief += ('ROLE: SCOUT. Inspect original external sources; compare distinct mechanisms. '
                              'Record concrete hypotheses with source URLs, compatibility, risks and cheapest first test. '
                              'Call propose_hypothesis with explicit source_urls (actual fetched URLs), then '
                              'save a precise decision/next action. Finish after a useful shortlist; '
                              'a separate reproducer continues your durable job. No official validation in this role.\n')
                    tools = [t for t in tools if t != 'run_development_validation']
                else:
                    brief += ('ROLE: REPRODUCER. Check the scout interpretation against original sources, correct errors, '
                              'If the scout left no structured hypotheses, first register source-linked hypotheses '
                              'from its own saved research, with explicit source_urls. '
                              'Implement and diagnose the selected method, then request full official validation. '
                              'Write artifact/GENERATION.md (via worker/attempt_00/artifact/GENERATION.md) with exact '
                              'generation instructions before validation. Record decisions citing actual experiment IDs. '
                              'Cite the chosen hypothesis_id in record_decision so evidence is attached to the correct method. '
                              'Preserve failed paths and next actions. Reject unsound ideas when warranted.\n')
                budget = dict(budget)
                remaining = record['budgets']['max_model_seconds'] - record['consumed']['model_seconds']
                budget['session_seconds'] = min(budget['session_seconds'], remaining,
                    float(research.get('budgets', {}).get('session_seconds', 1200)))
                admission=contextlib.nullcontext()
                capacity=research.get('provider_capacity_module')
                if capacity and provider.get('name')=='kimi_proxy':
                    import importlib.util
                    spec=importlib.util.spec_from_file_location('hermes_provider_capacity',capacity)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    admission=module.slot('kimi_proxy',job)
                import time
                waiting=time.monotonic()
                with admission:
                    waited=time.monotonic()-waiting
                    result=backend.run(brief + prompt, tools, workspace, budget)
                result.admission_wait_seconds=waited
                return result
        return Routed()

    controller, _, _ = _load_controller(job, transport_factory=research.get('test_transport_factory') or factory,
        search_service=research.get('test_search_service'), fetcher=research.get('test_fetcher'))
    # Cold acceptance receives only its explicitly frozen public sources.
    # Existing library successes must not leak into discovery/reproduction.
    facts = [] if record.get('checkpoint', {}).get('cold_acceptance') else eligible_knowledge(knowledge, record)
    context = job / 'worker/research-agenda.json'
    context.write_text(json.dumps({'topic': record['topic'], 'branch': record.get('branch'),
                                   'level': record['level'], 'eligible_knowledge': facts}, indent=2))
    api = job / 'worker/task-api'
    api.mkdir(exist_ok=True)
    description = controller.adapter.paths.get('description')
    if description and Path(description).is_file():
        shutil.copyfile(description, api / 'description.txt')
    else:
        (api / 'description.txt').write_text(controller.adapter.objective)
    for source in controller.adapter.paths['description'].parent.glob('*.py'):
        if source.name in ('evaluator.py','diagnose.py'): continue
        if source.stat().st_size < 2*2**20 and not source.is_symlink():
            target=api/source.name
            if not target.exists(): shutil.copyfile(source,target)
    before = controller.consumed()
    try:
        # Recover any orphan time before starting, never repeat completed experiments.
        controller._recover_orphan_session()
        state = controller.job_state()
        if state['stage'] == 'retry_wait':
            retry = state.get('retry', {})
            from .models import utc
            if retry.get('eligible_utc', '') > utc():
                return record
            controller.save_job(stage=retry.get('resume_stage', 'researching'))
        state = controller.run(max_sessions=1)
        finding = _finding(controller, record, knowledge, facts, job, role)
        activity = digest({'experiments': controller.store.list_experiments(),
                           'hypotheses': controller.store.list_hypotheses(),
                           'decisions': controller.store.list_decisions()})
        # Preserve negative and unfinished R&D too. These are research memory,
        # not ready advice, and branch-origin science remains branch-private.
        checkpoint_key=digest({'job':str(job),'activity':activity})
        prior=knowledge.eligible_records(record.get('branch') or '__shared__',record['level'])
        if not any(r['payload'].get('research_checkpoint_key')==checkpoint_key for r in prior):
            knowledge.add('branch_private' if record.get('branch') else 'external',
                {'research_checkpoint_key':checkpoint_key,'topic':record['topic'],
                 'hypotheses':controller.store.list_hypotheses(),
                 'decisions':controller.store.list_decisions(),
                 'experiments':[{'id':e['id'],'kind':e['kind'],'status':e['status'],
                                 'metrics':e.get('metrics'), 'conclusion':e.get('conclusion')}
                                for e in controller.store.list_experiments()],
                 'stage':state['stage'],'label':'R&D memory; not an accepted seed or ready handoff'},
                branch=record.get('branch'),level=record['level'])
        after = controller.consumed()
        checkpoint = {'job': str(job), 'job_stage': state['stage'], 'role': role,
                      'next_actions': [controller.store.last_decision().get('next_action', 'Continue own research')
                                       if controller.store.last_decision() else 'Continue own research']}
        if finding:
            checkpoint['finding_id'] = finding['id']
        updated = agenda.record_session(record['id'],
            model_seconds=max(0, after['model_seconds'] - before['model_seconds']),
            usd=max(0, after['usd'] - before['usd']), checkpoint_update=checkpoint, activity_digest=activity)
        from .controller import TERMINAL
        if state['stage'] in TERMINAL:
            status = 'completed' if state['stage'] in ('seed_ready','completed_no_improvement') else 'shelved'
            agenda.db.execute('UPDATE investigations SET status=? WHERE id=?', (status, record['id']))
            agenda.db.commit()
            updated = agenda.get(record['id'])
        return updated
    except BaseException:
        # The caller backs off. Preserve the job and account interrupted elapsed time
        # using the controller's durable orphan marker before any future paid start.
        controller._recover_orphan_session()
        after = controller.consumed()
        agenda.record_session(record['id'],
            model_seconds=max(0, after['model_seconds'] - before['model_seconds']),
            usd=max(0, after['usd'] - before['usd']),
            checkpoint_update={'job': str(job), 'job_stage': 'infrastructure_recovery_required'},
            activity_digest='infrastructure_recovery_required')
        raise
    finally:
        controller.finalize_segment()
        _close(controller)
