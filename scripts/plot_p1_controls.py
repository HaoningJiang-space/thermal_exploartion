"""Focus on the corrected thermal controls; the full report includes T0."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
a=p.parse_args()
if a.output.exists():raise SystemExit("Preserve the existing figure")
rows=list(csv.DictReader(a.source.open()));fig,axs=plt.subplots(1,2,figsize=(11,4))
for ax,work in zip(axs,("batch1_gemv","batch32_gemm")):
    for j,fabric in enumerate(("local","global_ideal","mesh_paid")):
        selected={int(r["thermal_mode"]):float(r["tflops"]) for r in rows if r["scenario"]=="gradient_uniform"
                  and r["placement"]=="free" and r["workload"]==work and r["fabric"]==fabric}
        x=np.arange(3)+(j-1)*.24;v=[selected[m] for m in (1,3,2)]
        bars=ax.bar(x,v,width=.24,label=fabric)
        ax.bar_label(bars,fmt="%.2f",fontsize=7,padding=2)
    ax.set_xticks(range(3),["T1 scalar (legacy)","T1 layer","T2 spatial"])
    ax.set(title=work,ylabel="Local / candidate sustained LP throughput (TFLOP/s)")
    ax.set_ylim(0,ax.get_ylim()[1]*1.10);ax.grid(axis="y",alpha=.2)
axs[0].legend(fontsize=8,ncol=3)
fig.suptitle("P1 corrected controls / gradient cooling / free placement / uncalibrated model")
fig.tight_layout();fig.savefig(a.output,dpi=180);plt.close(fig)
