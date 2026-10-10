import copy
import json
from pathlib import Path
import unittest

import numpy as np
from scipy.sparse.linalg import spsolve

from thermal_exploration.model import optimize, fabric_cases, route
from thermal_exploration.thermal import assemble, response


class PhysicsAndFairness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((Path(__file__).resolve().parents[1]/"configs/pilot.json").read_text())
        cls.h,cls.gh,_=response(4,cls.cfg["thermal"])
        cls.profile=np.ones(16)/16

    def run_point(self, cfg=None, fabric=0, mode=2, placement="fixed"):
        c=cfg or self.cfg
        h,gh,_=response(c["grid"],c["thermal"])
        return optimize(c,h,gh,c["workloads"][0],c["tilings"][-1],
                        fabric_cases(c["hardware"])[fabric],mode,self.profile,placement)

    def test_conservation_and_reciprocity(self):
        a=assemble(4,self.cfg["thermal"])
        self.assertTrue(np.allclose(a.toarray(),a.toarray().T))
        self.assertGreater(min(np.linalg.eigvalsh(a.toarray())),0)
        b=np.r_[np.arange(1,33),np.zeros(16)]
        t=spsolve(a,b)
        # Every watt ultimately leaves through top-side convection.
        self.assertAlmostEqual(0.1*sum(t[32:]),sum(b),places=8)
        self.assertTrue(np.allclose(self.h,self.h.T,atol=1e-8))

    def test_hb_peak_does_not_create_power_for_unused_bandwidth(self):
        a=self.run_point(mode=0)
        c=copy.deepcopy(self.cfg);c["hardware"]["bank_group_peak_tb_s"]*=2
        b=self.run_point(cfg=c,mode=0)
        self.assertGreaterEqual(b["tflops"],a["tflops"]-1e-8)
        self.assertAlmostEqual(a["dram_power_w"]-4.8,
                               (b["dram_power_w"]-4.8)*a["tflops"]/b["tflops"],places=7)

    def test_uniform_control_has_no_ideal_ownership_gain(self):
        for mode in range(3):
            a=self.run_point(mode=mode)
            b=self.run_point(fabric=2,mode=mode)
            self.assertAlmostEqual(a["tflops"],b["tflops"],places=6)

    def test_work_and_data_completion(self):
        r=self.run_point(fabric=2)
        mapping=np.asarray(r["mapping_tflops"])
        np.testing.assert_allclose(mapping.sum(axis=0),r["tflops"]*self.profile,atol=1e-7)
        self.assertAlmostEqual(r["used_bandwidth_tb_s"],r["tflops"]/r["intensity_flop_byte"],places=8)
        self.assertLessEqual(max(r["temperature_c"]),85+1e-6)
        self.assertLessEqual(r["original_constraint_max_violation"],1e-6)
        self.assertTrue(np.all(np.sum(r["dvfs_time_fractions"],axis=1)<=1+1e-7))

    def test_relaxations_cannot_reduce_optimum(self):
        c=copy.deepcopy(self.cfg);c["thermal"]["cooling_gradient"]=0.6
        fixed=self.run_point(c,placement="fixed")
        free=self.run_point(c,placement="free")
        ideal=self.run_point(c,fabric=2,placement="free")
        self.assertGreaterEqual(free["tflops"],fixed["tflops"]-1e-7)
        self.assertGreaterEqual(ideal["tflops"],free["tflops"]-1e-7)
        self.assertLessEqual(max(free["bank_fractions"]),0.125+1e-8)

    def test_matched_baselines_and_routing(self):
        f=fabric_cases(self.cfg["hardware"])
        self.assertEqual(f[3].area_fraction,f[4].area_fraction)
        self.assertEqual(f[3].static_w,f[4].static_w)
        self.assertEqual(route(15,0,4),[(0,1),(1,2),(2,3),(3,7),(7,11),(11,15)])

    def test_row_activation_has_energy_and_bandwidth_cost(self):
        hw=self.cfg["hardware"]
        a=optimize(self.cfg,self.h,self.gh,self.cfg["workloads"][0],self.cfg["tilings"][0],
                   fabric_cases(hw)[0],0,self.profile)
        b=self.run_point(mode=0)
        self.assertGreater(b["effective_bank_tb_s"],a["effective_bank_tb_s"])
        ea=(a["dram_power_w"]-4.8)/a["used_bandwidth_tb_s"]
        eb=(b["dram_power_w"]-4.8)/b["used_bandwidth_tb_s"]
        self.assertGreater(ea,eb)


if __name__ == "__main__":
    unittest.main()
