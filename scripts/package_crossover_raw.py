"""Public bundles for multiple immutable runs, with collision-free manifests."""
import argparse,hashlib,io,json,re,tarfile
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',nargs='+',required=True);ap.add_argument('--output',required=True);ap.add_argument('--name',required=True);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=False);manifest=[];parts=out/'entries';parts.mkdir()
 for source in map(Path,a.sources):
  if not source.is_dir():raise ValueError('Missing source')
  for group in [*sorted(p for p in source.iterdir() if p.is_dir()),source]:
   files=sorted(p for p in group.iterdir() if p.is_file() and p.suffix in ('.gz','.json','.csv','.tsv','.log','.md'))
   if not files:continue
   label=source.name+'/'+(group.name if group!=source else 'contract');path=parts/(label.replace('/','--')+'.tar.gz');entries=[]
   with tarfile.open(path,'w:gz',compresslevel=6) as archive:
    for file in files:
     data=file.read_bytes() if file.suffix=='.gz' else re.sub(r'/[^\s"<>]*thermal-exploration-runs','<run-root>',file.read_text()).encode()
     entry=tarfile.TarInfo(label+'/'+file.name);entry.size=len(data);entry.mtime=0;archive.addfile(entry,io.BytesIO(data));entries.append(dict(name=entry.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
   manifest.append(dict(file=path.name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),entries=entries))
 m=out/'raw-manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n');target=out/(a.name+'.tar')
 with tarfile.open(target,'w') as archive:
  for p in sorted(parts.iterdir()):archive.add(p,arcname=p.name)
  archive.add(m,arcname=m.name)
 print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())),flush=True)
if __name__=='__main__':main()
