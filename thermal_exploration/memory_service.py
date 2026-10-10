"""Shared steady DRAM service coefficients for G1, G2, and Memory Audit.

These are rates/energy coefficients, not command scheduling. Keeping this
boundary shared prevents different entry points silently using different caps.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MemoryService:
    bank_ceiling_tb_s: float
    read_latency_ns: float
    energy_pj_per_useful_byte: float
    activations_per_useful_byte: float
    model_kind: str


def memory_service_model(hw, kernel):
    peak = hw["bank_group_peak_tb_s"]
    if "internal_bank_group_ceiling_tb_s" in hw:
        # Independent necessary timing cap replaces the serial approximation.
        internal = hw["internal_bank_group_ceiling_tb_s"]
        bank_bw = min(peak, internal)
        kind = "explicit_internal_necessary_ceiling"
    else:
        bank_bw = 1 / (1 / peak + hw["row_miss_penalty_ns"] * 1000
                       * kernel["row_miss_fraction"] / (kernel["chunk_bytes"]
                                                       * hw["independent_banks_per_group"]))
        kind = "legacy_serial_row_miss_relaxation"
    acts = kernel["row_miss_fraction"] / kernel["chunk_bytes"]
    energy = hw["dram_pj_per_byte"] + hw["activation_nj"] * 1000 * acts
    latency = hw["read_latency_ns"]
    if not all(math.isfinite(v) and v > 0 for v in (peak, bank_bw, latency)):
        raise ValueError("Memory peak, internal service rate, and latency must be positive and finite")
    if energy < 0 or not math.isfinite(energy) or acts < 0:
        raise ValueError("Invalid DRAM energy or row activity")
    return MemoryService(bank_bw, latency, energy, acts, kind)
