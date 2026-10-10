"""A bounded Mode-B organization experiment, not a Stratum device simulator."""
import copy
import json
import math
from pathlib import Path

from .hardware_contract import require_prediction_ready
from .model import Fabric,optimize
from .multiphase import optimize_cycle


def load_exploration(path="configs/exploration/hb_npu_v1.json"):
    p=json.loads(Path(path).read_text());require_prediction_ready(p,"architecture_exploration")
    return p


def values(p):return {k:v["value"] for k,v in p["parameters"].items()}


def organization_cost(p,paths,allocation="fixed_compute"):
    v=values(p);r=p["resources"]
    extra=r["lv_periphery_reference_mm2"]*v["replicated_periphery_fraction"]*(paths-1)
    active=r["active_logic_reference_mm2"]+extra+r["hb_reserved_area_mm2"]
    pad_area=(v["hb_data_connections"]+v["hb_control_power_connections"])*v["hb_pitch_um"]**2/1e6
    ref_compute=v["compute_block_reference_mm2"]
    block_area=ref_compute/r["reference_compute_blocks"]*v["compute_block_area_scale"]
    compute_area=block_area*r["reference_compute_blocks"];peak=v["logic_peak_tflops"];blocks=r["reference_compute_blocks"]
    other=r["active_logic_reference_mm2"]-r["lv_periphery_reference_mm2"]-ref_compute
    active+=compute_area-ref_compute
    if allocation=="shared_area":
        remaining=r["logic_area_mm2"]-other-r["hb_reserved_area_mm2"]-(r["lv_periphery_reference_mm2"]+extra)
        blocks_per_tile=max(0,math.floor(remaining/block_area/16))
        blocks=blocks_per_tile*16;compute_area=blocks*block_area
        peak=blocks/r["reference_compute_blocks"]*v["logic_peak_tflops"]
        active=other+r["hb_reserved_area_mm2"]+r["lv_periphery_reference_mm2"]+extra+compute_area
    elif allocation!="fixed_compute":raise ValueError("Unknown area allocation")
    return dict(paths_per_channel=paths,allocation=allocation,compute_blocks=blocks,compute_area_mm2=compute_area,
                compute_peak_tflops=peak,compute_static_w=compute_area*v["compute_static_w_mm2"],
                additional_periphery_mm2=extra,active_area_mm2=active,
                die_area_budget_mm2=r["logic_area_mm2"],hb_grid_area_mm2=pad_area,
                area_feasible=blocks>0 and active<=r["logic_area_mm2"]+1e-9 and pad_area<=r["hb_reserved_area_mm2"],
                periphery_static_w=(r["lv_periphery_reference_mm2"]+extra)*v["periphery_static_w_mm2"],
                extra_dynamic_fraction=v["extra_path_dynamic_fraction"]*(paths-1))


def bounds(p,paths):
    v=values(p);r=p["resources"]
    rc=2.29+27.50+4.77  # sourced fastest-tier row-cycle; active set fits this tier
    row=r["row_buffer_bytes"];channels=r["channels"]
    bank=row*r["banks_per_channel"]/rc/1000*channels
    activation=min(paths*row/v["tRRD_ns"],paths*4*row/v["tFAW_ns"])/1000*channels
    column=min(paths*1.024,2.048)*channels  # common command bus: one1024B RD/0.5ns
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


