"""Static export figures, explicit paired grids and mixed-service attribution."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def save(fig,out,name):
 fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=180);fig.savefig(out/(name+'.pdf'));plt.close(fig)
def geomean(values):return float(np.exp(np.mean(np.log(values)))) if values else np.nan
def supplements(out,points,iso):
 valid=[r for r in points if r['status']=='PASS_ACCOUNTING'];fig,axes=plt.subplots(1,2,figsize=(10,4))
 for ax,b in zip(axes,(8,32)):
  for offset,partition,color in ((-.18,'column','#789caf'),(.18,'row','#287d65')):
   values=[]
   for tp in ('1','4','16','hybrid'):
    choices=[]
    for schedule,order in (('barrier','static'),('overlap','static'),('overlap','dynamic')):
     rows=[r['time_us'] for r in valid if r['experiment'].startswith('expert-p2') and r['batch']==b and r.get('tp')==tp and r.get('baseline')=='B3_3d_placement' and r['combine_scheme']=='fused' and r['down_partition']==partition and r['schedule']==schedule and r['order']==order and r['step'] in (0,127) and r['layer'] in (0,15,23)]
     if len(rows)==6:choices.append(geomean(rows))
    values.append(min(choices,default=np.nan))
   ax.bar(np.arange(4)+offset,values,width=.35,color=color,label=partition+' down')
  ax.set_xticks(range(4),['EP','TP4','TP16','Hybrid']);ax.set(title=f'B{b}, matched six cases',ylabel='MoE-subgraph geometric mean (us)');ax.legend(fontsize=8)
 fig.suptitle('Static row-down weights, same capacity/bytes; paid hidden allgather',fontsize=11);save(fig,out,'frozen-down-layout')
 fig,axes=plt.subplots(1,2,figsize=(12,4.5));names=['bank_cycle','uniform_fast_tier','native_only','hb_only','ingress_only','hb_ingress_only','mac_only','infinite_noc','ideal_memory']
 for ax,b in zip(axes,(8,32)):
  for tp in ('1','4','16','hybrid'):
   values=[next((100*(r['speedup']-1) for r in iso if r['batch']==b and r['tp']==tp and r['combine_scheme']=='fused' and r['down_partition']=='row' and r['isolation']==name and r.get('schedule')=='barrier' and r.get('order')=='static'),np.nan) for name in names]
   ax.plot(range(len(names)),values,marker='o',lw=1,label=tp)
  ax.set_xticks(range(len(names)),['Bank\ncap','Fast\ntier','DRAM','HB','FIFO\nin','HB+FIFO','MAC','NoC','Memory'],rotation=35,ha='right',fontsize=9);ax.set(title=f'B{b}: row-down, barrier/static',ylabel='Timing-only oracle gain (%)');ax.legend(title='TP',fontsize=8)
 fig.suptitle('P3: strongest measured static layout, step0/layer0; gains overlap',fontsize=11);save(fig,out,'physical-isolation-row')
 fig,axes=plt.subplots(2,2,figsize=(10,7))
 for i,family in enumerate(('topic_short','code_math')):
  for j,partition in enumerate(('column','row')):
   ax=axes[i,j]
   for dtype,color,style in (('FP32','#2d6d9e','-'),('BF16','#c25b32','--')):
    values=[]
    for tp in ('1','4','16','hybrid'):
     rows=[r['time_us'] for r in valid if r['experiment'].startswith(f'expert-promptfused-{family}-{dtype}-') and r.get('tp')==tp and r['down_partition']==partition and r['schedule']=='barrier' and r['order']=='static']
     values.append(geomean(rows) if len(rows)==6 else np.nan)
    ax.plot(range(4),values,style,marker='o',color=color,label=dtype)
   ax.set_xticks(range(4),['EP','TP4','TP16','Hybrid']);ax.set(title=f'{family}: {partition} down',ylabel='MoE-subgraph geometric mean (us)');ax.legend(fontsize=8)
 fig.suptitle('Paired teacher-forced B4/C128: fixed barrier/static policy, separate training prior',fontsize=11);save(fig,out,'prompt-precision')
 distribution=json.loads((out/'routing-distributions.json').read_text())['distribution'];fig,axes=plt.subplots(1,2,figsize=(10,4))
 for ax,b in zip(axes,(8,32)):
  histogram=distribution[str(b)]['effective_expert_batch_histogram'];x=sorted(map(int,histogram));y=np.array([histogram[str(k)] for k in x],dtype=float);y=y/y.sum()*100
  ax.bar(x,y,color='#2d6d9e');ax.set(title=f'B{b}: real expert reuse distribution',xlabel='Tokens per active expert',ylabel='Active-expert occurrences (%)')
 fig.suptitle('All 128 steps / 24 layers; controlled FP32 capture, not a production trace',fontsize=11);save(fig,out,'routing-reuse')
 records=json.loads((out/'routing-records.json').read_text());fig,ax=plt.subplots(figsize=(8,4))
 for b,color in ((8,'#2d6d9e'),(32,'#c25b32')):
  values=[8*b/(r['active_experts']+4) for r in records if r['batch']==b]
  ax.hist(values,bins=20,weights=np.ones(len(values))*100/len(values),alpha=.55,color=color,label=f'B{b}')
 ax.axvline(128/26.599,c='0.2',ls='--',label='128 TFLOP/s /26.599 TB/s')
 ax.set(xlabel='Linear FLOPs / active BF16 weight byte',ylabel='Captured layer/step cases (%)',title='Weight-reuse regimes include the always-active shared expert');ax.legend(fontsize=8)
 fig.suptitle('Ideal weight-only balance; excludes activation/KV traffic and execution dependencies',fontsize=10);save(fig,out,'reuse-crossover')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',required=True);a=ap.parse_args();out=Path(a.results)
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 f=json.loads((out/'cross-fidelity.json').read_text());fig,ax=plt.subplots(1,2,figsize=(10,4))
 for peak,color in ((128,'#276b9e'),(152,'#c25b32')):
  rows=[r for r in f['absolute'] if r['peak']==peak];ax[0].scatter([r['native_us'] for r in rows],[r['matched_fluid_us'] for r in rows],label=f'{peak} TFLOP/s',c=color)
 x=np.linspace(0,8.3,100);ax[0].plot(x,x,c='0.5',lw=1);ax[0].fill_between(x,.9*x,1.1*x,color='0.5',alpha=.12,label='10% target')
 ax[0].set(xlabel='Ramulator frontend (us)',ylabel='Matched fluid frontend (us)',title='Selected tensors: shared input/MAC/port rules');ax[0].legend(fontsize=8)
 rs=f['speedup'];ax[1].bar(np.arange(len(rs)),[(r['native_speedup']-1)*100 for r in rs],width=.55,label='Native 128 to 152')
 ax[1].scatter(np.arange(len(rs)),[(r['matched_fluid_speedup']-1)*100 for r in rs],color='#c25b32',marker='x',label='Matched fluid')
 ax[1].set_xticks(np.arange(len(rs)),[('QKV' if r['shape'][0]==6144 else 'Down')+f'{r["shape"][2]} / '+('C' if r['case'].startswith('column') else 'Rm' if r['case'].endswith('_m') else 'Rk') for r in rs],rotation=40)
 ax[1].set(xlabel='Batch / partition-loop',ylabel='Throughput gain (%)',title='Same frontend isolates memory abstraction');ax[1].legend(fontsize=8)
 fig.suptitle('P0: not independent frontend or complete H3 validation',fontsize=11);save(fig,out,'profile-fidelity')
 rows=json.loads((out/'workspace-repair.json').read_text());fig,axes=plt.subplots(1,2,figsize=(10,4));x=np.arange(4)
 for index,base in enumerate(('B2_stream_fusion','B3_3d_placement')):
  r=[v for v in rows if v['baseline']==base];ys=[v.get('tokens_s') or 0 for v in r];axes[index].bar(x,ys,color=['#276b9e','#76a4c3','#c9c9c9','#c25b32'])
  for i,v in enumerate(r):
   if not v.get('tokens_s'):axes[index].text(i,450,'Schedule\ninfeasible',ha='center',rotation=90,color='#a53030')
  axes[index].set_xticks(x,['128/36\ncohort','128/36\nrows','152/18\ncohort','152/18\nrows']);axes[index].set_ylim(0,15500);axes[index].set(title=base.replace('_',' '),ylabel='Conditional full-model tokens/s')
 fig.suptitle('P1: Qwen B32 / C512, all 128 steps; same weights and MAC work',fontsize=11);save(fig,out,'workspace-repair')
 if not (out/'all-points.json').exists():return
 points=json.loads((out/'all-points.json').read_text());valid=[r for r in points if r['status']=='PASS_ACCOUNTING']
 summaries=json.loads((out/'conventional-baselines.json').read_text());fig,axes=plt.subplots(1,2,figsize=(10,4))
 for ax,b in zip(axes,(8,32)):
  for offset,combine,col in ((-.18,'eager','#7b98ab'),(.18,'fused','#2d6d9e')):
   ys=[]
   for tp in ('1','4','16','hybrid'):
    choices=[r for r in summaries if r['batch']==b and r['tp']==tp and r['combine_scheme']==combine and r['down_partition']=='column' and r['samples']==20]
    ys.append(min((r['geomean_us'] for r in choices),default=np.nan))
   ax.bar(np.arange(4)+offset,ys,width=.35,color=col,label=combine)
  ax.set_xticks(np.arange(4),['EP','TP4','TP16','Hybrid']);ax.set(title=f'B{b}: fixed-policy geometric mean',ylabel='MoE-subgraph latency (us)');ax.legend(fontsize=8)
 fig.suptitle('P2: best measured conventional placement/schedule; 20 matched layer-step cases',fontsize=11);save(fig,out,'conventional-execution')
 iso=json.loads((out/'physical-isolation.json').read_text());fig,axes=plt.subplots(1,2,figsize=(12,4.5));names=['bank_cycle','uniform_fast_tier','native_only','hb_only','ingress_only','hb_ingress_only','mac_only','infinite_noc','ideal_memory']
 for ax,b in zip(axes,(8,32)):
  for index,tp in enumerate(('1','4','16','hybrid')):
   values=[next((100*(r['speedup']-1) for r in iso if r['batch']==b and r['tp']==tp and r['combine_scheme']=='fused' and r['down_partition']=='column' and r['isolation']==name and r.get('schedule')=='barrier' and r.get('order')=='static'),np.nan) for name in names]
   ax.plot(range(len(names)),values,marker='o',lw=1,label=tp)
  ax.set_xticks(range(len(names)),['Bank\ncap','Fast\ntier','DRAM','HB','FIFO\nin','HB+FIFO','MAC','NoC','Memory'],rotation=35,ha='right',fontsize=9);ax.set(title=f'B{b}, barrier/static, step0 / layer0',ylabel='Timing-only oracle gain (%)');ax.legend(title='TP',fontsize=8)
 fig.suptitle('P3: nonadditive probes; Bank/Tier are bounds, not calibrated Mono3D commands',fontsize=11);save(fig,out,'physical-isolation')
 fig,axes=plt.subplots(1,2,figsize=(10,4));categories=['Joint memory/MAC','NoC + flight','SRAM + vector','Other/gaps'];colors=['#2d6d9e','#d67d3d','#74a791','#a5a5a5']
 for ax,b in zip(axes,(8,32)):
  for i,tp in enumerate(('1','4','16','hybrid')):
   r=next((x for x in valid if x['experiment'].startswith('expert-p3strong') and x['down_partition']=='row' and x['batch']==b and x['label'].split('-tp')[1].split('-')[0]==tp and x['isolation']=='none'),None)
   if not r:continue
   kinds=r['critical_kind_ticks'];joint=sum(kinds.get(k,0) for k in ('mac','dram','hb'))
   noc=sum(kinds.get(k,0) for k in ('link','join'));local=sum(kinds.get(k,0) for k in ('sram_read','sram_write','vector'))
   values=np.array([joint,noc,local,r['critical_gap_ticks']])*.00025;bottom=0
   for j,(v,c) in enumerate(zip(values,colors)):ax.bar(i,v,bottom=bottom,color=c,label=categories[j] if i==0 else None);bottom+=v
  ax.set_xticks(range(4),['EP','TP4','TP16','Hybrid']);ax.set(title=f'B{b}: selected causal parent chain',ylabel='Critical-path time (us)');ax.legend(fontsize=7)
 fig.suptitle('Service stages include their SRAM/vector work; not additive busy-window counters',fontsize=11);save(fig,out,'critical-path')
 supplements(out,points,iso)
if __name__=='__main__':main()
