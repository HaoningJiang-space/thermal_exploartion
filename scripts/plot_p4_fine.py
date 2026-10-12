"""Scientific figures from audited P4-B evidence only."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);a=ap.parse_args();p=a.results
 rows=json.loads((p/'paired-comparisons.json').read_text());probes=json.loads((p/'counterfactuals.json').read_text());q=json.loads((p/'component-qualification.json').read_text())
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150,'savefig.dpi':180})
 def save(fig,name):
  fig.savefig(p/(name+'.png'),bbox_inches='tight');fig.savefig(p/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(10,4.2),layout='constrained');colors=['#696969','#2874a6','#d68910']
 for ax,b in zip(axes,(8,32)):
  data=sorted([r for r in rows if r['batch']==b],key=lambda r:(r['tp'],r['down_partition']));x=np.arange(len(data))
  for i,(key,label) in enumerate((('macro_us','Macro'),('fine_fixed_us','Fine, fixed order'),('fine_prefetch_us','Fine + prefetch'))):ax.bar(x+(i-1)*.24,[r[key] for r in data],width=.24,color=colors[i],label=label)
  ax.set_xticks(x,[f'TP{r["tp"]}\n{r["down_partition"]}' for r in data]);ax.set_title(f'Original Qwen route: B{b}');ax.set_ylabel('MoE subgraph time (us)');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
 fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,-.09),ncol=3,fontsize=9);fig.suptitle('Resource-granularity sensitivity - full-MoE timing not qualified',fontsize=12);save(fig,'reservation-sensitivity')
 fig,axes=plt.subplots(1,2,figsize=(10,4.2),layout='constrained')
 options=[('none','link_only','Link only'),('none','flight_only','Flight only'),('none','infinite_noc','Link + flight'),('mac_only','baseline','MAC arithmetic')]
 for ax,b in zip(axes,(8,32)):
  x=np.arange(4)
  for i,(grain,label) in enumerate((('macro','Macro'),('fine_fixed','Fine, fixed order'),('fine_prefetch','Fine + prefetch'))):
   data=[next(r for r in probes if r['batch']==b and r['grain']==grain and r['isolation']==iso and r['noc_mode']==noc) for iso,noc,_ in options]
   ax.bar(x+(i-1)*.24,[r['latency_reduction_pct'] for r in data],width=.24,color=colors[i],label=label)
  ax.set_xticks(x,[label.replace(' ','\n',1) for _,_,label in options]);ax.set_title(f'B{b}, TP16, row-down');ax.set_ylabel('Model latency removed (%)');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
 fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,-.09),ncol=3,fontsize=9);fig.suptitle('Separate counterfactuals - gains interact and do not add',fontsize=12);save(fig,'separate-counterfactuals')
 fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained');native=[r for r in q['records'] if r['backend']=='native'];labels=[f'K{r["shape"][1]}, B{r["shape"][2]}\n{r["case"].split("_")[0]}' for r in native]
 vals=[100*r['relative_error'] for r in native];axes[0].bar(np.arange(8),vals,color=['#b03a2e' if abs(v)>10 else '#2874a6' for v in vals]);axes[0].axhspan(-10,10,color='#2874a6',alpha=.08);axes[0].axhline(-10,ls='--',c='#696969');axes[0].axhline(10,ls='--',c='#696969');axes[0].set_xticks(np.arange(8),labels,rotation=40,ha='right',fontsize=8);axes[0].set_ylabel('Graph / native latency - 1 (%)');axes[0].set_title('Absolute target: +/-10%, 5/8 native cases pass')
 vals=[100*r['relative_prediction_error'] for r in q['pairs']];axes[1].bar(np.arange(4),vals,color=['#b03a2e' if abs(v)>5 else '#2874a6' for v in vals]);axes[1].axhspan(-5,5,color='#2874a6',alpha=.08);axes[1].axhline(-5,ls='--',c='#696969');axes[1].axhline(5,ls='--',c='#696969');axes[1].set_xticks(np.arange(4),[f'K{r["k"]}\nB{r["batch"]}' for r in q['pairs']]);axes[1].set_ylabel('Row / column ratio prediction error (%)');axes[1].set_title('Relative target: +/-5%, 1/4 pairs pass')
 for ax in axes:ax.axhline(0,color='black',lw=.7);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
 fig.suptitle('Native component qualification fails - no latency fitting',fontsize=12);save(fig,'component-qualification')
if __name__=='__main__':main()
