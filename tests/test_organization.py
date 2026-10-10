import copy
import unittest
from thermal_exploration.hardware_contract import IncompleteCalibration,load_profile,require_prediction_ready
from thermal_exploration.hb_trace import address_vector,gemv_trace,streaming_trace,validate
from thermal_exploration.organization import bounds,load_exploration,lp_config,organization_cost,values
from thermal_exploration.model import kernel


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

    def test_mapping_preserves_32gib_geometry_and_local_full_gemv(self):
        for paths in (1,2,4):
            req=gemv_trace(paths);work=validate(req,paths)
            self.assertEqual(work,dict(request_count=32776,read_bytes=2*4096**2+8192,useful_flops=2*4096**2))
            self.assertEqual(len({r["address"] for r in req}),len(req))
            self.assertEqual(address_vector(32*2**30-1024,paths)[5],32767)
            self.assertEqual(len({tuple(address_vector(i*4096,paths)[:5]) for i in range(256)}),256)
        bad=streaming_trace(1,16);bad[0]["addr_vec"][0]=1
        with self.assertRaises(ValueError):validate(bad,1)


if __name__=="__main__":unittest.main()
