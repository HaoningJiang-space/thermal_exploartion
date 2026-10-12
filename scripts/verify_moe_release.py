"""Anonymous API and complete streamed SHA256 verification of public evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def anonymous(url):
    # Deliberately no token, credential helper or authenticated session.
    return urlopen(Request(url,headers={'User-Agent':'thermal-moe-artifact-check'}),timeout=60)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=json.loads(a.manifest.read_text())
    with anonymous('https://api.github.com/repos/HaoningJiang-space/thermal_exploartion/releases/tags/'+m['release']) as f:r=json.load(f)
    if r['draft']:raise ValueError('Release is not public')
    remote={x['name']:x for x in r['assets']}
    if set(remote)!={x['file'] for x in m['assets']}:raise ValueError('Public asset set mismatch')
    def verify(item):
        published=remote[item['file']]
        if published['size']!=item['bytes'] or published['digest']!='sha256:'+item['sha256'] or published['browser_download_url']!=item['url']:
            raise ValueError('Published asset metadata mismatch')
        h=hashlib.sha256();size=0
        with anonymous(item['url']) as f:
            while data:=f.read(2**20):h.update(data);size+=len(data)
        if h.hexdigest()!=item['sha256'] or size!=item['bytes']:raise ValueError('Anonymous download digest mismatch')
        record=dict(file=item['file'],bytes=size,sha256=h.hexdigest(),status='PASS_ANONYMOUS_COMPLETE_DOWNLOAD_SHA256',url=item['url'])
        print(json.dumps(record),flush=True)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(verify,m['assets']))
    a.output.write_text(json.dumps(dict(release=m['release'],status='PASS_PUBLIC_RELEASE_AND_COMPLETE_ANONYMOUS_DOWNLOADS',authenticated=False,total_bytes=sum(x['bytes'] for x in records),assets=records),indent=2)+'\n')
