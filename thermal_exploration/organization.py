"""A bounded Mode-B organization experiment, not a Stratum device simulator."""
import copy
import json
import math
from pathlib import Path

from .hardware_contract import require_prediction_ready
from .model import Fabric,optimize


def load_exploration(path="configs/exploration/hb_npu_v1.json"):
    p=json.loads(Path(path).read_text());require_prediction_ready(p,"architecture_exploration")
    return p


def values(p):return {k:v["value"] for k,v in p["parameters"].items()}


def organization_cost(p,paths):
    v=values(p);r=p["resources"]
    extra=r["lv_periphery_reference_mm2"]*v["replicated_periphery_fraction"]*(paths-1)
    active=r["active_logic_reference_mm2"]+extra+r["hb_reserved_area_mm2"]
    pad_area=(v["hb_data_connections"]+v["hb_control_power_connections"])*v["hb_pitch_um"]**2/1e6
    return dict(paths_per_channel=paths,additional_periphery_mm2=extra,active_area_mm2=active,
                die_area_budget_mm2=r["logic_area_mm2"],hb_grid_area_mm2=pad_area,
                area_feasible=active<=r["logic_area_mm2"] and pad_area<=r["hb_reserved_area_mm2"],
                periphery_static_w=(r["lv_periphery_reference_mm2"]+extra)*v["periphery_static_w_mm2"],
                extra_dynamic_fraction=v["extra_path_dynamic_fraction"]*(paths-1))


def bounds(p,paths):
    v=values(p);r=p["resources"]
    rc=2.29+27.50+4.77  # sourced fastest-tier row-cycle; active set fits this tier
    row=r["row_buffer_bytes"];channels=r["channels"]
    bank=row*r["banks_per_channel"]/rc/1000*channels
    activation=min(paths*row/v["tRRD_ns"],paths*4*row/v["tFAW_ns"])/1000*channels
    column=paths*1.024*channels  # 1024-byte payload /1 ns per independent path
    hb=v["hb_data_connections"]*1/8/1000
    if v["hb_chip_tb_s"]>hb:raise ValueError("HB budget exceeds fixed connections at maximum rate")
    return dict(bank_cycle_tb_s=bank,activation_domain_tb_s=activation,column_tb_s=column,
                hb_tb_s=v["hb_chip_tb_s"],necessary_service_tb_s=min(bank,activation,column,v["hb_chip_tb_s"]),
                scope="Independent necessary bounds; no refresh, command bus, buffering or dependencies")


def thermal_config(p):
    v=values(p);a=p["resources"]["logic_area_mm2"]*1e-6
    return dict(ambient_c=25.,logic_limit_c=85.,dram_limit_c=85.,tile_pitch_m=math.sqrt(a)/4,
        logic_thickness_m=50e-6,dram_thickness_m=30e-6,lid_thickness_m=1e-3,
        silicon_k_w_mk=100.,lid_k_w_mk=400.,bond_thickness_m=v["bond_areal_resistance_mm2_k_w"]*1e-6,
        bond_k_w_mk=1.,tim_thickness_m=20e-6,tim_k_w_mk=4.,
        convection_w_m2k=1/(v["package_top_resistance_k_w"]*a),cooling_gradient=v["cooling_gradient"],vertical_scale=1.)


def lp_config(p,paths,service_tb_s,act_per_byte=None):
    v=values(p);r=p["resources"];cost=organization_cost(p,paths)
    if not cost["area_feasible"]:raise ValueError("Organization exceeds fixed silicon/HB area budget")
    access=v["access_energy_pj_byte"];activation=access*v["activation_share"]
    transfer=access-activation;logic_transfer=transfer*v["logic_memory_share"]
    if act_per_byte is None:act_per_byte=1/r["row_buffer_bytes"]
    # Full-row energy partition is an assumption. It does not independently
    # calibrate ACT/PRE. Additional path switching remains a paid cost.
    dram_energy=transfer-logic_transfer+activation*r["row_buffer_bytes"]*act_per_byte
    logic_energy=logic_transfer*(1+cost["extra_dynamic_fraction"])
    hw=dict(tile_peak_tflops=v["logic_peak_tflops"]/16,bank_group_peak_tb_s=v["hb_chip_tb_s"]/16,
        internal_bank_group_ceiling_tb_s=service_tb_s/16,independent_banks_per_group=16,
        row_miss_penalty_ns=34.56,read_latency_ns=v["read_latency_ns"],outstanding_per_tile=64,
        transaction_bytes=1024,sram_bytes_per_tile=r["sram_bytes"]/16,
        logic_static_w=(v["logic_background_w"]+cost["periphery_static_w"])/16,
        dram_static_w=v["dram_background_w"]/16,
        logic_pj_per_flop=v["logic_compute_pj_flop"]+v["logic_other_dynamic_pj_flop"],
        logic_memory_pj_per_byte=logic_energy,dram_pj_per_byte=dram_energy,activation_nj=0.,
        dvfs_fractions=[.25,.5,.75,1.],voltage_floor_fraction=.65,placement_max_fraction=.125,
        mesh_link_tb_s=.25,mesh_hop_latency_ns=2.,mesh_pj_per_byte_hop=.5,fabric_area_fraction=0.,fabric_static_w_per_tile=0.)
    return dict(grid=4,hardware=hw,thermal=thermal_config(p),
                workloads=[dict(name="decode_gemv",batch=1,m=4096,k=4096,element_bytes=2,output_resident_in_logic=True),
                           dict(name="prefill_gemm",batch=32,m=4096,k=4096,element_bytes=2,output_resident_in_logic=True)],
                tilings=[dict(name="full_4k_row_optimized",chunk_bytes=4096,row_miss_fraction=1.)])


def solve(p,paths,service,h,gh,workload,mode,act_per_byte=None):
    cfg=lp_config(p,paths,service,act_per_byte)
    result=optimize(cfg,h,gh,cfg["workloads"][workload],cfg["tilings"][0],Fabric("local",0),mode,[1/16]*16,"free")
    result["organization_cost"]=organization_cost(p,paths)
    result["prediction_mode"]="conditional_architecture_exploration"
    result["execution_scope"]="Steady divisible-work relaxation; common optimized placement/DVFS; not an implemented NPU"
    return result


def scenarios(p):
    # Prespecified one-at-a-time controls; all points and failures are retained.
    controls=[("default",{}),("energy_low",{"access_energy_pj_byte":2.7456}),
        ("energy_high",{"access_energy_pj_byte":4.1184}),
        ("cooling_strong",{"package_top_resistance_k_w":.1}),
        ("cooling_weak",{"package_top_resistance_k_w":.5}),
        ("logic_memory_share_low",{"logic_memory_share":.3}),
        ("logic_memory_share_high",{"logic_memory_share":.8}),
        ("periphery_cost_high",{"extra_path_dynamic_fraction":.2,"periphery_static_w_mm2":.2}),
        ("HB_16",{"hb_chip_tb_s":16.}),("HB_8",{"hb_chip_tb_s":8.})]
    result=[]
    for name,changes in controls:
        q=copy.deepcopy(p)
        for k,x in changes.items():q["parameters"][k]["value"]=x
        require_prediction_ready(q,"architecture_exploration");result.append((name,q))
    return result
