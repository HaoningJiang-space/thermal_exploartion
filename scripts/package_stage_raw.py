"""Package immutable sources without run-machine paths; preserve all points.

Nested gzip traces remain byte-identical. Public upload must scan both stored
files and decompressed trace contents; source/transform commits are separate.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--output',required=True);ap.add_argument('--name',required=True);a=ap.parse_args()
    src=Path(a.source);out=Path(a.output);out.mkdir(parents=True,exist_ok=False);raw=out/'entries';raw.mkdir();manifest=[]
    groups=[p for p in sorted(src.iterdir()) if p.is_dir()]+[src]
    for i,group in enumerate(groups):
        files=sorted(p for p in group.iterdir() if p.is_file() and p.suffix in ('.gz','.json','.csv','.tsv','.log'))
        if not files:continue
        label=group.name if group!=src else 'contract'
        path=raw/(label+'.tar.gz');entries=[]
        with tarfile.open(path,'w:gz',compresslevel=6) as archive:
            for file in files:
                if file.suffix=='.gz':data=file.read_bytes()
                else:data=re.sub(r'/[^\s"<>]*thermal-exploration-runs','<run-root>',file.read_text()).encode()
                entry=tarfile.TarInfo(label+'/'+file.name);entry.size=len(data);entry.mtime=0
                archive.addfile(entry,io.BytesIO(data));entries.append(dict(name=entry.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        manifest.append(dict(file=path.name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),entries=entries))
    m=out/'raw-manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n')
    target=out/(a.name+'.tar')
    with tarfile.open(target,'w') as archive:
        for path in sorted(raw.iterdir()):archive.add(path,arcname=path.name)
        archive.add(m,arcname='raw-manifest.json')
    print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())),flush=True)


if __name__=='__main__':main()
