"""Trusted attempt-boundary bridge. No model call and no waiting for research.

Deploy this through the host's preparation hook. Existing active attempts are
untouched. The host configuration explicitly opts a campaign into advice.
"""
import hashlib
import json
import shutil
from pathlib import Path

from .knowledge import KnowledgeBase, check_findings
from .models import file_digest, atomic_write, utc


def branch_request(run, branch, knowledge_root, branch_id, level, task):
    """Own-parent science stays in this branch's compartment, including failures."""
    from .investigations import Investigations
    root=Path(knowledge_root)
    if not (root/'knowledge.sqlite').exists(): return
    key=hashlib.sha256(str(run.resolve()).encode()).hexdigest()
    base=KnowledgeBase(root/'knowledge.sqlite',timeout=0)
    agenda=None
    try:
        own=base.eligible_records(branch_id,level)
        if any(r['payload'].get('request_key')==key for r in own): return
        payload={'request_key':key,'task':task,'origin':'own prepared parent at attempt boundary'}
        candidates=sorted(branch.glob('attempt_*/artifact/program.py'))
        if candidates and candidates[-1].stat().st_size<=512*2**10:
            payload['parent_code']=candidates[-1].read_text()
            payload['parent_code_sha256']=file_digest(candidates[-1])
        memory=branch/'experimental-memory.md'
        if memory.is_file():
            payload['own_experimental_memory']=memory.read_text()[:64000]
            payload['memory_excerpt_limited_to_chars']=64000
        score=branch/'parent-result.json'
        if score.is_file() and score.stat().st_size<128*2**10:
            payload['parent_result']=json.loads(score.read_text())
        base.add('branch_private',payload,branch=branch_id,level=level)
        agenda=Investigations(root/'investigations.sqlite',timeout=0)
        if not any(r['branch']==branch_id and r['status'] in ('queued','active') for r in agenda.list()):
            agenda.create('Investigate a useful next direction for this own-parent '+task+
                ' branch. Read its private parent context and failed experiments; check compatibility. '
                'Independent external research is welcome. Do not relay other branches.',
                branch=branch_id,level=level,origin='branch_request',priority=1)
    finally:
        if agenda:agenda.close()
        base.close()


def attach(run, branch, prompt, *, knowledge_root, branch_id, level=0, task='dfthcsos'):
    if 'EXTERNAL R&D HANDOFFS:' in prompt: return prompt
    run, branch = Path(run), Path(branch)
    audit = run / 'private/hermes-handoff.json'
    if audit.exists():
        outcome = json.loads(audit.read_text())
    else:
        candidates = sorted(branch.glob('attempt_*/artifact/program.py'))
        parent = {'task': task}
        if candidates:
            parent['code_sha256'] = file_digest(candidates[-1])
        outcome = check_findings(knowledge_root, branch_id, level, parent=parent,
                                  attempt_record=str(run / 'private/hermes-attempt.json'), max_findings=1)
        try:
            branch_request(run,branch,knowledge_root,branch_id,level,task)
        except Exception as error:
            outcome['request_note']='Branch request unavailable ('+type(error).__name__+'); attempt proceeds'
        handoffs = branch / 'hermes-handoffs'
        handoffs.mkdir(exist_ok=True)
        copied = []
        for receipt in outcome.get('delivered', []):
            source = Path(receipt['snapshot_path'])
            if file_digest(source) != receipt['snapshot_sha256']:
                continue
            dest = handoffs / source.name
            shutil.copyfile(source, dest)
            snapshot=json.loads(source.read_text())
            evidence=snapshot['record']['payload'].get('evidence',{})
            if evidence.get('level')=='verified_seed':
                from .publisher import verify_export
                export=Path(evidence.get('export',''))
                if not verify_export(export)['ok']:
                    dest.unlink(missing_ok=True)
                    continue
                bundle=handoffs/snapshot['record']['id']/'source-bundle'
                if not bundle.exists():
                    shutil.copytree(export/'source-bundle',bundle)
                snapshot['worker_source_bundle']=str(bundle.relative_to(branch))
                dest.write_text(json.dumps(snapshot,indent=2))
            copied.append({'path': str(dest.relative_to(branch)), 'sha256': file_digest(dest)})
        outcome['worker_files'] = copied
        outcome['branch_id'] = branch_id
        outcome['task'] = task
        outcome['checked_utc'] = utc()
        # The worker receives only frozen handoffs, never DB paths or another branch's records.
        atomic_write(audit, json.dumps(outcome, indent=2))
    files = outcome.get('worker_files', [])
    if not files or any(not (branch/f['path']).is_file() or file_digest(branch/f['path'])!=f['sha256'] for f in files):
        return prompt
    return prompt + ('\nEXTERNAL R&D HANDOFFS: Read the frozen JSON packages in hermes-handoffs/. '
        'Check compatibility with your parent before adopting a method. diagnostic_supported means a limited '
        'diagnostic only; verified_seed requires full official receipts. Printed/author scores are claims. '
        'You may reject advice; record why in your own research-state.md. No wait for the researcher is required. '
        'Any seeded-source adoption must still pass your ordinary full validation.\n')
