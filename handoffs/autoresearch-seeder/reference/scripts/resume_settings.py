"""Preserve evaluated failures on resume; retry unfinished agent sessions only."""
import json
import os
from dream_rsi.exploration import runner

original_resolve = runner._resolve_node
original_reset = runner.NodeStore.reset_for_retry


def resolve_preserving_evaluated(store, *, branch, seq, **kwargs):
    nid = runner.make_node_id(branch, seq)
    node = store.branch_dir(branch)/runner.attempt_name(seq)
    score = node/'eval/score.json'
    meta_file=node/'meta.json'
    if meta_file.is_file():
        try:
            if json.loads(meta_file.read_text()).get('status')=='failed':
                return node,nid,'skip'
        except (OSError,ValueError):pass
    if score.is_file() and (node/'meta.json').is_file():
        try:
            value = json.loads(score.read_text())
            if isinstance(value, dict) and isinstance(value.get('combined_score', value.get('score')), (int, float)):
                return node, nid, 'skip'
        except (OSError, ValueError):
            pass
    return original_resolve(store, branch=branch, seq=seq, **kwargs)


runner._resolve_node = resolve_preserving_evaluated


def reset_preserving_draft(self,nid):
    node=self.get_node_dir(nid)
    if os.environ.get('DRSI_PRESERVE_DRAFTS')=='1' and not (node/'eval/score.json').exists():
        meta=self.read_meta(nid)
        meta.status='draft'
        self._write_meta(node,meta)
        return node
    return original_reset(self,nid)


runner.NodeStore.reset_for_retry=reset_preserving_draft
