"""Source-isolated platform inventory; incomplete profiles fail closed.

This is calibration bookkeeping, not a constructor for the legacy LP machine.
Unknown component values remain None instead of being silently assigned zero.
"""
import json
import math
from pathlib import Path


class IncompleteCalibration(ValueError):
    pass


def load_profile(path):
    p=json.loads(Path(path).read_text())
    if p.get("schema")!=1 or p.get("profile_kind")!="literature_reference_and_calibration_gate":
        raise ValueError("Unknown calibration profile schema")
    if "base_config" in p or "base_profile" in p:
        raise ValueError("Literature platforms cannot inherit the illustrative pilot machine")
    d=p["dram"]; l=p["logic"]
    if len(d["tier_tRCD_ns"])!=d["timing_tier_count"] or any(t<=0 for t in d["tier_tRCD_ns"]):
        raise ValueError("Every timing tier must have a positive sourced tRCD")
    if len(set(d["tier_tRCD_ns"]))!=d["timing_tier_count"]:
        raise ValueError("Tier timings cannot be silently flattened")
    if l["pu_count"]!=d["channels_per_chip"]:
        raise ValueError("This reference requires its reported PU/channel organization")
    return p


def geometry(profile):
    d=profile["dram"];l=profile["logic"]
    banks=d["channels_per_chip"]*d["banks_per_channel"]
    bank_bits=d["mats_per_bank"]*d["mat_rows"]*d["mat_columns"]
    rows=bank_bits//(d["row_buffer_bytes"]*8)
    if bank_bits%(d["row_buffer_bytes"]*8) or rows%d["timing_tier_count"]:
        raise ValueError("Row geometry cannot partition into timing tiers")
    macs=l["pu_count"]*l["pes_per_pu"]*l["mac_array_rows"]*l["mac_array_columns"]
    return dict(bank_count=banks,bank_capacity_bytes=bank_bits//8,
                chip_capacity_bytes=banks*bank_bits//8,rows_per_bank=rows,
                rows_per_tier_per_bank=rows//d["timing_tier_count"],
                tier_capacity_bytes=banks*bank_bits//8//d["timing_tier_count"],
                mac_count=macs,topology_peak_tflops=macs*l["frequency_ghz"]*2/1000,
                sram_bytes=l["pu_count"]*(l["shared_bytes_per_pu"]+l["pes_per_pu"]*l["psum_bytes_per_pe"]),
                row_swap_rf_bytes=l["pu_count"]*l["pes_per_pu"]*l["row_swap_rf_bytes_per_pe"])


def decode_reference_address(profile, channel, bank, row, column_byte):
    """Explicit derived equal-row tier mapping, not a validated bit-level map."""
    d=profile["dram"];g=geometry(profile)
    if not (0<=channel<d["channels_per_chip"] and 0<=bank<d["banks_per_channel"]
            and 0<=row<g["rows_per_bank"] and 0<=column_byte<d["row_buffer_bytes"]):
        raise ValueError("Address outside the sourced organization")
    return dict(channel=channel,bank=bank,row=row,column_byte=column_byte,
                timing_tier=row//g["rows_per_tier_per_bank"],
                activation_domain=None,column_domain=None,rank=None,bank_group=None,
                mapping_status="derived_uniform_row_partition; command-domain membership unavailable")


def tier_bound(profile, tier, useful_bytes=None, busy_banks=None):
    d=profile["dram"];g=geometry(profile)
    if not 0<=tier<d["timing_tier_count"]:
        raise ValueError("Invalid timing tier")
    q=d["row_buffer_bytes"] if useful_bytes is None else useful_bytes
    b=g["bank_count"] if busy_banks is None else busy_banks
    if not 0<q<=d["row_buffer_bytes"] or not 0<b<=g["bank_count"]:
        raise ValueError("Invalid useful row bytes or busy bank count")
    rcd=d["tier_tRCD_ns"][tier];ras=rcd+d["tRAS_offset_from_tRCD_ns"];rc=ras+d["tRP_ns"]
    rate=q*b/rc/1000
    return dict(tier=tier,tRCD_ns=rcd,tRAS_ns=ras,tRP_ns=d["tRP_ns"],tRC_ns=rc,
                bank_only_full_row_ceiling_tb_s=rate,
                minimum_ACT_to_column_delay_ns=rcd,
                necessary_inflight_requests_at_ceiling_for_256b=rate*1000*rcd/256,
                bound_status="conditional bank-cycle bound; unknown ACT/column/queue/HB constraints remain")


def area_inventory(profile):
    a=profile["areas"];l=profile["logic"]
    pu_area=a["pu_mm2"]*l["pu_count"]
    pe_area=pu_area*a["pu_fractions"]["processing_elements"]
    rows=[dict(component=k,area_mm2=pe_area*v,site="bonded_logic",scope="derived from rounded hierarchy percentages")
          for k,v in a["pe_fractions"].items()]
    rows.extend(dict(component=k,area_mm2=pu_area*v,site="bonded_logic",scope="derived combined group; subcomponent split unavailable")
                for k,v in a["pu_fractions"].items() if k!="processing_elements")
    rows.extend(dict(component=k,area_mm2=a[k],site="bonded_logic",scope="reported area")
                for k in ("external_hbm3_phy_mm2","low_voltage_dram_periphery_mm2","power_tsv_mm2"))
    total=sum(r["area_mm2"] for r in rows)
    return dict(leaves=rows,leaf_total_mm2=total,reported_active_mm2=a["reported_active_mm2"],
                absolute_difference_mm2=total-a["reported_active_mm2"],
                relative_difference=total/a["reported_active_mm2"]-1,
                die_headroom_mm2=profile["die"]["area_mm2"]-total,
                controller_noc_vector_separate_areas=None,
                pe_rounded_total_mm2=a["rounded_pe_mm2"]*l["pu_count"]*l["pes_per_pu"],
                pe_hierarchy_percentage_total_mm2=pe_area)


