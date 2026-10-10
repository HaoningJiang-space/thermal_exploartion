"""All finite D2 execution cases, without treating a streaming probe as RTL."""
import argparse,csv,hashlib,io,json,re,tarfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def clean(s):return re.sub(r'/[^\s"<>]*thermal-exploration-runs','<run-root>',s)
def table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--raw',action='store_true');a=p.parse_args()
    src,out=Path(a.input),Path(a.output);out.mkdir(parents=True,exist_ok=False)
    s=json.loads((src/'summary.json').read_text())
    if s['smoke']:raise ValueError('Smoke is not the full multi-tier experiment')
    for name in ('summary.json','provenance.json'):(out/name).write_text(clean((src/name).read_text()))
    rows=[]
    for c in s['cases']:
        if c['workload']['total_bytes']!=6*2**30 or c['workload']['useful_flops']!=7*2**30:raise ValueError('Full working set/work changed')
        d=c['driver'];rows.append(dict(case=c['name'],task_bytes=c['settings']['task_bytes'],mapping=c['settings']['mapping'],
            uniform_timing=c['settings']['uniform'],ticks=d['ticks'],bytes=d['useful_bytes'],flops=d['useful_flops'],
            tb_s=c['full_workload_tb_s'],tflops=c['effective_tflops'],hb_utilization=c['hb_utilization'],
            buffer_high_water_bytes=d['buffer_high_water_bytes'],consumer_frontier_bytes=c['consumer_frontier_bytes'],
            **{k+'_fraction':d['tile_cycle_partition'].get(k,0)/(16*d['ticks']) for k in ('compute_busy','missing_critical_data','dependency_wait','no_remaining_work')}))
    table(out/'execution-cases.csv',rows)
    by={r['case']:r for r in rows};normal=by['mapped_prefetched']['tflops'];fine=by['fine_streaming_probe']['tflops']
    uniform=by['uniform_fine_probe']['tflops']/by['uniform_prefetched']['tflops']
    ratio=fine/normal;interaction=ratio/uniform
    gate=dict(optimized_over_ordinary_pct=(normal/by['ordinary_striped']['tflops']-1)*100,
        finer_probe_over_optimized_pct=(ratio-1)*100,uniform_finer_probe_gain_pct=(uniform-1)*100,
        tier_interaction_ratio=interaction,criterion='Frozen D2 hardware screen: remaining probe gain >5% and tier interaction >1%; not a universal Research Go criterion',
        status='NO_GO_NEW_EXECUTION_UNIT' if ratio<=1.05 or interaction<=1.01 else 'CONDITIONAL_SIGNAL_REQUIRES_KNOWN_DATAFLOW_AND_COST_CONTROLS',
        research_status='GO_EXECUTION_ATTRIBUTION_AND_DEPENDENCY_WORKLOAD_SELECTION',
        research_scope='Retain the placement/prefetch/consumer attribution method; reassess the next workload, without claiming a novel execution unit',
        policy='Research Go and Hardware Go are separate. Thermal reversal is required only for a claim explicitly about thermal optimality reversal.',
        scope='This fixed6GiB task/dependency model; not a general theorem or a strict optimality upper bound',
        thermal_closure='Not executed in D2. This gate neither proves a thermal mechanism nor closes HB architecture research.',
        frontier_metric='Task-join last packets only. Quantization changes with task size; not globally unique critical-path bytes.')
    (out/'gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    names=['ordinary_striped','prefetched_striped','mapped_prefetched','fine_streaming_probe','uniform_prefetched','uniform_fine_probe']
    labels=['Ordinary\nstriped','Prefetch\nstriped','Mapped\nprefetch','Fine\nprobe','Uniform\nprefetch','Uniform\nfine probe']
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    axes[0].bar(labels,[by[n]['tflops'] for n in names],color=['#71808a','#b39a56','#267b9b','#80adba','#8b93b0','#b0b5ce'])
    axes[0].set(ylabel='Effective compute (TFLOP/s)',title='Same6GiB traffic /7GiFLOP /128TF peak')
    for i,n in enumerate(names):axes[0].text(i,by[n]['tflops']+.15,f"{by[n]['tflops']:.2f}",ha='center',fontsize=8)
    bottom=[0.]*len(names)
    for key,label,color in [('compute_busy','Consumer occupied*','#267b9b'),('missing_critical_data','Missing input','#bf8547'),('dependency_wait','Dependency','#927aaa'),('no_remaining_work','Finished tile','#d6d9dc')]:
        vals=[by[n][key+'_fraction'] for n in names];axes[1].bar(labels,vals,bottom=bottom,label=label,color=color)
        bottom=[x+y for x,y in zip(bottom,vals)]
    axes[1].set(ylabel='Fraction of total tile cycles',ylim=(0,1),title='Consumer states; *includes tick rounding');axes[1].legend(fontsize=8)
    fig.suptitle('D2: data arrivals, task joins and finite prefetch (T0 conditional model)');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('multitier_execution.'+ext),dpi=180)
    plt.close(fig)
    if a.raw:
        manifest=[]
        for c in s['cases']:
            dest=out/(c['name']+'-raw.tar.gz');entries=[]
            with tarfile.open(dest,'w:gz',compresslevel=6) as tar:
                for f in sorted((src/c['name']).iterdir()):
                    if not f.is_file():continue
                    data=clean(f.read_text()).encode();name=c['name']+'/'+f.name
                    info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;tar.addfile(info,io.BytesIO(data))
                    entries.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            manifest.append(dict(file=dest.name,bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),entries=entries))
        (out/'raw-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
