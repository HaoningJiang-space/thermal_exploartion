import copy
import json
from pathlib import Path
import unittest

import numpy as np

from thermal_exploration.model import optimize
from thermal_exploration.multiphase import g2_fabrics, optimize_cycle
from thermal_exploration.thermal import response


class SharedPlacementGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.cfg=json.loads((root/"configs/pilot.json").read_text())
        cls.g2=json.loads((root/"configs/g2.json").read_text())
        cls.cfg["thermal"]["cooling_gradient"]=0.6
        cls.h,cls.gh,_=response(4,cls.cfg["thermal"])

    def point(self,placement="shared",mode=2,regime="phase_steady",fabric=0,reps=(1,32),g2=None):
        return optimize_cycle(self.cfg,g2 or self.g2,self.h,self.gh,reps,
                              g2_fabrics(self.cfg["hardware"])[fabric],mode,placement,regime)

    def test_oracle_reproduces_single_kernel_rate_bounds(self):
        r=self.point("independent_oracle")
        tiling=next(t for t in self.cfg["tilings"] if t["name"]==self.g2["tiling"])
        for phase in r["phases"]:
            workload=next(w for w in self.cfg["workloads"] if w["name"]==phase["name"])
            oracle=optimize(self.cfg,self.h,self.gh,workload,tiling,
                            g2_fabrics(self.cfg["hardware"])[0],2,np.ones(16)/16,"free")
            self.assertAlmostEqual(phase["tflops"],oracle["tflops"],places=5)

    def test_shared_layout_and_exact_completed_work(self):
        r=self.point(reps=(1,128))
        a,b=r["phases"]
        np.testing.assert_allclose(a["bank_fractions"],b["bank_fractions"],atol=1e-9)
        for phase in r["phases"]:
            self.assertAlmostEqual(phase["completed_work_tflop"],phase["required_work_tflop"],places=9)
            self.assertAlmostEqual(sum(phase["bank_fractions"]),1,places=8)
            self.assertLessEqual(max(phase["bank_fractions"])*r["resident_weight_bytes"],r["bank_capacity_bytes"]+1e-3)
        self.assertAlmostEqual(b["required_work_tflop"]/a["required_work_tflop"],4.0)

    def test_relaxation_ordering_for_both_thermal_regimes(self):
        for regime in ("phase_steady","cycle_average"):
            a=self.point("independent_oracle",regime=regime)
            b=self.point("migration",regime=regime)
            c=self.point("shared",regime=regime)
            self.assertLessEqual(a["cycle_time_s"],b["cycle_time_s"]+1e-8)
            self.assertLessEqual(b["cycle_time_s"],c["cycle_time_s"]+1e-8)

    def test_identical_phase_layout_has_no_shared_placement_penalty(self):
        g=copy.deepcopy(self.g2);g["phases"]=["batch32_gemm","batch32_gemm"]
        for regime in ("phase_steady","cycle_average"):
            a=self.point("independent_oracle",regime=regime,g2=g)
            b=self.point("shared",regime=regime,g2=g)
            self.assertAlmostEqual(a["cycle_time_s"],b["cycle_time_s"],places=8)

    def test_repetition_scaling_cannot_drop_decode_work(self):
        a=self.point(reps=(1,1));b=self.point(reps=(2,2))
        self.assertAlmostEqual(b["cycle_time_s"],2*a["cycle_time_s"],places=8)
        self.assertEqual(b["phases"][1]["repetitions"],2)

    def test_migration_charges_both_periodic_transitions_and_io(self):
        r=self.point("migration",regime="cycle_average",fabric=4)
        self.assertEqual([(m["source_phase"],m["destination_phase"]) for m in r["migrations"]],[(0,1),(1,0)])
        for m in r["migrations"]:
            self.assertGreaterEqual(m["moved_bytes"],m["minimum_layout_change_bytes"]-1e-2)
            self.assertAlmostEqual(m["total_read_write_bytes"],2*m["moved_bytes"])
            if m["moved_bytes"]>1e-2:
                self.assertGreater(m["duration_s"],0)
                self.assertGreater(m["dynamic_energy_j"],0)
        self.assertAlmostEqual(r["cycle_time_s"],sum(s["duration_s"] for s in r["segments"]),places=9)

    def test_incompatible_weights_and_insufficient_capacity_rejected(self):
        g=copy.deepcopy(self.g2);g["resident_weight_bytes"]+=1
        with self.assertRaises(ValueError):self.point(g2=g)
        g=copy.deepcopy(self.g2);g["bank_capacity_bytes"]=1
        with self.assertRaises(ValueError):self.point(g2=g)
        with self.assertRaises(ValueError):self.point(reps=(1,0))

    def test_forced_disjoint_layouts_move_one_full_tensor_each_direction(self):
        layouts=[np.r_[np.full(8,1/8),np.zeros(8)],np.r_[np.zeros(8),np.full(8,1/8)]]
        r=optimize_cycle(self.cfg,self.g2,self.h,self.gh,(1,32),
                         g2_fabrics(self.cfg["hardware"])[0],2,"migration","cycle_average",layouts)
        for m in r["migrations"]:
            self.assertAlmostEqual(m["moved_bytes"],self.g2["resident_weight_bytes"],delta=1e-2)
            self.assertGreater(m["duration_s"],0)
            # Both DRAM endpoints are charged even if wire cost were zero.
            minimum=self.g2["resident_weight_bytes"]*24/1e12
            self.assertGreaterEqual(m["dynamic_energy_j"],minimum)
        self.assertAlmostEqual(r["migration_moved_bytes"],2*self.g2["resident_weight_bytes"],delta=1e-2)


if __name__=="__main__":unittest.main()
