"""Archive all prespecified D1 points and reproducible raw command evidence."""
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
    for name in ('summary.json','profile.json','provenance.json'):(out/name).write_text(clean((src/name).read_text()))
    rows=[dict(case=r['case'],energy=r['energy_mode'],workload=r['workload'],thermal=r['thermal_model'],
        tflops=r['tflops'],logic_w=r['logic_power_w'],dram_w=r['dram_power_w'],logic_c=r['logic_peak_c'],dram_c=r['dram_peak_c'],
        logic_dynamic_pj_B=(r['energy_contract'].get('evidence') or {}).get('logic_dynamic_pj_per_useful_byte','fixed'),
        dram_dynamic_pj_B=(r['energy_contract'].get('evidence') or {}).get('dram_dynamic_pj_per_useful_byte','fixed'),
        area_mm2=r['active_area_mm2'],constraint_violation=r['original_constraint_max_violation']) for r in s['results']]
    table(out/'all-points.csv',rows)
    commands=[dict(case=c['name'],tb_s=c['steady']['useful_tb_s'],requests=c['work']['request_count'],
        bytes=c['work']['read_bytes'],command_count=c['commands']['commands'],ACT=c['commands']['counts'].get('ACT',0),
        PRE_rows=c['audit']['PREab_rows']+c['commands']['counts'].get('PREpb',0),
        overlap_ACTs=c['audit']['overlapping_ACTs'],tRAS_ns=c['timing_ns']['RAS'],tRC_ns=c['timing_ns']['RC']) for c in s['cases']]
    table(out/'command-cases.csv',commands)
    full=[c for c in commands if not c['case'].endswith('partial_row')];base=full[0]['tb_s'];oracle=full[-1]['tb_s']
    gate=dict(status='NO_GO_NEW_ROW_CYCLE_HARDWARE',scope='Fixed K32 full-row assumed internal model',
        overlap_restoration_ns=30,overlap_gain_pct=(full[3]['tb_s']/base-1)*100,
        overlap_fraction_of_oracle_increment=(full[3]['tb_s']-base)/(oracle-base),
        oracle_residual_over_overlap_pct=(oracle/full[3]['tb_s']-1)*100,
        oracle_residual_over_margin20_pct=(oracle/full[2]['tb_s']-1)*100,
        caution='Mechanism proxies, not complete SALP or reliability-qualified Mono3D timing; no independent command-energy calibration')
    (out/'gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.2));labels=['Baseline','Margin10%','Margin20%','SA overlap','Extreme oracle']
    colors=['#6c7983','#cda45a','#ae873e','#227c9d','#ad5562']
    axes[0].bar(labels,[c['tb_s'] for c in full],color=colors);axes[0].set(ylim=(0,32),ylabel='Useful steady service (TB/s)',title='Same K32 / capacity / HB / compute')
    axes[0].tick_params(axis='x',rotation=20)
    for i,c in enumerate(full):axes[0].text(i,c['tb_s']+.3,f"{c['tb_s']:.2f}",ha='center',fontsize=9)
    for mode,style in [('timing_only','o-'),('trace_driven','s--')]:
        data=[next(r for r in rows if r['case']==c['case'] and r['energy']==mode and r['thermal']=='T2' and r['workload']=='decode_gemv') for c in full]
        axes[1].plot(labels,[r['tflops'] for r in data],style,label=mode)
    axes[1].set(ylim=(25,31),ylabel='T2 GEMV (TFLOP/s)',title='Assumed energy; both interfaces retained');axes[1].tick_params(axis='x',rotation=20);axes[1].legend(fontsize=8);axes[1].grid(alpha=.2)
    fig.suptitle('D1: known-mechanism proxies explain the row-cycle signal');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('known_mechanisms.'+ext),dpi=180)
    plt.close(fig)
    if a.raw:
        manifest=[]
        for c in s['cases']:
            dest=out/(c['name']+'-raw.tar.gz');entries=[]
            with tarfile.open(dest,'w:gz',compresslevel=6) as tar:
                for f in sorted((src/c['name']).iterdir()):
                    if not f.is_file() or f.name=='requests.json':continue
                    data=clean(f.read_text()).encode();name=c['name']+'/'+f.name
                    info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;tar.addfile(info,io.BytesIO(data))
                    entries.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            manifest.append(dict(file=dest.name,bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),entries=entries))
        (out/'raw-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
