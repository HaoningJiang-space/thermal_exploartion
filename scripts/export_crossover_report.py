"""Export all admissions, failures, resource probes and fixed-area frontiers."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from thermal_exploration.crossover_execution import Profile

def read(path):return json.loads(path.read_text())
def default(r):
 p=r.get('profile',{})
 return r.get('status')=='PASS_ACCOUNTING' and p.get('compute_tflops')==128 and p.get('hb_tb_s')==32 and p.get('fifo_ingress_bytes_tick')==500 and p.get('isolation')=='none'
def strongest(rows):return min(rows,key=lambda r:r['time_us'])
def compact(r,directory):
 x={k:v for k,v in r.items() if k!='step_records'}
 x['raw_experiment']=directory.name
 if 'step_records' in r:
  times=[v['time_us'] for v in r['step_records']];x['step_latency_us']=dict(mean=sum(times)/len(times),minimum=min(times),maximum=max(times),count=len(times))
 return x

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();root=Path(a.root);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 directories=sorted(root.glob('crossover-main-*-2bb172c'))
 if len(directories)!=8 or any(not (d/'summary.json').exists() for d in directories):raise ValueError('Primary matrix incomplete')
 points=[];contracts=[];admissions=[]
 for d in directories:
  points += [compact(r,d) for r in read(d/'summary.json')];contracts.append(dict(experiment=d.name,contract=read(d/'contract.json')));admissions+=read(d/'admissions.json')
 supplemental=root/'crossover-supplement-6bf1571'
 if not (supplemental/'summary.json').exists():raise ValueError('Matched probes incomplete')
 points += [compact(r,supplemental) for r in read(supplemental/'summary.json')]
 best=[];frontier=[];probes=[];schedules=[]
 for scenario in dict.fromkeys(x['scenario'] for x in points):
  data=[r for r in points if r['scenario']==scenario];refs=[r for r in data if default(r)];b=strongest(refs)
  b=dict(b,memory_lower_fraction=b['data_supply_lower_bound_us']/b['time_us'],effective_mac_tflops=b['activity']['mac']/b['time_us']/1e6,mean_step_us=b['time_us']/b['steps'])
  best.append(b)
  for p in sorted({r['profile']['compute_tflops'] for r in data if r.get('status')=='PASS_ACCOUNTING' and r['profile']['isolation']=='none' and r['profile']['hb_tb_s']==32 and r['profile']['fifo_ingress_bytes_tick']==500}):
   f=strongest([r for r in data if r.get('status')=='PASS_ACCOUNTING' and r['profile']['compute_tflops']==p and r['profile']['isolation']=='none' and r['profile']['hb_tb_s']==32 and r['profile']['fifo_ingress_bytes_tick']==500])
   frontier.append(dict(scenario=scenario,compute_tflops=p,sram_mib=f['profile']['sram_mib'],tokens_s=f['tokens_s'],relative_performance=f['tokens_s']/b['tokens_s'],baseline=f['baseline'],schedule=f['schedule'],area=f['area']))
  for r in refs:
   schedules.append(dict(scenario=scenario,baseline=r['baseline'],schedule=r['schedule'],tokens_s=r['tokens_s']))
  for r in data:
   if r.get('status')!='PASS_ACCOUNTING' or r['profile']['compute_tflops']!=128:continue
   p=r['profile'];label=p['isolation'] if p['isolation']!='none' else 'HB16' if p['hb_tb_s']==16 else 'FIFO_ingress128' if p['fifo_ingress_bytes_tick']==128 else None
   if label:
    probes.append(dict(scenario=scenario,probe=label,speedup_fraction=b['time_us']/r['time_us']-1,baseline=r['baseline'],schedule=r['schedule'],reference_time_us=b['time_us'],time_us=r['time_us'],work_preserved={k:r['activity'][k]==b['activity'][k] for k in ('dram','mac','hb')}))
 area=[]
 for peak,sram in read(root/'crossover-2bb172c/configs/crossover/contract.json')['profiles']:
  p=Profile(peak,sram);area.append(dict(compute_tflops=peak,sram_mib=sram,default=p.area(),phi0=p.area(0),phi04=p.area(.4)))
 for name,data in [('all-points.json',points),('contracts.json',contracts),('admissions.json',admissions),('crossover-map.json',best),('resource-probes.json',probes),('schedules.json',schedules),('frontier.json',frontier),('area-ledger.json',area)]:
  (out/name).write_text(json.dumps(data,indent=2)+'\n')
 counts=Counter(r['status'] for r in points);(out/'counts.json').write_text(json.dumps(dict(points=len(points),statuses=counts,steps=128,primary_source='2bb172c',supplement_source='6bf1571'),indent=2)+'\n')
 plt.rcParams.update({'font.size':10})
 colors={'llama31_8b':'#2368a0','qwen15_moe':'#db6d27'}
 def save(fig,name):
  fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=180);fig.savefig(out/(name+'.pdf'));plt.close(fig)
 fig,ax=plt.subplots(1,2,figsize=(12,4.9));xs=[.1,20];ax[0].plot(xs,[min(128,x*26.599) for x in xs],'--',c='grey',label='Reference roofline (MAC only)')
 # Draw exact kink rather than the line through only the endpoints.
 ax[0].lines[0].remove();ax[0].plot([.1,128/26.599,20],[2.6599,128,128],'--',c='grey',label='Reference roofline (MAC only)')
 for r in best:
  control=r['admission']['context_extension_assumed'];marker='x' if control else 'o';ax[0].scatter(r['arithmetic_intensity'],r['effective_mac_tflops'],c=colors[r['model']],marker=marker)
  label=('L' if r['model']=='llama31_8b' else 'Q')+str(r['batch'])+('/32K' if r['context']==32768 else '/8K' if r['context']==8192 else '')
  offset=(4,-12) if r['scenario']=='qwen_b1_c2k' else (-16,8) if r['scenario']=='llama_b1_c2k' else (5,1) if control else (4,4)
  ax[0].annotate(label,(r['arithmetic_intensity'],r['effective_mac_tflops']),xytext=offset,textcoords='offset points',fontsize=8)
 ax[0].axvline(128/26.599,ls=':',c='black');ax[0].set(xlabel='Actual MAC FLOP / DRAM read byte',ylabel='Effective MAC TFLOP/s',ylim=(0,140),xlim=(0,17));ax[0].legend(fontsize=8)
 labels=[('L' if r['model']=='llama31_8b' else 'Q')+str(r['batch'])+'/'+str(r['context']) for r in best]
 ax[1].bar(range(len(best)),[100*r['memory_lower_fraction'] for r in best],color=[colors[r['model']] for r in best]);ax[1].set(xticks=range(len(best)),xticklabels=labels,ylim=(0,105),ylabel='Bytes / reference service / execution (%)');ax[1].tick_params(axis='x',rotation=65)
 fig.suptitle('128-step structural Decode: crossover, not a serving measurement');save(fig,'architecture-crossover')
 chosen=[s for s in dict.fromkeys(r['scenario'] for r in probes)]
 fig,ax=plt.subplots(1,3,figsize=(14,4.6))
 for axis,scenario in zip(ax,chosen):
  rr=[r for r in probes if r['scenario']==scenario];axis.barh([r['probe'] for r in rr],[100*r['speedup_fraction'] for r in rr]);axis.axvline(0,c='grey');axis.set(title=scenario.replace('_',' '),xlabel='Matched single-resource speedup (%)');axis.grid(axis='x',alpha=.2)
 fig.suptitle('Separate capacity probes; gains overlap and must not be summed');save(fig,'memory-service-isolation')
 fig,ax=plt.subplots(1,2,figsize=(12,4.8))
 for axis,model in zip(ax,('llama','qwen')):
  for scenario in dict.fromkeys(r['scenario'] for r in frontier if r['scenario'].startswith(model)):
   rr=sorted((r for r in frontier if r['scenario']==scenario),key=lambda r:r['compute_tflops'])
   if len(rr)<2:continue
   axis.plot([r['compute_tflops'] for r in rr],[100*r['relative_performance'] for r in rr],'-o',label=scenario.replace(model+'_',''))
  axis.axhline(100,ls='--',c='grey');axis.set(title=model.title(),xlabel='Peak MAC TFLOP/s (SRAM changes with profile)',ylabel='Relative tokens/s (%)',xticks=[64,96,128,152]);axis.legend(fontsize=8);axis.grid(alpha=.2)
 fig.suptitle('Fixed 121 mm² ledger: unassigned 35.25 mm² remains unavailable');save(fig,'architecture-frontier')
 fig,ax=plt.subplots(figsize=(9,4.3));key='llama_b4_c8k';rr=[r for r in schedules if r['scenario']==key]
 for i,b in enumerate(('B2_stream_fusion','B3_3d_placement')):
  v=[r for r in rr if r['baseline']==b];ax.bar([j+i*.38 for j in range(4)],[r['tokens_s'] for r in v],width=.38,label=b)
 ax.set(xticks=[j+.19 for j in range(4)],xticklabels=['Serial','Finite prefetch','Blocked collective','Both'],ylabel='Structural tokens/s',title='Llama B4/C8192: same area, work and ports');ax.legend();save(fig,'optimized-scheduling')
 print(json.dumps(dict(points=len(points),statuses=counts,output=str(out))))
if __name__=='__main__':main()
