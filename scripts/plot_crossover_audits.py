"""Scientific plots of overlapping native observations and conditional heat."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',required=True);a=ap.parse_args();p=Path(a.results)
 plt.rcParams.update({'font.size':9})
 def save(fig,name):
  fig.tight_layout();fig.savefig(p/(name+'.png'),dpi=180);fig.savefig(p/(name+'.pdf'));plt.close(fig)
 d=json.load(open(p/'detailed-memory.json'))
 chosen=[r for r in d if r['case'] in ('row_fifo_k','column_fifo64','row_blocked_k')]
 labels=[('Expert B2' if 'expert' in r['experiment'] else 'QKV B4' if 'b4' in r['experiment'] else 'QKV B1')+' '+('cached' if r['case']=='row_blocked_k' else 'row' if r['case']=='row_fifo_k' else 'column') for r in chosen]
 fig,ax=plt.subplots(1,2,figsize=(13,4.8));ax[0].barh(labels,[r['useful_dram_tb_s'] for r in chosen]);ax[0].axvline(26.599,ls='--',c='grey',label='Long-stream reference, not universal bound');ax[0].axvline(32,ls=':',c='black',label='HB capacity');ax[0].set(xlabel='Useful weight TB/s');ax[0].legend(fontsize=7,loc='lower right')
 states=sorted({s for r in chosen for s in r['exclusive_mac_tile_tick_states']});left=[0.]*len(chosen)
 for state in states:
  values=[100*r['exclusive_mac_tile_tick_states'].get(state,0)/r['state_denominator'] for r in chosen]
  ax[1].barh(labels,values,left=left,label=state.replace('mac_occupied','task occupied (incl. ports)').replace('_',' '));left=[a+b for a,b in zip(left,values)]
 ax[1].set(xlabel='Exclusive tile/task-slot observations (%)',xlim=(0,100));ax[1].legend(fontsize=7,loc='upper left',bbox_to_anchor=(1.01,1))
 fig.suptitle('Native causal supply: task occupancy is not arithmetic MAC utilization');save(fig,'native-memory-breakdown')
 t=json.load(open(p/'thermal.json'));fig,ax=plt.subplots(1,2,figsize=(12,4.8))
 for workload in dict.fromkeys(r['workload'] for r in t):
  rr=sorted((r for r in t if r['workload']==workload),key=lambda r:r['profile']['compute_tflops']);base=next(r for r in rr if r['profile']['compute_tflops']==128)
  xs=[r['profile']['compute_tflops'] for r in rr];label=workload.replace('_',' ')
  ax[0].plot(xs,[max(r['periodic_logic_peak_c'],r['periodic_dram_peak_c']) for r in rr],'-o',label=label)
  ax[1].plot(xs,[100*r['energy_per_token_j']/base['energy_per_token_j'] for r in rr],'-o',label=label)
 ax[0].axhline(85,ls='--',c='black');ax[0].set(ylabel='Periodic peak temperature (°C)',xlabel='Peak MAC TFLOP/s',ylim=(35,88));ax[0].legend(fontsize=7)
 ax[1].axhline(100,ls='--',c='grey');ax[1].set(ylabel='Energy/token relative to128TF (%)',xlabel='Peak MAC TFLOP/s');ax[1].legend(fontsize=7)
 for axis in ax:axis.set_xticks([64,96,128,152]);axis.grid(alpha=.2)
 fig.suptitle('Default cooling only: assumed source/energy model; no thermal throttling');save(fig,'thermal-frontier')
if __name__=='__main__':main()
