"""G2: minimize fixed-work cycle time with a shared resident weight layout.

Integrated work (TFLOP), durations (s), layouts (fractions), and transported
weight fractions are LP variables. Known phase work removes rate/layout
bilinearity. Migration includes both transitions of a periodic two-phase cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import sparse
from scipy.optimize import linprog

from .model import Fabric, kernel, route
from .thermal import THERMAL_NAMES, layer_response, thermal_control


@dataclass
class ServiceBlock:
    flows: list
    paths: list
    duty: np.ndarray
    bank: np.ndarray
    queue: np.ndarray
    power: np.ndarray
    shards: np.ndarray
    links: list
    link_load: np.ndarray
    bank_bw: float
    intensity: float


def service_block(cfg, workload, tiling, fabric):
    hw=cfg["hardware"]; grid=cfg["grid"]; n=grid**2
    kr=kernel(workload,tiling); intensity=kr["intensity"]
    if 2*kr["chunk_bytes"] > hw["sram_bytes_per_tile"]:
        raise ValueError("Private SRAM double-buffer capacity exceeded")
    flows=[];paths=[]
    for i in range(n):
        for j in range(n):
            path=route(i,j,grid)
            if fabric.radius is None or len(path)<=fabric.radius:
                for f in hw["dvfs_fractions"]:
                    flows.append((i,j,f));paths.append(path)
    v=len(flows)
    duty=np.zeros((n,v));bank=np.zeros((n,v));queue=np.zeros((n,v));power=np.zeros((2*n,v));shards=np.zeros((n,v))
    links=sorted({edge for path in paths for edge in path})
    link_idx={edge:i for i,edge in enumerate(links)};link_load=np.zeros((len(links),v))
    dram_energy=hw["dram_pj_per_byte"]+hw["activation_nj"]*1000*kr["row_miss_fraction"]/kr["chunk_bytes"]
    bank_bw=1/(1/hw["bank_group_peak_tb_s"]+hw["row_miss_penalty_ns"]*1000
               *kr["row_miss_fraction"]/(kr["chunk_bytes"]*hw["independent_banks_per_group"]))
    for c,((i,j,f),path) in enumerate(zip(flows,paths)):
        duty[i,c]=1/(hw["tile_peak_tflops"]*(1-fabric.area_fraction)*f)
        bank[j,c]=1/intensity;shards[j,c]=1
        latency=hw["read_latency_ns"]+(len(path)*hw["mesh_hop_latency_ns"] if fabric.paid else 0)
        queue[i,c]=1000*latency/(intensity*hw["transaction_bytes"])
        voltage=hw["voltage_floor_fraction"]+(1-hw["voltage_floor_fraction"])*f
        power[i,c]=hw["logic_pj_per_flop"]*voltage**2
        power[n+j,c]=dram_energy/intensity
        if fabric.paid:
            for edge in path:
                link_load[link_idx[edge],c]=1/intensity
                for endpoint in edge:
                    power[endpoint,c]+=hw["mesh_pj_per_byte_hop"]/(2*intensity)
    return ServiceBlock(flows,paths,duty,bank,queue,power,shards,links,link_load,bank_bw,intensity)


def g2_fabrics(hw):
    a=hw["fabric_area_fraction"];s=hw["fabric_static_w_per_tile"]
    return [Fabric("local",0),Fabric("neighbor_ideal",1),Fabric("global_ideal",None),
            Fabric("neighbor_paid",1,True,a,s),Fabric("mesh_paid",None,True,a,s),
            Fabric("local_matched",0,True,a,s)]


def optimize_cycle(cfg, g2, h, gh, repetitions, fabric, thermal_mode,
                   placement="shared", thermal_regime="phase_steady", fixed_layouts=None):
    if placement not in ("independent_oracle","shared","migration"):
        raise ValueError(placement)
    if thermal_regime not in ("phase_steady","cycle_average"):
        raise ValueError("Invalid thermal model")
    if len(repetitions)!=2 or any(int(r)!=r or r<=0 for r in repetitions):
        raise ValueError("Exactly two phases must each complete positive integer repetitions")
    lookup={w["name"]:w for w in cfg["workloads"]}
    phases=[lookup[name] for name in g2["phases"]]
    tiling=next(t for t in cfg["tilings"] if t["name"]==g2["tiling"])
    weights=[w["m"]*w["k"]*w["element_bytes"] for w in phases]
    if weights != [g2["resident_weight_bytes"]]*2:
        raise ValueError("Both phases must reuse the same resident weight tensor")
    blocks=[service_block(cfg,w,tiling,fabric) for w in phases]
    work=np.asarray([kernel(w,tiling)["flops"]*r/1e12 for w,r in zip(phases,repetitions)])
    grid=cfg["grid"];n=grid**2;hw=cfg["hardware"];tc=cfg["thermal"]
    cap=min(g2["bank_capacity_bytes"]/g2["resident_weight_bytes"],hw["placement_max_fraction"])
    if cap*n < 1-1e-12:
        raise ValueError("Resident weight exceeds common Bank capacity budget")
    p0=np.r_[np.full(n,hw["logic_static_w"]+fabric.static_w),np.full(n,hw["dram_static_w"])]
    hm=thermal_control(h,gh,thermal_mode)
    allowed=np.r_[np.full(n,tc["logic_limit_c"]-tc["ambient_c"]),np.full(n,tc["dram_limit_c"]-tc["ambient_c"])]
    room=allowed-hm@p0
    if thermal_mode and min(room)<0:
        raise RuntimeError("Static thermal infeasibility")
    sizes=[len(b.flows) for b in blocks];offsets=[0,sizes[0]]
    cursor=sum(sizes);t_idx=[cursor,cursor+1];cursor+=2
    layout_idx=[np.arange(cursor,cursor+n)];cursor+=n
    if placement=="shared":
        layout_idx*=2
    else:
        layout_idx.append(np.arange(cursor,cursor+n));cursor+=n
    moves=[(i,j) for i in range(n) for j in range(n) if i!=j]
    z_idx=[];d_idx=[]
    if placement=="migration":
        for _ in range(2):
            z_idx.append(np.arange(cursor,cursor+len(moves)));cursor+=len(moves)
            d_idx.append(cursor);cursor+=1
    nv=cursor;objective=np.zeros(nv);objective[t_idx+d_idx]=1
    au=[];bu=[];ae=[];be=[]

    def constraint(matrix, columns, t, budget, equality=False, rhs=None):
        matrix=np.asarray(matrix);rows=np.zeros((len(matrix),nv));rows[:,columns]=matrix
        if t is not None:
            rows[:,t]=-np.asarray(budget)
        if equality:
            ae.append(sparse.csr_matrix(rows));be.append(np.zeros(len(matrix)) if rhs is None else rhs)
        else:
            au.append(sparse.csr_matrix(rows));bu.append(np.zeros(len(matrix)) if rhs is None else rhs)

    energy_rows=[];duration_indices=[]
    for s,b in enumerate(blocks):
        columns=np.arange(offsets[s],offsets[s]+sizes[s]);t=t_idx[s]
        constraint(b.duty,columns,t,np.ones(n))
        constraint(b.bank,columns,t,np.full(n,b.bank_bw))
        constraint(b.queue,columns,t,np.full(n,hw["outstanding_per_tile"]))
        if fabric.paid and b.links:
            constraint(b.link_load,columns,t,np.full(len(b.links),hw["mesh_link_tb_s"]))
        rows=np.zeros((n,nv));rows[:,columns]=b.shards/work[s]
        rows[:,layout_idx[s]]-=np.eye(n)
        ae.append(sparse.csr_matrix(rows));be.append(np.zeros(n))
        energy=np.zeros((2*n,nv));energy[:,columns]=b.power
        energy_rows.append(energy);duration_indices.append(t)
        if thermal_mode and thermal_regime=="phase_steady":
            constraint(hm@b.power,columns,t,room)
    for indices in {tuple(x) for x in layout_idx}:
        rows=np.zeros((1,nv));rows[0,list(indices)]=1
        ae.append(sparse.csr_matrix(rows));be.append(np.ones(1))

    move_energy=None;move_bank=None;move_link=None;move_queue=None
    all_links=sorted({edge for i,j in moves for edge in route(j,i,grid)})
    if placement=="migration":
        mc=g2["migration"];weight_tb=g2["resident_weight_bytes"]/1e12
        balance=np.zeros((n,len(moves)));move_bank=np.zeros((n,len(moves)))
        move_queue=np.zeros((n,len(moves)));move_link=np.zeros((len(all_links),len(moves)))
        link_lookup={e:i for i,e in enumerate(all_links)};move_energy=np.zeros((2*n,len(moves)))
        act_pj=mc["activation_nj"]*1000*mc["row_miss_fraction"]/mc["chunk_bytes"]
        for c,(src,dst) in enumerate(moves):
            balance[src,c]=1;balance[dst,c]=-1
            move_bank[src,c]+=weight_tb;move_bank[dst,c]+=weight_tb
            path=route(dst,src,grid)
            latency=hw["read_latency_ns"]+len(path)*mc["hop_latency_ns"]
            move_queue[src,c]=weight_tb*1000*latency/mc["transaction_bytes"]
            move_energy[n+src,c]=weight_tb*(mc["dram_read_pj_per_byte"]+act_pj)
            move_energy[n+dst,c]=weight_tb*(mc["dram_write_pj_per_byte"]+act_pj)
            for edge in path:
                move_link[link_lookup[edge],c]=weight_tb
                for endpoint in edge:
                    move_energy[endpoint,c]+=weight_tb*mc["pj_per_byte_hop"]/2
        for transition in range(2):
            # 0: prefill -> decode; 1: decode -> next prefill. Both are charged.
            src=transition;dst=1-transition;indices=z_idx[transition];d=d_idx[transition]
            rows=np.zeros((n,nv));rows[:,indices]=balance
            rows[:,layout_idx[src]]-=np.eye(n);rows[:,layout_idx[dst]]+=np.eye(n)
            ae.append(sparse.csr_matrix(rows));be.append(np.zeros(n))
            constraint(move_bank,indices,d,np.full(n,blocks[0].bank_bw))
            constraint(move_queue,indices,d,np.full(n,mc["outstanding_per_bank"]))
            constraint(move_link,indices,d,np.full(len(all_links),mc["link_tb_s"]))
            energy=np.zeros((2*n,nv));energy[:,indices]=move_energy
            energy_rows.append(energy);duration_indices.append(d)
            if thermal_mode and thermal_regime=="phase_steady":
                constraint(hm@move_energy,indices,d,room)
    if thermal_mode and thermal_regime=="cycle_average":
        rows=hm@sum(energy_rows);rows[:,duration_indices]-=room[:,None]
        au.append(sparse.csr_matrix(rows));bu.append(np.zeros(2*n))
    bounds=[(0,None)]*nv
    for indices in layout_idx:
        for j in indices:
            bounds[j]=(0,cap)
    if fixed_layouts is not None:
        fixed=np.asarray(fixed_layouts,dtype=float)
        if (fixed.shape!=(2,n) or not np.all(np.isfinite(fixed)) or min(fixed.ravel())<0
                or max(fixed.ravel())>cap+1e-12 or not np.allclose(fixed.sum(axis=1),1)):
            raise ValueError("Invalid fixed layout verification fixture")
        if placement=="shared" and not np.allclose(fixed[0],fixed[1]):
            raise ValueError("Shared placement cannot use different fixed layouts")
        for s,indices in enumerate(layout_idx):
            for j,value in zip(indices,fixed[s]):bounds[j]=(float(value),float(value))
    au=sparse.vstack(au,format="csr");bu=np.concatenate(bu)
    ae=sparse.vstack(ae,format="csr");be=np.concatenate(be)
    result=linprog(objective,A_ub=au,b_ub=bu,A_eq=ae,b_eq=be,bounds=bounds,method="highs",
                   options={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9})
    if not result.success:
        raise RuntimeError(f"G2 LP failed: {result.message}")
    lp_solves=1
    if placement=="migration":
        # Fix the optimal total time, then remove gratuitous transfer cycles and
        # idle time placed in migration slots by a degenerate primary optimum.
        secondary=np.zeros(nv);secondary[d_idx]=1/result.fun
        for indices in z_idx:secondary[indices]=1
        fixed_time=sparse.csr_matrix((objective/result.fun)[None,:])
        refined=linprog(secondary,A_ub=au,b_ub=bu,
                        A_eq=sparse.vstack([ae,fixed_time],format="csr"),b_eq=np.r_[be,1.0],
                        bounds=bounds,method="highs",
                        options={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9})
        if not refined.success:raise RuntimeError(f"G2 migration tie-break failed: {refined.message}")
        result=refined;lp_solves+=1
    x=result.x
    # Normalize integrated constraint errors by their physical scale; verify
    # completed fractions independently instead of hiding errors in tiny work.
    work_error=0.0
    for s,b in enumerate(blocks):
        vals=x[offsets[s]:offsets[s]+sizes[s]]
        work_error=max(work_error,float(np.max(np.abs(b.shards@vals/work[s]-x[layout_idx[s]]))))
    violation=max(0.0,float(np.max(au@x-bu)),float(np.max(np.abs(ae@x-be))))
    if violation>1e-7 or work_error>1e-6:
        raise RuntimeError("G2 original work/LP constraints violated")
    total_time=float(objective@x)
    phase_records=[];segments=[]
    for s,b in enumerate(blocks):
        vals=x[offsets[s]:offsets[s]+sizes[s]];duration=float(x[t_idx[s]])
        if duration<=0:
            raise RuntimeError("Positive phase work has zero duration")
        power=p0+b.power@vals/duration
        mapping=np.zeros((n,n))
        for c,(i,j,f) in enumerate(b.flows):mapping[i,j]+=vals[c]
        segments.append({"name":phases[s]["name"],"duration_s":duration,"power_w":power.tolist()})
        phase_records.append({"name":phases[s]["name"],"repetitions":int(repetitions[s]),
                              "required_work_tflop":float(work[s]),"completed_work_tflop":float(vals.sum()),
                              "duration_s":duration,"tflops":float(work[s]/duration),
                              "bank_fractions":x[layout_idx[s]].tolist(),
                              "used_bandwidth_tb_s":float((b.bank@vals).sum()/duration),
                              "hb_peak_utilization":float((b.bank@vals).sum()/duration/(n*hw["bank_group_peak_tb_s"])),
                              "logic_power_w":float(power[:n].sum()),"dram_power_w":float(power[n:].sum()),
                              "power_w":power.tolist(),"spatial_steady_temperature_c":(tc["ambient_c"]+h@power).tolist(),
                              "remote_work_fraction":float(sum(vals[c] for c,path in enumerate(b.paths) if path)/work[s]),
                              "mapping_work_tflop":mapping.tolist()})
    migration_records=[]
    if placement=="migration":
        ordered=[]
        for s in range(2):
            ordered.append(segments[s]);z=x[z_idx[s]];duration=float(x[d_idx[s]])
            moved=float(z.sum()*g2["resident_weight_bytes"])
            if duration>1e-15:
                power=p0+move_energy@z/duration
                ordered.append({"name":f"migration_{s}_to_{1-s}","duration_s":duration,"power_w":power.tolist()})
            migration_records.append({"source_phase":s,"destination_phase":1-s,"moved_bytes":moved,
                                      "minimum_layout_change_bytes":float(np.abs(x[layout_idx[s]]-x[layout_idx[1-s]]).sum()/2*g2["resident_weight_bytes"]),
                                      "duration_s":duration,"transfer_fractions":z.tolist(),
                                      "dynamic_energy_j":float((move_energy@z).sum()),
                                      "total_read_write_bytes":2*moved})
        segments=ordered
    total_energy=p0*total_time+sum(e@x for e in energy_rows)
    average_power=total_energy/total_time
    return {"fabric":fabric.name,"placement":placement,"thermal_mode":thermal_mode,"thermal_regime":thermal_regime,
            "thermal_model":THERMAL_NAMES[thermal_mode],
            "cycle_time_s":total_time,"cycles_per_s":1/total_time,
            "useful_tflops":float(work.sum()/total_time),"required_work_tflop":work.tolist(),
            "phases":phase_records,"segments":segments,"migrations":migration_records,
            "migration_time_s":float(sum(x[d_idx])) if d_idx else 0.0,
            "migration_moved_bytes":sum(m["moved_bytes"] for m in migration_records),
            "lp_solves":lp_solves,
            "average_power_w":average_power.tolist(),
            "average_spatial_temperature_c":(tc["ambient_c"]+h@average_power).tolist(),
            "average_layer_temperature_c":(tc["ambient_c"]+layer_response(h)@average_power).tolist(),
            "original_constraint_max_violation":violation,"phase_fraction_error":work_error,
            "resident_weight_bytes":g2["resident_weight_bytes"],"bank_capacity_bytes":g2["bank_capacity_bytes"],
            "migration_cost_scope":"serial common DMA mesh; both DRAM endpoints; no startup/arbiter overhead"}
