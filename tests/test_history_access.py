import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from history_access import history_access_note

def test_linked_history_lists_original_files_and_errors(tmp_path):
    archive=tmp_path/'history/iter000/explore_b0/attempt_00'
    for name in ['proposal.md','eval/score.json','error.txt','artifact/program.py']:
        f=archive/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(name)
    branch=tmp_path/'explore_b0';(branch/'history').mkdir(parents=True)
    (branch/'history/iter000').symlink_to(tmp_path/'history/iter000',target_is_directory=True)
    node=branch/'attempt_00';note=history_access_note(tmp_path,node)
    index=(node/'agent_log/history-files.md').read_text()
    assert '1 historical proposals' in note
    for name in ['proposal.md','eval/score.json','error.txt','artifact/program.py']:
        assert str(archive/name) in index
    assert json.loads((node/'agent_log/history-files.json').read_text())['proposal_count']==1

def test_new_e0_has_no_history_note(tmp_path):
    assert history_access_note(tmp_path,tmp_path/'explore_b0/attempt_00')==''

def test_archives_do_not_include_live_sibling_branches(tmp_path):
    live=tmp_path/'explore_b9/attempt_00/proposal.md';live.parent.mkdir(parents=True);live.write_text('private live branch')
    assert history_access_note(tmp_path,tmp_path/'explore_b0/attempt_00')==''
