"""Download optional checkpoint pool; never called inside candidate execution."""
import json
from pathlib import Path
from huggingface_hub import snapshot_download
root=Path(__file__).resolve().parents[1]
p=json.loads((root/'tasks/gift_forecasting_v2/protocol.json').read_text())
for name,model in p['models'].items():
 destination=root/p['models_host_dir']/Path(model['path']).name
 snapshot_download(model['repo'],revision=model.get('revision'),local_dir=destination)
 print(name, destination)
