"""Fetch pinned worker package sources; binaries/model weights are not vendored."""
import hashlib,json,tarfile,tempfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
 ('toto2-9213d2c.tar.gz','DataDog/toto','9213d2c86f716c43010a0a3b2b6a0e3f440e6743','toto2'),
 ('timestral-a534bdb.tar.gz','mistralai/timestral','a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff',None),
 ('granite-tsfm-dfe846e.tar.gz','ibm-granite/granite-tsfm','dfe846e6c1f1b0086b4a7b0831249ac8aeb7dcd7',None)]

def main():
 out=ROOT/'tasks/gift_forecasting_v2/vendor';out.mkdir(parents=True,exist_ok=True)
 records=[]
 for name,repo,commit,subdir in SOURCES:
  url=f'https://codeload.github.com/{repo}/tar.gz/{commit}'
  with tempfile.TemporaryDirectory() as temp:
   archive=Path(temp)/'source.tar.gz';urllib.request.urlretrieve(url,archive)
   if subdir:
    source=Path(temp)/'source';source.mkdir()
    with tarfile.open(archive) as tar:
     for item in tar:
      parts=Path(item.name).parts[1:]
      if not item.isfile() or not parts or parts[0]!=subdir or '..' in parts:continue
      relative=Path(*parts[1:])
      if not relative.parts:continue
      target=source/relative;target.parent.mkdir(parents=True,exist_ok=True)
      target.write_bytes(tar.extractfile(item).read())
    with tarfile.open(out/name,'w:gz') as tar:tar.add(source,arcname='toto2')
   else:(out/name).write_bytes(archive.read_bytes())
   records.append({'file':name,'repository':repo,'commit':commit,'source_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'package_sha256':hashlib.sha256((out/name).read_bytes()).hexdigest()})
 (out/'sources.json').write_text(json.dumps(records,indent=2)+'\n')
 print(json.dumps(records,indent=2))

if __name__=='__main__':main()
