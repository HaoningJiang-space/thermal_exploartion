"""Bundle immutable P0-P3 evidence, including exits and explicitly retired controls."""
import argparse,hashlib,io,json,re,tarfile,gzip
from pathlib import Path

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',nargs='+',required=True);ap.add_argument('--output',required=True);ap.add_argument('--name',required=True);ap.add_argument('--retired',action='store_true');a=ap.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False);parts=out/'entries';parts.mkdir();manifest=[]
 for source in map(Path,a.sources):
  if not source.is_dir():raise ValueError('Missing source')
  files=[(p,p.name) for p in sorted(source.rglob('*')) if p.is_file() and p.suffix in ('.gz','.json','.csv','.tsv','.log','.md','.yaml')]
  files=[(p,str(p.relative_to(source))) for p,_ in files]
  for suffix in ('.exit','.log'):
   path=Path(str(source)+suffix)
   if path.exists():files.append((path,'process'+suffix))
  target=parts/(source.name+'.tar.gz');entries=[]
  with tarfile.open(target,'w:gz',compresslevel=6) as archive:
   for file,name in files:
    original=file.read_bytes();data=original
    if file.suffix!='.gz':data=re.sub(rb'/[^\s"<>]*thermal-exploration-runs',b'<run-root>',data)
    entry=tarfile.TarInfo(source.name+'/'+name);entry.size=len(data);entry.mtime=0;archive.addfile(entry,io.BytesIO(data))
    record=dict(name=entry.name,bytes=len(data),sha256=sha(data),original_sha256=sha(original))
    if name.endswith('.gz'):
     try:
      with gzip.GzipFile(fileobj=io.BytesIO(data)) as decoded:
       while decoded.read(2**20):pass
      record['gzip_integrity']='PASS'
     except (EOFError,OSError):
      if not a.retired:raise
      record['gzip_integrity']='TRUNCATED_RETIRED_CONTROL'
    entries.append(record)
  manifest.append(dict(file=target.name,bytes=target.stat().st_size,sha256=sha(target.read_bytes()),validity='RETIRED_MODEL_OR_SCHEDULE_CONTROL' if a.retired else 'FROZEN_EVIDENCE',entries=entries))
 m=out/'raw-manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n');target=out/(a.name+'.tar')
 with tarfile.open(target,'w') as archive:
  for p in sorted(parts.iterdir()):archive.add(p,arcname=p.name)
  archive.add(m,arcname=m.name)
 size=target.stat().st_size
 if size>=2**31:raise ValueError('Split release asset below 2 GiB')
 print(json.dumps(dict(file=target.name,bytes=size,sha256=sha(target.read_bytes()))),flush=True)
if __name__=='__main__':main()
