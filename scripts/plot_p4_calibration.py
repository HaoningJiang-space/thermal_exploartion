"""Visualize component qualification without extrapolating to MoE."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);ap.add_argument('--old-results',type=Path,required=True);a=ap.parse_args()
 q=json.loads((a.results/'qualification.json').read_text());old=json.loads((a.old_results/'component-qualification.json').read_text());native=[r for r in q['records'] if r['backend']=='native'];legacy=[r for r in native if r['role']=='legacy'];shape=[r for r in native if r['role']=='shape_validation']
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180});fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained');x=np.arange(8)
 axes[0].bar(x-.18,[100*r['relative_error'] for r in old['records'] if r['backend']=='native'],width=.36,label='Archived packet Graph',color='#b03a2e');axes[0].bar(x+.18,[100*r['relative_error'] for r in legacy],width=.36,label='Finite flit interpreter',color='#2874a6')
 axes[0].set_xticks(x,[f'K{r["shape"][1]}, B{r["shape"][2]}\n{r["case"].split("_")[0]}' for r in legacy],rotation=40,ha='right',fontsize=8);axes[0].set_title('Same eight archived Native reference cases');axes[0].set_ylabel('Prediction / Native time - 1 (%)')
 axes[1].bar(np.arange(4),[100*r['relative_error'] for r in shape],color='#2874a6');axes[1].set_xticks(np.arange(4),[f'B{r["shape"][2]}\n{r["case"].split("_")[0]}' for r in shape]);axes[1].set_title('Real M1408 / K2048 projection shape validation');axes[1].set_ylabel('Prediction / Native time - 1 (%)');axes[1].set_ylim(-11,11)
 for ax in axes:ax.axhspan(-10,10,color='#2874a6',alpha=.06);ax.axhline(-10,color='#696969',ls='--');ax.axhline(10,color='#696969',ls='--');ax.axhline(0,color='black',lw=.7);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
 fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,-.09),ncol=2);fig.suptitle('Component contract calibration - full MoE Graph remains unqualified',fontsize=12)
 for ext in ('png','pdf'):fig.savefig(a.results/('component-calibration.'+ext),bbox_inches='tight')
 plt.close(fig)
if __name__=='__main__':main()
