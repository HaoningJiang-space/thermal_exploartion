import copy
import json
from pathlib import Path
import unittest

import numpy as np

from thermal_exploration.memory_service import memory_service_model
from thermal_exploration.model import kernel, optimize
from thermal_exploration.multiphase import g2_fabrics, optimize_cycle, service_block
from thermal_exploration.thermal import THERMAL_MODES, response

ROOT = Path(__file__).resolve().parents[1]


class SharedMemoryService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((ROOT/"configs/pilot.json").read_text())
        cls.g2=json.loads((ROOT/"configs/g2.json").read_text())
        cls.cfg["thermal"]["cooling_gradient"]=0.6
        cls.h,cls.gh,_=response(4,cls.cfg["thermal"])

    def test_legacy_coefficients_and_explicit_replacement(self):
        hw=self.cfg["hardware"];kr=kernel(self.cfg["workloads"][0],self.cfg["tilings"][0])
        m=memory_service_model(hw,kr)
        self.assertAlmostEqual(m.bank_ceiling_tb_s,1/(1/hw["bank_group_peak_tb_s"]+1000*hw["row_miss_penalty_ns"]*kr["row_miss_fraction"]/(kr["chunk_bytes"]*hw["independent_banks_per_group"])))
        self.assertEqual(m.model_kind,"legacy_serial_row_miss_relaxation")
        for cap in (.01,100):
            c=dict(hw,internal_bank_group_ceiling_tb_s=cap)
            m=memory_service_model(c,kr)
            self.assertEqual(m.bank_ceiling_tb_s,min(cap,hw["bank_group_peak_tb_s"]))
            b=service_block(dict(self.cfg,hardware=c),self.cfg["workloads"][0],self.cfg["tilings"][0],g2_fabrics(c)[0])
            self.assertEqual(b.bank_bw,m.bank_ceiling_tb_s)

    def test_g1_and_independent_g2_phase_optima_match_with_internal_caps(self):
        # Duplicate a kernel in G2: each independent phase is exactly the same
        # single-stage problem. Covers cap-dominated, legacy, and queue limits.
        for cap,queue in ((None,512),(.01,512),(100,1)):
            cfg=copy.deepcopy(self.cfg);cfg["hardware"]["outstanding_per_tile"]=queue
            if cap is not None:cfg["hardware"]["internal_bank_group_ceiling_tb_s"]=cap
            for workload in cfg["workloads"]:
                g2=copy.deepcopy(self.g2);g2["phases"]=[workload["name"]]*2
                tiling=next(t for t in cfg["tilings"] if t["name"]==g2["tiling"])
                for fabric in (g2_fabrics(cfg["hardware"])[0],g2_fabrics(cfg["hardware"])[4]):
                    for mode in THERMAL_MODES:
                        a=optimize(cfg,self.h,self.gh,workload,tiling,fabric,mode,np.ones(16)/16,"free")
                        b=optimize_cycle(cfg,g2,self.h,self.gh,(1,1),fabric,mode,"independent_oracle")
                        for phase in b["phases"]:
                            self.assertAlmostEqual(phase["tflops"]/a["tflops"],1,places=7)
                            # Throughput is the objective; degenerate optima may
                            # select different Logic DVFS power distributions.
                            self.assertAlmostEqual(phase["dram_power_w"],a["dram_power_w"],places=5)

    def test_fixed_layout_phase_equivalence_and_latency_accounting(self):
        cfg=copy.deepcopy(self.cfg);cfg["hardware"]["internal_bank_group_ceiling_tb_s"]=.1
        cfg["hardware"]["read_latency_ns"]=100
        g2=copy.deepcopy(self.g2);w=cfg["workloads"][0];g2["phases"]=[w["name"]]*2
        t=next(t for t in cfg["tilings"] if t["name"]==g2["tiling"]);f=g2_fabrics(cfg["hardware"])[0]
        profile=np.ones(16)/16
        a=optimize(cfg,self.h,self.gh,w,t,f,2,profile,"fixed")
        b=optimize_cycle(cfg,g2,self.h,self.gh,(1,1),f,2,"shared",fixed_layouts=[profile,profile])
        self.assertAlmostEqual(b["phases"][0]["tflops"],a["tflops"],places=7)
        service=memory_service_model(cfg["hardware"],kernel(w,t))
        self.assertEqual(service.read_latency_ns,100)


if __name__=="__main__":unittest.main()
