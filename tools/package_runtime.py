"""Save a reviewed local Docker image for private AWS deployment; no upload."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--image',default='remedigenius-ce:0.1.0rc9')
p.add_argument('--output',default='dist/rgce-runtime.tar.gz')
a=p.parse_args()
path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
with path.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=1) as output:
    process=subprocess.Popen(['docker','save',a.image],stdout=subprocess.PIPE)
    shutil.copyfileobj(process.stdout,output)
    if process.wait(): raise SystemExit('Docker image export failed')
sha=hashlib.sha256()
with path.open('rb') as source:
    for chunk in iter(lambda:source.read(1024*1024),b''):sha.update(chunk)
print(json.dumps({'archive':str(path.resolve()),'sha256':sha.hexdigest(),'image':a.image}))