def lp_config(p,paths,service_tb_s,act_per_byte=None,allocation="fixed_compute"):
    v=values(p);r=p["resources"];cost=organization_cost(p,paths,allocation)
    if not cost["area_feasible"]:raise ValueError("Organization exceeds fixed silicon/HB area budget")
    access=v["access_energy_pj_byte"];activation=access*v["activation_share"]
    transfer=access-activation;logic_transfer=transfer*v["logic_memory_share"]
    act_per_byte=1/r["row_buffer_bytes"]
    # Full-row energy partition is an assumption. It does not independently
    # calibrate ACT/PRE. Additional path switching remains a paid cost.
    dram_energy=transfer-logic_transfer+activation*r["row_buffer_bytes"]*act_per_byte
    logic_energy=logic_transfer*(1+cost["extra_dynamic_fraction"])
    hw=dict(tile_peak_tflops=cost["compute_peak_tflops"]/16,bank_group_peak_tb_s=v["hb_chip_tb_s"]/16,
        internal_bank_group_ceiling_tb_s=service_tb_s/16,independent_banks_per_group=16,
        row_miss_penalty_ns=34.56,read_latency_ns=v["read_latency_ns"],outstanding_per_tile=512,
        transaction_bytes=1024,sram_bytes_per_tile=r["sram_bytes"]/16,
        logic_static_w=(v["logic_background_w"]+cost["periphery_static_w"]+cost["compute_static_w"])/16,
        # Refresh and its worst-case extra row reopenings are per-time costs,
        # not coefficients that incorrectly shrink with thermal throttling.
        dram_static_w=(v["dram_background_w"]+256*v["refresh_nj_per_bank"]/3900+
                       256*activation*r["row_buffer_bytes"]/1000/3900)/16,
        logic_pj_per_flop=v["logic_compute_pj_flop"]+v["logic_other_dynamic_pj_flop"],
        logic_memory_pj_per_byte=logic_energy,dram_pj_per_byte=dram_energy,activation_nj=0.,
        dvfs_fractions=[.25,.5,.75,1.],voltage_floor_fraction=.65,placement_max_fraction=.125,
        mesh_link_tb_s=.25,mesh_hop_latency_ns=2.,mesh_pj_per_byte_hop=.5,fabric_area_fraction=0.,fabric_static_w_per_tile=0.)
    return dict(grid=4,hardware=hw,thermal=thermal_config(p),
                workloads=[dict(name="decode_gemv",batch=1,m=4096,k=4096,element_bytes=2,output_resident_in_logic=True),
                           dict(name="prefill_gemm",batch=32,m=4096,k=4096,element_bytes=2,output_resident_in_logic=True)],
                tilings=[dict(name="full_4k_row_optimized",chunk_bytes=4096,row_miss_fraction=1.)])


def solve(p,paths,service,h,gh,workload,mode,act_per_byte=None,allocation="fixed_compute"):
    cfg=lp_config(p,paths,service,act_per_byte,allocation)
    if workload==2:
        g2=dict(phases=["prefill_gemm","decode_gemv"],tiling=cfg["tilings"][0]["name"],
                resident_weight_bytes=2*4096**2,bank_capacity_bytes=p["resources"]["dram_capacity_bytes"]//16)
        result=optimize_cycle(cfg,g2,h,gh,(1,32),Fabric("local",0),mode,"shared","phase_steady")
        result["workload"]="mixed_shared_1prefill_32decode"
        result["tflops"]=result["useful_tflops"]
    else:
        result=optimize(cfg,h,gh,cfg["workloads"][workload],cfg["tilings"][0],Fabric("local",0),mode,[1/16]*16,"free")
    result["organization_cost"]=organization_cost(p,paths,allocation)
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
        ("compute_area_low",{"compute_block_area_scale":.75}),
        ("compute_area_high",{"compute_block_area_scale":1.25}),
        ("logic_energy_low",{"logic_other_dynamic_pj_flop":0.}),
        ("logic_energy_high",{"logic_other_dynamic_pj_flop":.08}),
        ("periphery_area_low",{"replicated_periphery_fraction":.25}),
        ("periphery_area_high",{"replicated_periphery_fraction":.75}),
        ("bond_resistance_low",{"bond_areal_resistance_mm2_k_w":.5}),
        ("bond_resistance_high",{"bond_areal_resistance_mm2_k_w":2.}),
        ("uniform_cooling",{"cooling_gradient":0.}),
        ("cooling_gradient_high",{"cooling_gradient":.3}),
        ("HB_16",{"hb_chip_tb_s":16.}),("HB_8",{"hb_chip_tb_s":8.})]
    result=[]
    for name,changes in controls:
        q=copy.deepcopy(p)
        for k,x in changes.items():q["parameters"][k]["value"]=x
        require_prediction_ready(q,"architecture_exploration");result.append((name,q))
    return result
