"""Static paired research figures, no synthetic/interpolated performance."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

LABELS={('broadcast_all','drain_all'):'Batch / drain',('destination_only','drain_all'):'Token / drain',('decoupled','drain_all'):'Decoupled / drain',('broadcast_all','row_ready'):'Batch / row-ready64',('destination_only','row_ready'):'Token / row-ready64',('decoupled','row_ready'):'Decoupled / row-ready64',('broadcast_all','row_ready_128'):'Batch / row-ready128'}
COLORS=['#496480','#21918c','#c28e5c','#829bc7','#8cc9a3','#dfbb92','#985b94']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);a=ap.parse_args();root=a.results
 points=json.loads((root/'paired-comparisons.json').read_text());raw=json.loads((root/'all-points.json').read_text())
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
 variants=list(LABELS);combos=[(4,'column'),(4,'row'),(16,'column'),(16,'row')]
 def save(fig,name):
  fig.savefig(root/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(root/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(13,4.9),sharey=False)
 for ax,b in zip(axes,(8,32)):
  for j,(dispatch,reduction) in enumerate(variants):
   rows=[next(r for r in points if r['batch']==b and r['tp']==tp and r['down_partition']==down and r['role']=='primary' and r['dispatch']==dispatch and r['reduction']==reduction) for tp,down in combos]
   ax.bar(np.arange(4)+(j-3)*.105,[r['time_us'] for r in rows],width=.10,label=LABELS[dispatch,reduction],color=COLORS[j])
  ax.set_xticks(np.arange(4),['TP4\ncolumn','TP4\nrow','TP16\ncolumn','TP16\nrow']);ax.set_title(f'B{b}: actual step 0 / layer 0');ax.set_ylabel('MoE subgraph latency (us)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
 fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3,bbox_to_anchor=(.5,-.01));fig.subplots_adjust(bottom=.24,wspace=.27);save(fig,'paired-latency')
 fig,axes=plt.subplots(1,2,figsize=(12,4.4),sharey=True)
 for ax,b in zip(axes,(8,32)):
  for j,(dispatch,reduction) in enumerate(variants):
   rows=[next(r for r in points if r['batch']==b and r['tp']==16 and r['down_partition']=='row' and (r['step'],r['layer'])==case and r['dispatch']==dispatch and r['reduction']==reduction) for case in ((0,0),(32,7),(127,23))]
   ax.bar(np.arange(3)+(j-3)*.105,[r['noc_speedup_pct'] for r in rows],width=.10,color=COLORS[j],label=LABELS[dispatch,reduction])
  ax.set_xticks(np.arange(3),['s0/l0\nprimary','s32/l7\nholdout','s127/l23\nholdout']);ax.set_title(f'B{b}: TP16, row-down');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
 axes[0].set_ylabel('Infinite-NoC speedup potential (%)');fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3,bbox_to_anchor=(.5,-.03));fig.subplots_adjust(bottom=.26);save(fig,'noc-diagnostic')
 fig,axes=plt.subplots(1,2,figsize=(11,4.3))
 for ax,b in zip(axes,(8,32)):
  for j,dispatch in enumerate(('broadcast_all','destination_only','decoupled')):
   rows=[next(r for r in points if r['batch']==b and r['tp']==tp and r['down_partition']==down and r['role']=='primary' and r['dispatch']==dispatch and r['reduction']=='drain_all') for tp,down in combos]
   ax.bar(np.arange(4)+(j-1)*.24,[r['dispatch_byte_hops']/2**20 for r in rows],width=.23,color=COLORS[j],label=LABELS[dispatch,'drain_all'].split(' /')[0])
  ax.set_xticks(np.arange(4),['TP4\ncolumn','TP4\nrow','TP16\ncolumn','TP16\nrow']);ax.set_title(f'B{b}: step 0 / layer 0');ax.set_ylabel('Input NoC traffic (MiB-hop)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
 fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3);fig.subplots_adjust(bottom=.2);save(fig,'paid-dispatch')
 fig,ax=plt.subplots(figsize=(10.5,3.8))
 for i,reduction in enumerate(('drain_all','row_ready','row_ready_128')):
  rec=next(r for r in raw if r['batch']==32 and r['tp']==16 and r['down_partition']=='row' and r['step']==0 and r['dispatch_scheme']=='broadcast_all' and r['reduction_scheme']==reduction and r['isolation']=='none');ev=rec['event_replay']
  ax.barh(i+.12,ev['last_local_expert_us'],height=.22,color=COLORS[0],label='Local-expert completion window' if i==0 else None)
  ax.barh(i-.12,ev['last_combine_us']-ev['first_combine_us'],left=ev['first_combine_us'],height=.22,color=COLORS[1],label='Combine window (includes waits)' if i==0 else None)
  ax.annotate(f"{rec['time_us']:.3f} us",(rec['time_us'],i),xytext=(6,0),textcoords='offset points',va='center')
 ax.set_yticks([0,1,2],['Drain-all','Row-ready64','Row-ready128']);ax.set_xlim(0,78);ax.set_xlabel('Time (us)');ax.set_title('B32 / TP16 / row-down: combine and local-expert windows');ax.grid(axis='x',alpha=.2)
 fig.legend(*ax.get_legend_handles_labels(),loc='lower center',ncol=2);fig.subplots_adjust(bottom=.25);save(fig,'row-ready-overlap')

if __name__=='__main__':main()
