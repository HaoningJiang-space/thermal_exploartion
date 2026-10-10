"""Remove a provably redundant MoE input broadcast from immutable traces.

The normalized input was already broadcast for router/shared/routed compute.
Router work does not overwrite it; <=64KiB private input storage is reserved.
All phases are sequential, so deletion/time translation is a feasible schedule
transformation, not an ideal bandwidth assumption or new hardware proposal.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess


def transform(events,batch,hidden):
    if batch*hidden*2+batch*(61*4+36)>65536:
        raise ValueError('Input/router metadata cannot stay in reserved private storage')
    shift=0;removed=Counter();by_reason=Counter();ready=set();output=[];removed_ticks=0
    for event in events:
        stage=event['stage'];prefix=stage.rsplit('.',1)[0]
        if stage.endswith('.ffn_input_distribution'):ready.add((event['step'],prefix))
        if stage.endswith('.dispatch'):
            if (event['step'],prefix) not in ready:raise ValueError('No preceding resident input broadcast')
            delta=event['finish_tick']-event['start_tick'];shift+=delta;removed_ticks+=delta
            by_reason[event['critical_reason']]+=delta
            for kinds in event['activity'].values():removed.update(kinds)
            continue
        copied=dict(event,start_tick=event['start_tick']-shift,finish_tick=event['finish_tick']-shift)
        copied['deps']=[output[-1]['id']] if output else []
        output.append(copied)
    if any(a['finish_tick']!=b['start_tick'] for a,b in zip(output,output[1:])):
        raise ValueError('Trace translation introduced gap/overlap')
    return output,removed,by_reason,removed_ticks


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    src=Path(a.source);out=Path(a.output)
    if out.exists():raise ValueError('Preserve immutable input and derived evidence')
    out.mkdir(parents=True);summaries=[]
    for file in ('contract.json','admissions.json'):os.link(src/file,out/file)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    for r in json.loads((src/'summary.json').read_text()):
        if r.get('status')!='PASS_ACCOUNTING':summaries.append(r);continue
        folder=out/r['directory'];folder.mkdir(exist_ok=True)
        source=src/r['directory']/r['events_file']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=r['events_sha256']:raise ValueError('Corrupt parent trace')
        if r['model']!='qwen15_moe':os.link(source,folder/source.name);summaries.append(r);continue
        with gzip.open(source,'rt') as f:events=[json.loads(line) for line in f]
        rewritten,removed,reason,ticks=transform(events,r['batch'],2048)
        if removed['mac'] or removed['dram'] or removed['dram_write']:raise ValueError('Removed useful computation or memory work')
        path=folder/source.name
        with gzip.open(path,'wt') as f:
            for event in rewritten:f.write(json.dumps(event,separators=(',',':'))+'\n')
        activity=Counter(r['activity']);activity.subtract(removed)
        if any(n<0 for n in activity.values()):raise ValueError('Negative remaining work')
        critical=Counter(r['critical_macro_path_ticks']);critical.subtract(reason)
        result=dict(r,time_us=r['time_us']-ticks*.00025,activity=dict(activity),critical_macro_path_ticks=dict(critical),
            events_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),derived_source_commit=sha,
            execution_transform='Known input reuse; remove redundant post-router dispatch broadcast; preserve all DDR/MAC/route/remaining buffer work',
            removed_duplicate_broadcast_ticks=ticks,removed_activity=dict(removed))
        result['tokens_s']=result['tokens']/(result['time_us']*1e-6)
        summaries.append(result)
    (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    parent_commit=json.loads((src/'contract.json').read_text())['source_commit']
    (out/'derivation.json').write_text(json.dumps(dict(source_execution_commit=parent_commit,transform_commit=sha,
        justification='Normalized FFN input already replicated, immutable through router;64KiB reserved input/metadata storage; serial-phase translation',
        scope='Constructive existing-software schedule from complete immutable source trace; no new hardware or ideal NoC'),indent=2)+'\n')
    print('Derived',len(summaries),'complete schedules; source unchanged')


if __name__=='__main__':main()
