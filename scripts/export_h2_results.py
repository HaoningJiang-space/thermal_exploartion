"""Archive every successful and failed frozen H2 case, with sanitized raw data."""
import argparse,csv,hashlib,io,json,re,tarfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);raw=out/'raw';raw.mkdir();points=[];manifest=[]
    for run in map(Path,a.runs):
        provenance=json.loads((run/'provenance.json').read_text())
        for case in sorted(p for p in run.iterdir() if p.is_dir() and (p/'contract.json').exists()):
            if (case/'result.json').exists():
                point=json.loads((case/'result.json').read_text());point.update(name=case.name,status='PASS',source_commit=provenance['source_commit'])
            else:
                point=dict(name=case.name,status='FAILED_INCOMPLETE',source_commit=provenance['source_commit'],
                    reason=(case/'execution.log').read_text().strip(),scope='2,000,000 tick limit; not a finite latency or a proved universal deadlock')
            points.append(point);entries=[];path=raw/(case.name+'.tar.gz')
            with tarfile.open(path,'w:gz',compresslevel=6) as archive:
                for file in sorted(case.iterdir()):
                    if not file.is_file():continue
                    # CSV/TSV are numerical, JSON/log may contain run locations.
                    if file.suffix in ('.json','.log'):
                        data=re.sub(r'/[^\s"<>]*thermal-exploration-runs','<run-root>',file.read_text()).encode()
                    else:data=file.read_bytes()
                    info=tarfile.TarInfo(case.name+'/'+file.name);info.size=len(data);info.mtime=0
                    archive.addfile(info,io.BytesIO(data));entries.append(dict(name=info.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            manifest.append(dict(file=path.name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),entries=entries))
    (out/'all-points.json').write_text(json.dumps(points,indent=2)+'\n');(out/'raw-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    valid=[p for p in points if p['status']=='PASS'];keys=('name','source_commit','time_us','effective_tflops','mac_utilization','useful_dram_tb_s','physical_dram_tb_s')
    with (out/'all-points.csv').open('w') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:p[k] for k in keys} for p in valid)
    fig,axes=plt.subplots(1,2,figsize=(11,4.2))
    select=['row_blocked_k','column_blocked_m','2d_blocked_k','column_reduce64','column64_ideal_transport','column64_ideal_memory','column64_ideal_buffer']
    index={p['name']:p for p in valid};labels=['Row','Column','2D','Column64','Ideal NoC','Ideal memory','Ideal buffer']
    vals=[index[k]['effective_tflops'] for k in select]
    axes[0].bar(labels,vals,color=['#7185a5']*3+['#247c7b']+['#d7a04a']*3);axes[0].axhline(128,ls='--',color='black',lw=1);axes[0].set_ylabel('Effective TFLOP/s');axes[0].tick_params(axis='x',rotation=35);axes[0].set_ylim(0,140)
    baseline=index['column_reduce64'];states=baseline['driver']['mac_states'];total=sum(states.values())
    axes[1].barh(list(states),[100*v/total for v in states.values()],color='#247c7b');axes[1].set_xlabel('Tile-time (%)');axes[1].set_title('Column64: mutually exclusive MAC states')
    fig.suptitle('H2-A: causal execution under assumed finite resources');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('execution.'+ext),dpi=180)
    with tarfile.open(out/'h2-raw.tar','w') as bundle:
        for path in sorted(raw.iterdir()):bundle.add(path,arcname=path.name)
        bundle.add(out/'raw-manifest.json',arcname='raw-manifest.json')
    print(json.dumps(dict(successful=len(valid),failed=len(points)-len(valid),bundle_bytes=(out/'h2-raw.tar').stat().st_size)),flush=True)


if __name__=='__main__':main()
