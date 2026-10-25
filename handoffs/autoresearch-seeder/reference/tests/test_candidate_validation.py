"""The validator snapshots only its bound regular source file and grants no shell."""
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from candidate_validation import snapshot_program
import candidate_validation_tools as tools


def make_attempt(tmp_path):
    attempt=tmp_path/'explore_b0/attempt_00'
    (attempt/'artifact').mkdir(parents=True)
    return attempt


def test_snapshot_rejects_links_and_special_files(tmp_path):
    attempt=make_attempt(tmp_path);source=attempt/'artifact/program.py';target=tmp_path/'snapshot.py'
    outside=tmp_path/'secret';outside.write_text('secret')
    source.symlink_to(outside)
    with pytest.raises(OSError):snapshot_program(attempt,target)
    source.unlink();os.link(outside,source)
    with pytest.raises(ValueError,match='regular'):snapshot_program(attempt,target)
    source.unlink();os.mkfifo(source)
    with pytest.raises(ValueError,match='regular'):snapshot_program(attempt,target)
    source.unlink();(attempt/'artifact').rmdir();(attempt/'artifact').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(OSError):snapshot_program(attempt,target)
    assert not target.exists()


def test_snapshot_and_clean_bound_server(tmp_path):
    attempt=make_attempt(tmp_path);(attempt/'artifact/program.py').write_text('print(1)\n')
    target=tmp_path/'snapshot.py';digest=snapshot_program(attempt,target)
    assert len(digest)==64 and target.read_text()=='print(1)\n'
    config=tools.server_config(attempt)
    assert config['command']=='/usr/bin/env'
    assert '-i' in config['args']
    assert config['args'][-2:]==['--attempt',str(attempt)]
    assert not any('TOKEN=' in part or 'API_KEY=' in part for part in config['args'])


def test_diagnostic_snapshot_is_separate_and_logs_are_bounded(tmp_path):
    from candidate_validation import bounded_log
    attempt=make_attempt(tmp_path)
    (attempt/'artifact/program.py').write_text('submission')
    (attempt/'artifact/diagnostic.py').write_text('diagnostic')
    target=tmp_path/'snapshot.py'
    snapshot_program(attempt,target,'diagnostic.py')
    assert target.read_text()=='diagnostic'
    with pytest.raises(ValueError):snapshot_program(attempt,target,'../../secret')
    log=tmp_path/'log';log.write_text('x'*20000+'final diagnostic')
    result=bounded_log(log)
    assert result['truncated'] and len(result['text'])==16000
    assert result['text'].endswith('final diagnostic')
