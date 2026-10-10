"""Compare completion with independently audited arrivals; no execution rerun."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    src, out = Path(args.input), Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    summary = json.loads((src / "summary.json").read_text())
    audit = json.loads((src / "arrival-audit.json").read_text())
    cases = {c["name"]: c for c in summary["cases"]}
    arrivals = {c["case"]: c for c in audit["cases"]}
    names = ["ordinary_striped", "prefetched_striped", "mapped_prefetched",
             "fine_streaming_probe", "uniform_prefetched", "uniform_fine_probe"]
    labels = ["Ordinary striped", "Prefetch striped", "Mapped prefetch",
              "Fine probe", "Uniform prefetch", "Uniform fine probe"]
    rows = []
    for name in names:
        case, arrival = cases[name], arrivals[name]
        work, driver = case["workload"], case["driver"]
        if work["total_bytes"] != 6 * 2**30 or work["useful_flops"] != 7 * 2**30:
            raise ValueError("Frozen D2 work changed")
        if driver["ticks"] != arrival["finish_tick"] or arrival["requests"] * 1024 != work["total_bytes"]:
            raise ValueError("Arrival audit does not match execution")
        lower = arrival["fixed_arrival_completion_lower_bound_ticks"]
        if not arrival["last_delivery_tick"] <= lower <= driver["ticks"]:
            raise ValueError("Noncausal completion bound")
        # Frozen native timing uses 0.25 ns events, not the DRAM 0.5 ns CK.
        rows.append(dict(case=name,completion_us=driver["ticks"] * .00025,
                         last_byte_us=arrival["last_delivery_tick"] * .00025,
                         fixed_arrival_lower_us=lower * .00025,
                         tail_ns=(driver["ticks"] - lower) * .25,
                         consumer_only_speedup_upper_pct=arrival["fixed_arrival_consumer_speedup_upper_bound_pct"]))
    hb_lower_us = 6 * 2**30 / (32e12) * 1e6
    mac_lower_us = 7 * 2**30 / (128e12) * 1e6
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.8, 1]})
    y = list(range(len(rows)))
    axes[0].barh(y, [r["completion_us"] for r in rows], color="#80adba", label="Complete execution")
    axes[0].scatter([r["fixed_arrival_lower_us"] for r in rows], y, color="#263d4a", marker="D", s=28, label="Fixed-arrival lower bound", zorder=3)
    axes[0].axvline(hb_lower_us, color="#b17b33", linestyle="--", label=f"HB necessary bound {hb_lower_us:.2f} us")
    axes[0].axvline(mac_lower_us, color="#888888", linestyle=":", label=f"MAC necessary bound {mac_lower_us:.2f} us")
    axes[0].set(yticks=y, yticklabels=labels, xlabel="Complete-work time (us)", title="Supply horizon dominates this D2 workload")
    axes[0].invert_yaxis()
    axes[0].legend(fontsize=8, loc="lower right")
    axes[1].barh(y, [r["tail_ns"] for r in rows], color="#bf8547")
    axes[1].set(yticks=y, yticklabels=[], xlabel="Tail after fixed-arrival bound (ns)", title="Consumer-only headroom", xlim=(0, 10))
    axes[1].invert_yaxis()
    for i, row in enumerate(rows):
        axes[1].text(row["tail_ns"] + .1, i, f"{row['tail_ns']:g} ns", va="center", fontsize=9)
    figure.suptitle("Same 6 GiB / 7 GiFLOP; each bound conditions on its own memory schedule")
    figure.tight_layout()
    for extension in ("png", "pdf"):
        figure.savefig(out / ("arrival_bounds." + extension), dpi=180)
    plt.close(figure)
    evidence = dict(cases=rows,hb_necessary_lower_us=hb_lower_us,mac_necessary_lower_us=mac_lower_us,
                    input_sha256={name:hashlib.sha256((src/name).read_bytes()).hexdigest()
                                  for name in ("summary.json", "arrival-audit.json")},
                    scope="Conditional consumer-only bounds; not common global scheduling or thermal bounds",
                    execution_rerun=False)
    (out / "arrival-bounds.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