def power_inventory(profile):
    l=profile["logic"];d=profile["dram"];r=profile["reference_power"]
    stack=r["stack_body_w"];mem=stack*r["figure15_fractions"]["logic_memory_communication"]
    mac=l["reported_peak_tflops"]/2*l["mac_energy_pj_per_mac"]
    topology_mac=geometry(profile)["topology_peak_tflops"]/2*l["mac_energy_pj_per_mac"]
    pdram=d["energy_pj_per_bit"]*8*r["dram_approx_bandwidth_tb_s"]
    logic_sum=mac+mem
    return dict(mac_at_reported_peak_w=mac,mac_at_topology_peak_w=topology_mac,
                figure_compute_group_w=stack*r["figure15_fractions"]["compute"],
                figure_logic_memory_communication_group_w=mem,
                figure_dram_group_w=stack*r["figure15_fractions"]["dram"],
                mac_plus_figure_memory_communication_w=logic_sum,
                logic_reference_w=r["logic_body_w"],
                logic_absolute_error_w=logic_sum-r["logic_body_w"],
                logic_relative_error=logic_sum/r["logic_body_w"]-1,
                figure_logic_group_sum_w=stack*(1-r["figure15_fractions"]["dram"]),
                dram_aggregate_energy_ratio_pj_per_byte=d["energy_pj_per_bit"]*8,
                dram_aggregate_at_reference_bandwidth_w=pdram,
                dram_approx_reference_w=r["dram_approx_full_bandwidth_w"],
                dram_relative_error_vs_approx=pdram/r["dram_approx_full_bandwidth_w"]-1,
                dram_detailed_reference_from_stack_minus_logic_w=stack-r["logic_body_w"],
                dram_relative_error_vs_detailed=pdram/(stack-r["logic_body_w"])-1,
                component_coefficients={k:None for k in ("ACT","PRE","SRAM","NoC","Controller","Vector","Background","CUA_periphery","Logic_memory_periphery")},
                evidence_level="L0_reference_accounting_consistency",
                independent_power_validation=False,
                status="Same-paper aggregate arithmetic only; unresolved activity/scope; no workload coefficients fitted")


def require_prediction_ready(profile,mode="reference_reproduction"):
    if mode=="architecture_exploration":
        if profile.get("profile_kind")!="architecture_exploration_assumed" or not profile.get("policy",{}).get("conditional_exploration_allowed"):
            raise IncompleteCalibration("Architecture exploration requires its own sourced assumption contract")
        if not all(profile["fairness"].values()):raise ValueError("Missing fair resource/cost control")
        for name,p in profile["parameters"].items():
            if p["classification"] not in ("Paper-reported","Reasonably assumed","Idealized") or not p["basis"]:
                raise ValueError("Unclassified exploration parameter: "+name)
            if not isinstance(p["value"],(int,float)) or not math.isfinite(p["value"]):
                raise ValueError("Unknown/nonfinite exploration parameter: "+name)
            if p["range"] is not None and not p["range"][0]<=p["value"]<=p["range"][1]:
                raise ValueError("Default outside frozen assumption interval")
        return
    if mode!="reference_reproduction":raise ValueError("Unknown prediction mode")
    if not profile["calibration_policy"]["performance_prediction_allowed"] or profile["unresolved_inputs"]:
        raise IncompleteCalibration("Stratum reference cannot be used for performance/thermal predictions until unresolved inputs are calibrated")


def hb_interface_contract(profile):
    """A peak-rate equation is necessary, not sufficient, for a physical interface."""
    hb=profile["hybrid_bonding"]
    required=("data_pad_count", "data_rate_per_pad_gbps", "address_control_pad_count",
              "power_ground_pad_count", "pad_pitch_um", "io_area_mm2", "static_power_w",
              "energy_pj_per_bit", "port_peripheral_mapping")
    missing=[k for k in required if hb.get(k) is None]
    rate=None
    if hb.get("data_pad_count") is not None and hb.get("data_rate_per_pad_gbps") is not None:
        n=hb["data_pad_count"];r=hb["data_rate_per_pad_gbps"]
        if not (math.isfinite(n) and n>0 and int(n)==n and math.isfinite(r) and r>0):
            raise ValueError("HB data connections and rates must be positive")
        rate=n*r/8/1000
    return dict(data_rate_tb_s=rate,missing_fields=missing,
                physically_complete=not missing,
                scope="internal HB only; external xPU DQ rate is a separate path")


def top_cooling_necessary_bound(area_m2, h_w_m2k, ambient_c, maximum_c):
    """Maximum-principle bound: insulated sides, only top convection, positive heat.

    Assumes the whole active stack stays below maximum_c and passive spreader
    has no source. Internal resistances can only reduce this necessary limit.
    """
    if not all(math.isfinite(x) for x in (area_m2,h_w_m2k,ambient_c,maximum_c)):
        raise ValueError("Nonfinite cooling input")
    if area_m2<=0 or h_w_m2k<=0 or maximum_c<=ambient_c:
        raise ValueError("Invalid cooling boundary")
    return area_m2*h_w_m2k*(maximum_c-ambient_c)
