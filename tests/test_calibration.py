import copy
from pathlib import Path
import unittest

from thermal_exploration.calibrate import audit_profile
from thermal_exploration.hardware_contract import (IncompleteCalibration, area_inventory,
    decode_reference_address, geometry, load_profile, power_inventory,
    require_prediction_ready, tier_bound, hb_interface_contract, top_cooling_necessary_bound)

ROOT=Path(__file__).resolve().parents[1]


class StratumReferenceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile=load_profile(ROOT/"configs/platforms/stratum_micro2025.json")

    def test_bank_tier_capacity_and_sram_hierarchy(self):
        g=geometry(self.profile)
        self.assertEqual(g["bank_count"],256)  # tiers partition these banks, not multiply them
        self.assertEqual(g["chip_capacity_bytes"],32*2**30)
        self.assertEqual(g["tier_capacity_bytes"],4*2**30)
        self.assertEqual(g["sram_bytes"],36*2**20)
        self.assertEqual(g["row_swap_rf_bytes"],2*2**20)  # RF is not counted again as SRAM
        self.assertEqual(g["mac_count"],65536)
        self.assertAlmostEqual(g["topology_peak_tflops"],131.072)

    def test_tier_timings_reproduce_body_bank_bounds(self):
        expected=[34.56,36.19,38.26,40.77,43.71,47.09,50.90,55.15]
        for i,rc in enumerate(expected):self.assertAlmostEqual(tier_bound(self.profile,i)["tRC_ns"],rc)
        self.assertAlmostEqual(tier_bound(self.profile,0)["bank_only_full_row_ceiling_tb_s"],30.34,delta=.001)
        self.assertAlmostEqual(tier_bound(self.profile,7)["bank_only_full_row_ceiling_tb_s"],19.01,delta=.004)

    def test_row_mapping_boundaries_do_not_invent_command_domains(self):
        for row,tier in ((0,0),(4095,0),(4096,1),(32767,7)):
            a=decode_reference_address(self.profile,15,15,row,4095)
            self.assertEqual(a["timing_tier"],tier)
            self.assertIsNone(a["activation_domain"])
            self.assertIsNone(a["column_domain"])
        with self.assertRaises(ValueError):decode_reference_address(self.profile,16,0,0,0)
        with self.assertRaises(ValueError):decode_reference_address(self.profile,0,0,0,4096)

    def test_tRCD_changes_cycle_and_inflight_necessary_bounds(self):
        p=copy.deepcopy(self.profile);p["dram"]["tier_tRCD_ns"][0]=30
        a=tier_bound(self.profile,0);b=tier_bound(p,0)
        self.assertLess(b["bank_only_full_row_ceiling_tb_s"],a["bank_only_full_row_ceiling_tb_s"])
        self.assertGreater(b["minimum_ACT_to_column_delay_ns"],a["minimum_ACT_to_column_delay_ns"])
        self.assertGreater(b["necessary_inflight_requests_at_ceiling_for_256b"],a["necessary_inflight_requests_at_ceiling_for_256b"])

    def test_area_leaves_close_without_parent_double_counting(self):
        a=area_inventory(self.profile)
        self.assertAlmostEqual(sum(r["area_mm2"] for r in a["leaves"]),76.55)
        self.assertAlmostEqual(a["relative_difference"],76.55/76.63-1)
        self.assertIsNone(a["controller_noc_vector_separate_areas"])

    def test_power_anchor_does_not_hide_logic_disagreement(self):
        p=power_inventory(self.profile)
        self.assertAlmostEqual(p["dram_aggregate_at_reference_bandwidth_w"],104.12688)
        self.assertAlmostEqual(p["mac_at_reported_peak_w"],38.656)
        self.assertAlmostEqual(p["mac_plus_figure_memory_communication_w"],45.44891)
        self.assertGreater(p["logic_relative_error"],.06)
        self.assertIsNone(p["component_coefficients"]["NoC"])
        a=audit_profile(self.profile)
        self.assertFalse(a["gates"]["G3.2"]["logic_power_composition_reference_check_pass"])
        self.assertFalse(a["whole_model_calibration_gate_pass"])

    def test_missing_physical_inputs_block_prediction(self):
        with self.assertRaises(IncompleteCalibration):require_prediction_ready(self.profile)
        self.assertIsNone(self.profile["dram"]["tFAW_ns"])
        self.assertIsNone(self.profile["hybrid_bonding"]["data_pad_count"])
        self.assertIsNone(self.profile["thermal"]["calibrated_geometry"])

    def test_free_bandwidth_does_not_create_physical_interface(self):
        p=copy.deepcopy(self.profile)
        p["hybrid_bonding"].update(data_pad_count=128000,data_rate_per_pad_gbps=1)
        c=hb_interface_contract(p)
        self.assertEqual(c["data_rate_tb_s"],16)
        self.assertFalse(c["physically_complete"])
        self.assertIn("io_area_mm2",c["missing_fields"])
        p["hybrid_bonding"]["data_pad_count"]=-1
        with self.assertRaises(ValueError):hb_interface_contract(p)

    def test_legacy_cooling_is_already_infeasible_before_logic(self):
        bound=top_cooling_necessary_bound(.02**2,4000,25,85)
        self.assertAlmostEqual(bound,96)
        self.assertGreater(16*12,bound)
        with self.assertRaises(ValueError):top_cooling_necessary_bound(.02**2,0,25,85)


if __name__=="__main__":unittest.main()
