"""Frozen conditional Decode screening; no fabricated device validation."""
import argparse
import csv
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
from .decode_graph import attention,execute,ffn,moe
from .run import revision

WORKLOADS={
    'ffn_b1':('ffn',dict(batch=1)),
    'ffn_b32':('ffn',dict(batch=32)),
    'attention_b1_l8k':('attention',dict(batch=1,context=8192)),
    'attention_b16_l128k':('attention',dict(batch=16,context=131072)),
    'moe_uniform_b32':('moe',dict(batch=32,skew=0.)),
    'moe_zipf_b32':('moe',dict(batch=32,skew=1.2)),
    'moe_zipf_b128':('moe',dict(batch=128,skew=1.2)),
    'moe_zipf_ep_b32':('moe',dict(batch=32,skew=1.2,tensor_parts=1)),
    'moe_zipf_tp16_b32':('moe',dict(batch=32,skew=1.2,tensor_parts=16)),
}
MODES=('baseline','ideal_memory','infinite_noc','ideal_buffer','direct_stream','ideal_collective')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--resume-from');ap.add_argument('--workloads',nargs='+',choices=WORKLOADS,default=list(WORKLOADS));a=ap.parse_args()
    out=Path(a.output)
    if out.exists():raise ValueError('Never overwrite evidence')
    out.mkdir(parents=True)
    (out/'provenance.json').write_text(json.dumps(dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        started_utc=datetime.now(timezone.utc).isoformat(),scope='Conditional packet DAG discovery, not end-to-end Ramulator/real LLM validation'),indent=2)+'\n')
    summaries=[];previous=Path(a.resume_from) if a.resume_from else None
    parent_source=json.loads((previous/'provenance.json').read_text())['source_commit'] if previous else None
    if previous:
        (out/'reuse-provenance.json').write_text(json.dumps(dict(parent_source_commit=parent_source,
            basis='Only execution bookkeeping optimized; immutable parent points and event digests reused; new points have their own source commit'),indent=2)+'\n')
    def reuse(name,variant):
        path=previous/(name+'-'+variant+'.json') if previous else None
        if path is None or not path.exists():return False
        result=json.loads(path.read_text());result['source_commit']=parent_source
        for file in (path,previous/result['events_file'] if 'events_file' in result else None):
            if file is not None:os.link(file,out/file.name)
        summaries.append(result);print(name,variant,'REUSED',result['time_us'],flush=True);return True
    for name in a.workloads:
        kind,settings=WORKLOADS[name];constructor=dict(ffn=ffn,attention=attention,moe=moe)[kind]
        graphs={False:constructor(**settings),True:constructor(**settings,stream=True)}
        for stream,g in graphs.items():
            if sum(n.work for n in g.nodes if n.kind=='dram')!=g.meta['weight_bytes'] or sum(n.work for n in g.nodes if n.kind=='mac')!=g.meta['mac_flops']:
                raise ValueError('Decode byte/FLOP conservation')
            # Known memory FIFO consumption is evaluated as a strong baseline,
            # not labelled a newly proposed HB architecture.
            for mode in (MODES if not stream else (*MODES,'known_fusion')):
                variant=('known_fifo_' if stream else 'sram_')+mode
                if reuse(name,variant):continue
                r=execute(g,mode);events=r.pop('events')
                path=out/(name+'-'+variant+'.jsonl.gz')
                with gzip.open(path,'wt') as f:
                    for node,event in zip(g.nodes,events):
                        f.write(json.dumps(dict(event,deps=node.deps,resource=node.resource,leases=node.leases),separators=(',',':'))+'\n')
                result=dict(workload=name,variant=variant,source_commit=revision(),meta=g.meta,**r,events_file=path.name,events_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                (out/(name+'-'+variant+'.json')).write_text(json.dumps(result,indent=2)+'\n');summaries.append(result)
                print(name,variant,r['time_us'],flush=True)
            # Three bounded, declared sensitivities of the known baseline.
            if stream:
                for sensitivity,ports,links in (('ports_half',.5,1.),('ports_double',2.,1.),('links_half',1.,.5)):
                    if reuse(name,'known_fifo_'+sensitivity):continue
                    r=execute(g,'baseline',sram_scale=ports,link_scale=links);r.pop('events')
                    result=dict(workload=name,variant='known_fifo_'+sensitivity,source_commit=revision(),meta=g.meta,**r)
                    (out/(name+'-'+result['variant']+'.json')).write_text(json.dumps(result,indent=2)+'\n');summaries.append(result)
                    print(name,result['variant'],r['time_us'],flush=True)
    (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    with (out/'summary.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(('workload','variant','time_us','tokens','tokens_per_second','dram_bytes','mac_flops','noc_byte_hops'))
        for r in summaries:writer.writerow((r['workload'],r['variant'],r['time_us'],r['meta']['tokens'],r['meta']['tokens']/r['time_us']*1e6,r['activity']['dram'],r['activity']['mac'],r['activity'].get('link',0)))


if __name__=='__main__':main()
