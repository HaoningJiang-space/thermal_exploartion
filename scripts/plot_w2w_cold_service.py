"""Scientific figures from the independently audited full-size cold gate."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def save(fig, output, name):
    for ext in ('svg','pdf','png'):
        path=output/f'{name}.{ext}'
        fig.savefig(path,dpi=180)
        if ext=='svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')


def plot(receipt, output):
    r = json.loads(receipt.read_text())
    if not r['passed'] or not r['baseline_complete_physical_record_equal']:
        raise ValueError('Independent complete-result audit required')
    output.mkdir(parents=True, exist_ok=True)
    cases = r['cases']
    labels = dict(baseline='Up-local baseline', mc16='MC + paid staging: 16 slots',
        native_minimum_gaps='Optimistic native command gaps', collection_minimum='Collection: one tick (nonphysical)',
        gateway_output_relaxed='Gateway output: 4096 B/ns', native_round_robin='Same-resource native round-robin',
        return_capacity_relaxed='Return reservations: 1024 atoms')
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig, ax = plt.subplots(figsize=(9,4.7), layout='constrained')
    keys = list(cases)
    colors = ['#127878' if k=='native_minimum_gaps' else '#aab6c4' for k in keys]
    values = [cases[k]['makespan_ps']/1e6 for k in keys]
    ax.barh(np.arange(len(keys)), values, color=colors, height=.64)
    ax.set_yticks(np.arange(len(keys)), [labels[k] for k in keys])
    ax.invert_yaxis()
    ax.set_xlabel('Complete cold FFN output latency (µs)')
    ax.set_xlim(0,max(values)*1.30)
    ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    for n,(key,value) in enumerate(zip(keys,values)):
        benefit=cases[key]['completion_reduction_percent']
        ax.text(value+max(values)*.012,n,f'{value:.3f}  ({benefit:+.3f}%)',va='center',fontsize=8)
    gateway_bound=cases['baseline']['payload_work_bounds']['busiest_gateway_payload_ps']/1e6
    ax.axvline(gateway_bound,
               color='#b87d23',linestyle='--',linewidth=1.2,
               label=f'Fixed baseline mapping: {gateway_bound:.3f} µs Gateway payload bound')
    ax.legend(loc='lower right',fontsize=8)
    ax.set_title('Real captured cold token: unchanged full graph, addresses and native bytes')
    fig.suptitle('Diagnostic interventions; increased resources and timing idealizations are explicitly recorded',fontsize=9)
    save(fig,output,'cold-service-diagnostics')
    plt.close(fig)
    phase_labels = ['MC → grouped admission','Grouped → first atom admission',
        'First → last atom admission','Last admission → array callback',
        'Array callback → Gateway payload','Gateway payload → MC release']
    phase_colors = ['#77889b','#4476a8','#63a4c2','#d69955','#b75a60','#695284']
    diagnosis = cases['baseline']['e62_b8_pool']
    phases = list(diagnosis['full_window_phase_fraction'])
    fig,ax = plt.subplots(figsize=(8,2.8),layout='constrained')
    left=0
    for phase,label,color in zip(phases,phase_labels,phase_colors):
        value=100*diagnosis['full_window_phase_fraction'][phase]
        ax.barh([0],[value],left=left,color=color,label=f'{label}: {value:.2f}%')
        if value>8:ax.text(left+value/2,0,f'{value:.2f}%',ha='center',va='center',color='white')
        left+=value
    ax.set_xlim(0,100);ax.set_yticks([])
    ax.set_xlabel('Disjoint MC slot-lifetime share within the full-pool window (%)')
    ax.set_title(f"e62/b8/gate: {diagnosis['mc_full_wall_ps']/1e6:.3f} µs full-pool wall time × {diagnosis['capacity']} finite slots")
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.3),ncol=2,fontsize=8)
    fig.suptitle('Ownership accounting; these percentages are not additive stalls or recoverable output latency',fontsize=9)
    save(fig,output,'mc-ownership-phases')
    plt.close(fig)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();plot(a.receipt,a.output)
