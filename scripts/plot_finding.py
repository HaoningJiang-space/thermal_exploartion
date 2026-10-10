"""Compact scientific plot; normalization always uses the original Local."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

p=argparse.ArgumentParser();p.add_argument("--summary",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
a=p.parse_args();rows=json.loads(a.summary.read_text())
fig,axs=plt.subplots(1,2,figsize=(10,4),sharey=True)
for ax,placement in zip(axs,["fixed","free"]):
    x=np.arange(3)
    for idx,candidate in enumerate(["global_ideal","mesh_paid"]):
        r=next(r for r in rows if r["scenario"]=="gradient_uniform" and r["workload"]=="batch32_gemm"
               and r["placement"]==placement and r["candidate"]==candidate)
        vals=[r[f"net_speedup_t{m}_vs_original_local"] for m in range(3)]
        bars=ax.bar(x+(idx-0.5)*0.33,vals,0.33,label=candidate,bottom=0)
        for bar,val in zip(bars,vals):
            ax.text(bar.get_x()+bar.get_width()/2,val+0.004,f"{(val-1)*100:+.2f}%",ha="center",fontsize=9)
    ax.axhline(1,color="black",linewidth=1)
    ax.set_xticks(x,["T0: no heat limit","T1: global R","T2: spatial H"],fontsize=9)
    ax.set_title("Fixed bank placement" if placement=="fixed" else "Reoptimized bank placement")
    ax.set_ylim(0.9,1.21);ax.grid(axis="y",alpha=0.2);ax.legend(fontsize=9)
axs[0].set_ylabel("Speedup vs original Local")
fig.suptitle("Batch-32 GEMM / cooling gradient / uncalibrated screening model")
fig.tight_layout();fig.savefig(a.output,dpi=180);plt.close(fig)
