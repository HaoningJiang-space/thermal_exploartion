"""Publish all finite organization points and compact, complete command evidence."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from thermal_exploration.parameter_identifiability import report


def clean(s):return re.sub(r'/[^\s"<>]*thermal-exploration-runs','<run-root>',s)


def csv_table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def metrics(r):
    mixed='phases' in r
    if mixed:
        peaks=np.asarray([p['spatial_steady_temperature_c'] for p in r['phases']])
        power=r['average_power_w'];bandwidth=sum(p['used_bandwidth_tb_s']*p['duration_s'] for p in r['phases'])/r['cycle_time_s']
    else:peaks=np.asarray([r['temperature_c']]);power=r['power_w'];bandwidth=r['used_bandwidth_tb_s']
    c=r['organization_cost']
    return dict(scenario=r['scenario'],allocation=r['allocation'],workload=r['workload'],thermal=r['thermal_model'],
        K=r['paths']*16,banks_per_service_unit=16//r['paths'],useful_tflops=r['tflops'],
        internal_service_tb_s=r.get('service_tb_s','oracle'),used_bandwidth_tb_s=bandwidth,
        compute_peak_tflops=c['compute_peak_tflops'],compute_area_mm2=c['compute_area_mm2'],
        periphery_area_mm2=14.8+c['additional_periphery_mm2'],active_area_mm2=c['active_area_mm2'],
        logic_power_w=sum(power[:16]),dram_power_w=sum(power[16:]),
        spatial_logic_peak_c=float(peaks[:,:16].max()),spatial_dram_peak_c=float(peaks[:,16:].max()),
        constraint_violation=r['original_constraint_max_violation'],
        scope='phase-steady shared layout' if mixed else 'single steady divisible-work LP')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--raw-input',help='Original command directory when numerical controls reuse its commands')
    a=ap.parse_args();src=Path(a.input);out=Path(a.output)
    if out.exists():raise SystemExit('Choose a new archive directory')
    out.mkdir(parents=True)
    s=json.loads((src/'summary.json').read_text());rows=s['results'];m=[metrics(r) for r in rows]
    for r in m:
        if r['thermal']=='T2' and max(r['spatial_logic_peak_c'],r['spatial_dram_peak_c'])>85.0001:
            raise ValueError('Sustained T2 point exceeds temperature limit')
    csv_table(out/'all-design-points.csv',m)
    for name in ('summary.json','profile.json','provenance.json'):(out/name).write_text(clean((src/name).read_text()))
    evidence=report(json.loads((src/'profile.json').read_text()))
    (out/'critical-parameters.json').write_text(json.dumps(evidence,indent=2)+'\n')
    csv_table(out/'critical-ACT-bounds.csv',evidence['critical_ACT_bounds'])
    cmd=[]
    for c in s['command_cases']:
        w=c['steady_window'];counts=c['command_validation']['counts']
        cmd.append(dict(trace=c['name'],K=c['paths']*16,hb_tb_s=c['hb_tb_s'],kind=c['trace_kind'],
            multi_refresh=c['long_multi_refresh_trace'],ideal_only=c['ideal_row_retention'],
            requests=c['work']['request_count'],bytes=c['work']['read_bytes'],flops=c['work']['useful_flops'],
            full_tb_s=c['full_execution_tb_s'],window_tb_s=w['useful_tb_s'],window_ns=w['duration_ns'],
            start_tick=w['start_tick'],end_tick=w['end_tick'],ACT=counts.get('ACT',0),
            PRE=counts.get('PREpb',0)+counts.get('PREab',0),RD=counts.get('RD',0),REF=counts.get('REFab',0),
            verified_commands=c['command_validation']['commands']))
    csv_table(out/'command-metrics.csv',cmd)
    winners=[]
    for scenario in sorted({r['scenario'] for r in rows}):
        for allocation in ('shared_area','fixed_compute'):
            for work in sorted({r['workload'] for r in rows if r['allocation']==allocation}):
                for thermal in ('T0','T1_layer','T2'):
                    group=[r for r in rows if (r['scenario'],r['allocation'],r['workload'],r['thermal_model'])==(scenario,allocation,work,thermal)]
                    best=max(group,key=lambda r:r['tflops']);v=best['tflops']
                    winners.append(dict(scenario=scenario,allocation=allocation,workload=work,thermal=thermal,
                        best_K=best['paths']*16,best_tflops=v,within_one_percent_K=';'.join(str(r['paths']*16) for r in group if r['tflops']>=v*.99)))
    csv_table(out/'optimal-organizations.csv',winners)
    csv_table(out/'ideal-row-retention.csv',[metrics(r) for r in s['ideal_row_retention']])
    # The requested granularity curves: all three thermal controls, same area allocation.
    works=('decode_gemv','prefill_gemm','mixed_shared_1prefill_32decode')
    titles=('Batch-1 GEMV','Batch-32 GEMM','Shared layout: 1 Prefill +32 Decode')
    fig,axes=plt.subplots(1,3,figsize=(13,4.5))
    colors={'T0':'#687580','T1_layer':'#d78c24','T2':'#186b9c'}
    for ax,work,title in zip(axes,works,titles):
        for thermal in colors:
            group=sorted([r for r in m if (r['scenario'],r['allocation'],r['workload'],r['thermal'])==('default','shared_area',work,thermal)],key=lambda r:r['K'])
            ax.plot([r['K'] for r in group],[r['useful_tflops'] for r in group],marker='o',label=thermal,color=colors[thermal],linestyle={'T0':'--','T1_layer':':','T2':'-'}[thermal])
        ax.set(title=title,xlabel='Independent service units K',xticks=[16,32,64,128],ylim=(0,None));ax.grid(alpha=.2)
    axes[0].set_ylabel('Effective throughput (TFLOP/s)');axes[2].legend()
    fig.suptitle('Fixed 121 mm² budget: paid Peripheral–Compute exchange (conditional model)')
    fig.tight_layout();fig.savefig(out/'service_granularity.png',dpi=180);fig.savefig(out/'service_granularity.pdf');plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13,4.5))
    cmap=plt.get_cmap('viridis');norm=plt.Normalize(14.8,66.6)
    for ax,work,title in zip(axes,works,titles):
        for scenario,marker in (('default','o'),('cooling_weak','s')):
            group=sorted([r for r in m if (r['scenario'],r['allocation'],r['workload'],r['thermal'])==(scenario,'shared_area',work,'T2')],key=lambda r:r['K'])
            # Small common x jitter only for coincident rates would misstate
            # bandwidth. Keep identical x; annotate K and distinguish markers.
            ax.plot([r['internal_service_tb_s'] for r in group],[r['useful_tflops'] for r in group],alpha=.3,color='black')
            scatter=ax.scatter([r['internal_service_tb_s'] for r in group],[r['useful_tflops'] for r in group],
                c=[r['periphery_area_mm2'] for r in group],norm=norm,cmap=cmap,marker=marker,s=55,label=scenario)
            for r in group:ax.annotate(str(r['K']),(r['internal_service_tb_s'],r['useful_tflops']),xytext=(4,4),textcoords='offset points',fontsize=8)
        ax.set(title=title,xlabel='Multi-refresh internal service (TB/s)',ylim=(0,None));ax.grid(alpha=.2)
    axes[0].set_ylabel('T2 effective throughput (TFLOP/s)');axes[2].legend(fontsize=8,loc='lower left')
    fig.subplots_adjust(left=.06,right=.87,top=.83,bottom=.18,wspace=.32)
    ca=fig.add_axes([.9,.2,.016,.55]);fig.colorbar(scatter,cax=ca,label='Peripheral area (mm²)')
    fig.suptitle('Bandwidth–Area–Thermal tradeoff; labels =K\nTemperature-constrained LP, not chip measurements')
    fig.savefig(out/'bandwidth_area_thermal.png',dpi=180);fig.savefig(out/'bandwidth_area_thermal.pdf');plt.close(fig)
    # Full TSV requests, events, both command traces, cycles and configs, per
    # case. Omit redundant verbose request JSON and native binaries. Every
    # request field remains in TSV plus the frozen mapper and model source.
    archive_manifest=[]
    for case in sorted(p for p in Path(a.raw_input or src).iterdir() if p.is_dir()):
        target=out/(case.name+'-raw.tar.gz');entries=[]
        with tarfile.open(target,'w:gz',compresslevel=6) as tar:
            for f in sorted(case.iterdir()):
                if not f.is_file() or f.name=='requests.json':continue
                data=clean(f.read_text()).encode();name=case.name+'/'+f.name
                info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;tar.addfile(info,io.BytesIO(data))
                entries.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        archive_manifest.append(dict(archive=target.name,entries=entries))
    (out/'raw-manifest.json').write_text(json.dumps(archive_manifest,indent=2)+'\n')
    (out/'artifact-sha256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()},indent=2)+'\n')
    print(json.dumps(dict(points=len(m),command_cases=len(cmd),archives=len(archive_manifest),winners=len(winners))),flush=True)


if __name__=='__main__':main()
