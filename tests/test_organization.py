import copy
import unittest
from thermal_exploration.hardware_contract import IncompleteCalibration,load_profile,require_prediction_ready
from thermal_exploration.hb_trace import address_vector,gemv_trace,streaming_trace,validate
from thermal_exploration.organization import bounds,load_exploration,lp_config,organization_cost,solve,thermal_config,values
from thermal_exploration.model import kernel
from thermal_exploration.thermal import response


class ArchitectureMode(unittest.TestCase):
    def setUp(self):self.profile=load_exploration()

    def test_exploration_is_separate_from_reference_calibration(self):
        require_prediction_ready(self.profile,"architecture_exploration")
        strict=load_profile("configs/platforms/stratum_micro2025.json")
        with self.assertRaises(IncompleteCalibration):require_prediction_ready(strict)
        with self.assertRaises(IncompleteCalibration):require_prediction_ready(strict,"architecture_exploration")
        bad=copy.deepcopy(self.profile);bad["parameters"]["hb_chip_tb_s"]["value"]=None
        with self.assertRaises(ValueError):require_prediction_ready(bad,"architecture_exploration")

    def test_paid_paths_keep_banks_compute_capacity_and_hb_fixed(self):
        cfg1=lp_config(self.profile,1,15);cfg2=lp_config(self.profile,2,25)
        for k in ("tile_peak_tflops","sram_bytes_per_tile","bank_group_peak_tb_s","outstanding_per_tile"):
            self.assertEqual(cfg1["hardware"][k],cfg2["hardware"][k])
        self.assertGreater(organization_cost(self.profile,2)["active_area_mm2"],organization_cost(self.profile,1)["active_area_mm2"])
        self.assertFalse(organization_cost(self.profile,8)["area_feasible"])
        self.assertGreater(cfg2["hardware"]["logic_static_w"],cfg1["hardware"]["logic_static_w"])

    def test_energy_partition_and_no_double_charged_activation(self):
        cfg=lp_config(self.profile,1,15);hw=cfg["hardware"]
        self.assertAlmostEqual(hw["dram_pj_per_byte"]+hw["logic_memory_pj_per_byte"],3.432)
        self.assertEqual(hw["activation_nj"],0)
        self.assertEqual(kernel(cfg["workloads"][0],cfg["tilings"][0])["bytes"],2*4096**2+8192)

    def test_parallel_paths_cannot_multiply_fixed_bank_or_hb_limits(self):
        a=bounds(self.profile,1);b=bounds(self.profile,4)
        self.assertEqual(a["bank_cycle_tb_s"],b["bank_cycle_tb_s"])
        self.assertEqual(a["hb_tb_s"],b["hb_tb_s"])
        self.assertAlmostEqual(b["bank_cycle_tb_s"],30.34074074)
        self.assertLessEqual(b["necessary_service_tb_s"],b["hb_tb_s"])

    def test_more_periphery_reduces_compute_under_shared_area_budget(self):
        costs=[organization_cost(self.profile,k,"shared_area") for k in (1,2,4,8)]
        self.assertTrue(all(c["area_feasible"] and c["active_area_mm2"]<=121 for c in costs))
        self.assertTrue(all(a["compute_peak_tflops"]>b["compute_peak_tflops"] for a,b in zip(costs,costs[1:])))
        for c in costs:self.assertEqual(c["compute_blocks"]%16,0)
        self.assertLess(costs[-1]["compute_peak_tflops"],128)

    def test_mapping_preserves_32gib_geometry_and_local_full_gemv(self):
        for paths in (1,2,4,8):
            req=gemv_trace(paths);work=validate(req,paths)
            self.assertEqual(work,dict(request_count=32776,read_bytes=2*4096**2+8192,useful_flops=2*4096**2))
            self.assertEqual(len({r["address"] for r in req}),len(req))
            self.assertEqual(address_vector(32*2**30-1024,paths)[5],32767)
            self.assertEqual(len({tuple(address_vector(i*4096,paths)[:5]) for i in range(256)}),256)
        bad=streaming_trace(1,16);bad[0]["addr_vec"][0]=1
        with self.assertRaises(ValueError):validate(bad,1)

    def test_mixed_cycle_cannot_drop_work_or_change_resident_layout(self):
        h,g,_=response(4,thermal_config(self.profile))
        r=solve(self.profile,2,29,h,g,2,2,allocation="shared_area")
        self.assertEqual([p["repetitions"] for p in r["phases"]],[1,32])
        for p in r["phases"]:
            self.assertAlmostEqual(p["completed_work_tflop"],2*4096**2*32/1e12)
        self.assertEqual(r["phases"][0]["bank_fractions"],r["phases"][1]["bank_fractions"])
        self.assertAlmostEqual(r["tflops"]*r["cycle_time_s"],sum(r["required_work_tflop"]))


if __name__=="__main__":unittest.main()
