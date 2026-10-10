import copy
import json
from pathlib import Path
import unittest

import numpy as np

from thermal_exploration.memory_audit import internal_ceilings, power_breakdown
from thermal_exploration.model import optimize, fabric_cases
from thermal_exploration.thermal import response

ROOT = Path(__file__).resolve().parents[1]


class NecessaryMemoryBounds(unittest.TestCase):
    def setUp(self):
        self.audit = json.loads((ROOT / "configs/memory_audit.json").read_text())

    def test_units_and_four_activation_window(self):
        limits = internal_ceilings(self.audit, self.audit["traffic_cases"][2])
        self.assertAlmostEqual(limits["bank_act_pre_tb_s"], 256 * 32 / 45 / 1000)
        self.assertAlmostEqual(limits["activation_tFAW_tb_s"], 256 * 4 / 20 / 1000)
        self.assertAlmostEqual(limits["column_periphery_tb_s"], 256 * 8 / 2 / 1000)

    def test_subarray_oracle_does_not_multiply_shared_activation_or_io(self):
        traffic = self.audit["traffic_cases"][3]
        a = internal_ceilings(self.audit, traffic)
        b = internal_ceilings(self.audit, traffic, 8)
        self.assertAlmostEqual(b["bank_act_pre_tb_s"], a["bank_act_pre_tb_s"] * 8)
        for key in ("activation_tRRD_tb_s", "activation_tFAW_tb_s", "column_periphery_tb_s"):
            self.assertEqual(a[key], b[key])

    def test_row_locality_and_bank_spreading_address_different_limits(self):
        cases = self.audit["traffic_cases"]
        full = internal_ceilings(self.audit, cases[0]); small = internal_ceilings(self.audit, cases[2])
        hot = internal_ceilings(self.audit, cases[3])
        self.assertAlmostEqual(full["activation_tFAW_tb_s"] / small["activation_tFAW_tb_s"], 32)
        self.assertEqual(full["column_periphery_tb_s"], small["column_periphery_tb_s"])
        self.assertEqual(hot["activation_tFAW_tb_s"], small["activation_tFAW_tb_s"])
        self.assertAlmostEqual(small["bank_act_pre_tb_s"] / hot["bank_act_pre_tb_s"], 32)

    def test_separate_act_pre_and_byte_energy_accounting(self):
        a = dict(self.audit, **self.audit["traffic_cases"][0])
        b = power_breakdown(a, 1.0)
        self.assertAlmostEqual(b["act_count_s"], 1e12 / 8192)
        self.assertAlmostEqual(b["act_power_w"] + b["pre_power_w"], 1e12 / 8192 * 8e-9)
        self.assertAlmostEqual(b["array_dynamic_power_w"] + b["peripheral_dynamic_power_w"], 12)

    def test_explicit_internal_cap_replaces_legacy_serial_penalty(self):
        cfg = json.loads((ROOT / "configs/pilot.json").read_text())
        cfg["hardware"]["internal_bank_group_ceiling_tb_s"] = 0.01
        h, gh, _ = response(4, cfg["thermal"])
        r = optimize(cfg, h, gh, cfg["workloads"][0], cfg["tilings"][0],
                     fabric_cases(cfg["hardware"])[0], 0, np.ones(16)/16, "free")
        self.assertAlmostEqual(r["used_bandwidth_tb_s"], 0.16)
        self.assertAlmostEqual(r["effective_bank_tb_s"], 0.01)

    def test_unphysical_row_utilization_rejected(self):
        traffic = copy.deepcopy(self.audit["traffic_cases"][0]); traffic["useful_bytes_per_activation"] *= 2
        with self.assertRaises(ValueError):
            internal_ceilings(self.audit, traffic)


if __name__ == "__main__":
    unittest.main()
