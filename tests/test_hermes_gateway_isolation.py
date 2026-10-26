"""Parallel headless jobs must not share Hermes's user gateway singleton."""
import os
from pathlib import Path
import subprocess

import pytest
from scripts.autoresearch_seeder.backends import HermesBackend


def test_job_local_environment_does_not_inherit_another_gateway(tmp_path,monkeypatch):
    monkeypatch.setenv('HERMES_GATEWAY_LOCK_DIR','/unrelated/global/lock')
    a=HermesBackend({'credential_file':'unused'},tmp_path/'a')
    b=HermesBackend({'credential_file':'unused'},tmp_path/'b')
    assert a.session_environment()['HERMES_GATEWAY_LOCK_DIR']!=b.session_environment()['HERMES_GATEWAY_LOCK_DIR']
    assert Path(a.session_environment()['HERMES_GATEWAY_LOCK_DIR']).is_relative_to(a.home)
    assert 'ANTHROPIC_AUTH_TOKEN' not in a.session_environment()


def test_real_upstream_gateway_locks_allow_two_jobs_but_refuse_duplicate_owner(tmp_path):
    runtime=Path('/Users/kostagj/Documents/ChatGPT/EvolveTS-seeder-review/work/hermes-agent-runtime')
    python=runtime/'.venv/bin/python'
    if not python.is_file():pytest.skip('pinned Hermes runtime required')
    a=HermesBackend({'credential_file':'unused'},tmp_path/'a')
    b=HermesBackend({'credential_file':'unused'},tmp_path/'b')
    code='from gateway.host_rendezvous import claim_host_lock,ROLE_GATEWAY; print(claim_host_lock(ROLE_GATEWAY)[0].name,flush=True)'
    held=subprocess.Popen([str(python),'-u','-c',code+'; input()'],cwd=runtime,env=a.session_environment(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert held.stdout.readline().strip()=='ACQUIRED'
        other=subprocess.run([str(python),'-c',code],cwd=runtime,env=b.session_environment(),capture_output=True,text=True,timeout=30,check=True)
        duplicate=subprocess.run([str(python),'-c',code],cwd=runtime,env=a.session_environment(),capture_output=True,text=True,timeout=30,check=True)
        assert other.stdout.strip()=='ACQUIRED'
        assert duplicate.stdout.strip()=='HELD_BY_OTHER'
    finally:
        held.communicate('\n',timeout=10)
