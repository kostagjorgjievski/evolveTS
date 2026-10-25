"""Host preparation adapter. Only explicitly opted-in future campaign attempts."""
import json
from pathlib import Path

from .rsi_bridge import attach


def prepare(run, branch, prompt, config_path):
    config_path=Path(config_path)
    if not config_path.is_file(): return prompt
    config=json.loads(config_path.read_text())
    if not config.get('enabled'): return prompt
    meta=json.loads((Path(run)/'pilot.json').read_text())
    campaign=meta.get('campaign')
    if not campaign or str(Path(campaign).resolve()) not in config.get('campaigns',[]):
        return prompt
    task=json.loads((Path(campaign)/'campaign.json').read_text())['task']
    root=config.get('knowledge_roots',{}).get(task)
    if not root:return prompt
    branch_id=task+'/'+Path(campaign).name+'/'+Path(run).parent.name
    return attach(run,branch,prompt,knowledge_root=root,branch_id=branch_id,
                  level=int(meta.get('level',0)),task=task)
