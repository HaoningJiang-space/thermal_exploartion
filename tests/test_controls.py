import json
from pathlib import Path
import unittest

import numpy as np

from thermal_exploration.gate import classify
from thermal_exploration.thermal import layer_response, response
from thermal_exploration.model import optimize, fabric_cases
from thermal_exploration.multiphase import optimize_cycle, g2_fabrics
from thermal_exploration.run import summarize

ROOT = Path(__file__).resolve().parents[1]


class LayerControl(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "configs/pilot.json").read_text())
        self.cfg["thermal"]["cooling_gradient"] = 0.6
        self.h, self.gh, _ = response(4, self.cfg["thermal"])

    def test_uniform_layer_power_matches_spatial_layer_means(self):
        p = np.r_[np.full(16, 19 / 16), np.full(16, 71 / 16)]
        actual = (self.h @ p).reshape(2, 16).mean(axis=1)
        control = (layer_response(self.h) @ p).reshape(2, 16)
        np.testing.assert_allclose(control, np.repeat(actual[:, None], 16, axis=1))

    def test_no_lateral_information_but_layers_remain_distinct(self):
        layer = layer_response(self.h)
        p = np.zeros(32); p[0] = 10
        q = np.zeros(32); q[15] = 10
        np.testing.assert_allclose(layer @ p, layer @ q)
        q = np.zeros(32); q[16] = 10
        self.assertGreater(np.max(np.abs(layer @ p - layer @ q)), 1e-5)
        self.assertGreater(abs((layer @ p)[0] - (layer @ p)[16]), 1e-5)
        np.testing.assert_allclose(self.gh @ p, self.gh @ q)

    def test_each_layer_temperature_limit_is_enforced(self):
        cfg = self.cfg
        cfg["thermal"]["dram_limit_c"] = 75
        r = optimize(cfg, self.h, self.gh, cfg["workloads"][0], cfg["tilings"][-1],
                     fabric_cases(cfg["hardware"])[0], 3, np.ones(16) / 16, "free")
        self.assertEqual(r["thermal_model"], "T1_layer")
        self.assertLessEqual(r["layer_dram_c"], 75 + 1e-7)
        self.assertLessEqual(r["layer_logic_c"], 85 + 1e-7)

    def test_g2_shared_layer_control_respects_both_limits(self):
        g2 = json.loads((ROOT / "configs/g2.json").read_text())
        r = optimize_cycle(self.cfg, g2, self.h, self.gh, (1, 32),
                           g2_fabrics(self.cfg["hardware"])[0], 3)
        for s in r["segments"]:
            t = 25 + layer_response(self.h) @ s["power_w"]
            self.assertLessEqual(max(t), 85 + 1e-7)
        np.testing.assert_allclose(r["phases"][0]["bank_fractions"], r["phases"][1]["bank_fractions"])


class PlacementGate(unittest.TestCase):
    def gate(self, **kwargs):
        args = dict(placement="free", paid=True, controls_complete=True, net_t0=0.97,
                    net_t1_layer=0.99, net_t2=1.08, matched_t2=1.10)
        args.update(kwargs)
        return classify(**args)

    def test_fixed_layout_and_ideal_cost_oracles_cannot_pass(self):
        r = self.gate(placement="fixed", net_t2=1.1644)
        self.assertEqual(r["screening_class"], "fixed_placement_signal")
        self.assertFalse(r["architecture_gate_pass"])
        r = self.gate(paid=False)
        self.assertEqual(r["screening_class"], "ideal_upper_bound_signal")
        self.assertFalse(r["architecture_gate_pass"])

    def test_free_layout_net_cost_and_complete_controls_are_required(self):
        for kwargs in ({"net_t2": 1.0022}, {"net_t2": 1.04, "matched_t2": 1.10},
                       {"matched_t2": 1.04}, {"controls_complete": False},
                       {"placement": "independent_oracle"}):
            self.assertFalse(self.gate(**kwargs)["architecture_gate_pass"])
        self.assertTrue(self.gate()["architecture_gate_pass"])

    def test_layer_control_rejects_general_gain(self):
        self.assertFalse(self.gate(net_t1_layer=1.08)["architecture_gate_pass"])
        self.assertFalse(self.gate(net_t0=1.08)["architecture_gate_pass"])

    def test_pilot_summary_uses_free_results_and_layer_interaction(self):
        rows = []
        for p in ("fixed", "free"):
            for f in ("local", "local_matched", "neighbor_ideal", "global_ideal", "mesh_paid"):
                for m in (0, 1, 3, 2):
                    rate = 100.0
                    if f not in ("local", "local_matched") and m == 2:
                        rate *= 1.1644 if p == "fixed" else 1.0022
                    if f not in ("local", "local_matched") and m == 3:
                        rate *= 1.02
                    rows.append(dict(scenario="test", workload="gemm", placement=p,
                                     fabric=f, thermal_mode=m, tflops=rate))
        s = summarize(rows)
        self.assertFalse(any(r["architecture_gate_pass"] for r in s))
        r = next(r for r in s if r["placement"] == "fixed" and r["candidate"] == "mesh_paid")
        self.assertEqual(r["screening_class"], "fixed_placement_signal")
        self.assertAlmostEqual(r["free_t2_net_speedup"], 1.0022)
        self.assertAlmostEqual(r["spatial_interaction_ratio"], 1.1644 / 1.02)
        r = next(r for r in summarize([r for r in rows if r["placement"] == "fixed"])
                 if r["candidate"] == "mesh_paid")
        self.assertEqual(r["screening_class"], "incomplete_controls")


if __name__ == "__main__":
    unittest.main()
