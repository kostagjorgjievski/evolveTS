"""Neutral GLM preparation, then fresh-context DFTHC-SOS optimization."""
import asyncio,datetime,json,os,shutil,sys,time
from pathlib import Path
import dfthcsos_pilot as pilot
from key_pool import KeyPool
ROOT=pilot.ROOT
PREP_PROMPT='''Prepare a reusable, neutral DFTHC-SOS task/API orientation guide.
Read task.txt, protocol.json, reference_program.py, baseline-result.json and
appropriate official_code/ modules in this branch. Learn the scoring objective,
accuracy and resource constraints, submitted array meanings and dimensions,
angle encoding, circuit register/XOR contract, generator output convention,
and actual kickmix/numpy/scipy/dfthcsos APIs. Test useful examples with executable
diagnostics. Confirm baseline numerical reconstruction where useful. Inspect
actual signatures/docstrings rather than guessing. Separate measured facts from
assumptions. Note any confusing submitted-vs-native coefficient conventions.

This is preparation ONLY: do not search literature, choose optimization methods,
propose a better algorithm or generate an entire full-size circuit for orientation.
Do not inspect other branches/runs. Read only this branch; write only
attempt_99/artifact/** and attempt_99/proposal.md. Use diagnose_candidate (60sec/2GiB)
or integration_test (600sec/8GiB): save attempt_99/artifact/diagnostic.py first,
then call the no-argument tool. Official modules and own helpers are importable;
execution is offline, official sources are read-only, only TEST_OUTPUT_DIR is
writable temporary scratch, and printed logs are returned on success. No verified
score is produced by diagnostics. No shell tool is exposed.

Write attempt_99/proposal.md as a concise, self-contained, tested preparation guide
for a FRESH model conversation that will inherit the official baseline code and
score. Include exact small API examples, diagnostic results, pitfalls, constraints,
and uncertainties. It will not receive this preparation conversation or your
scratch. Refer to real branch task/source files and avoid unavailable transcript
references. Leave useful neutral self-check examples in attempt_99/artifact/.
You have up to30 minutes for preparation, not a requirement to fill that time.
Stop when the guide is useful. The following optimization attempt has its OWN
fresh200-minute budget. GLM-5.3 max effort is configured.
'''

def run_prepared(run, recover=False):
    meta=json.loads((run/'pilot.json').read_text()) if recover else pilot.initialize(run)
    if recover and (meta.get('status')!='error' or not (run/'worker/explore_b0/attempt_99/proposal.md').is_file()):raise RuntimeError('Recover only a stopped preparation with a saved guide')
    meta.update(provider='glm',worker_model='glm-5.3[1m]',effort='max',experiment='prepared_context_literature_round',status='preparing',pid=os.getpid(),prepared_parent_context=True,conversation_memory=False,preparation_max_seconds=1800)
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')
    cfg=pilot.runner.environment(ROOT/'.credentials/glm.env')
    keys=[cfg['ANTHROPIC_AUTH_TOKEN']]+[s.strip() for s in (ROOT/'.credentials/glm-keys.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    keys=list(dict.fromkeys(keys));pool=KeyPool(keys,ROOT/'runs/dqi-accounting/glm/key-pool.json',2);index=pool.acquire()
    if index is None:raise RuntimeError('No GLM key slot available')
    cfg.update(ANTHROPIC_AUTH_TOKEN=keys[index],ANTHROPIC_MODEL='glm-5.3[1m]',GLM_REASONING_EFFORT='max',CLAUDE_CODE_EFFORT_LEVEL='max')
    for key in ('ANTHROPIC_SMALL_FAST_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL','ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_OPUS_MODEL'):cfg[key]='glm-5.3[1m]'
    meta['key_slot']=index;(run/'pilot.json').write_text(json.dumps(meta,indent=2))
    branch=run/'worker/explore_b0';prep=branch/'attempt_99';(prep/'artifact').mkdir(parents=True,exist_ok=recover)
    server,url=pilot.effort_proxy.start(keys[index],run/'private/provider-requests.jsonl',provider='glm',upstream=cfg['ANTHROPIC_BASE_URL'],effort='max',model='glm-5.3')
    started=time.monotonic()
    try:
        try:
            if not recover:
                try:
                    asyncio.run(pilot.runner.agent(run,prepare_fn=lambda directory:(branch,prep,PREP_PROMPT),server_script=Path(__file__).with_name('dfthcsos_server.py'),tool_names=('diagnose_candidate','integration_test'),base_url=url,max_session_seconds=1800,provider_override='glm',config_override=cfg,lease_glm=False))
                except TimeoutError:
                    if not (prep/'proposal.md').is_file():raise
                    meta['preparation_stop_reason']='Preparation allowance reached after guide was saved'
        finally:server.shutdown();server.server_close()
        if not (prep/'proposal.md').is_file():raise RuntimeError('Preparation guide missing; refusing to call unprepared coding run prepared')
        shutil.copyfile(prep/'proposal.md',branch/'preparation-guide.md')
        archive=run/'private/preparation';archive.mkdir()
        for name in ('status.json','worker-prompt.txt'):
            p=run/'private'/name
            if p.exists():shutil.copyfile(p,archive/name)
        # Removing the resume lookup file before the coding call guarantees a
        # fresh SDK conversation. The preparation transcript remains archived.
        sdk=run/'private/sdk'
        if sdk.exists():shutil.move(str(sdk),str(archive/'sdk'))
        events=run/'private/sdk-events.jsonl'
        if events.exists():shutil.move(str(events),str(archive/'sdk-events.jsonl'))
        source=json.loads((branch/'baseline-result.json').read_text())
        (branch/'parent-result.json').write_text(json.dumps({'development':{'status':source['status'],'combined_score':source['combined_score'],'official':source['official']},'parent':'official baseline'},indent=2)+'\n')
        meta.update(status='prepared',preparation_seconds=1800 if recover else time.monotonic()-started,max_session_seconds=12000,session_seconds_used=0,budget_scope='per_attempt')
        if recover:meta['preparation_stop_reason']='Recovered saved guide after preparation timeout'
        meta.pop('error',None)
        (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')
        assert not (run/'private/sdk/sdk-session.json').exists()
        pilot.work(run,config_override=cfg)
    finally:pool.release(index)

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('DFTHC-SOS run required')
    try:run_prepared(run,recover='--recover-guide' in sys.argv[2:])
    except BaseException as error:
        if (run/'pilot.json').exists():
            m=json.loads((run/'pilot.json').read_text());m.update(status='error',error=type(error).__name__+': '+str(error));(run/'pilot.json').write_text(json.dumps(m,indent=2))
        raise
