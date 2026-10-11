"""Conditional event-energy / periodic-RC audit of H3 known baselines.

This evaluates existing organizations; it is not an unearned H4 hardware claim.
"""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
from .organization import load_exploration,values,thermal_config,organization_cost
from .periodic import PeriodicAudit
from .thermal import response,layer_response
from .run import revision

COEFFICIENTS=dict(mac_pj_flop=.302,vector_pj_op=.1,sram_pj_byte=.15,noc_pj_byte_hop=.5,
    fifo_and_steering_pj_byte=.1,fifo_steering_area_mm2=.8,fifo_steering_static_w=.08)
SCENARIOS={'default':(1.,.3),'energy_low':(.8,.3),'energy_high':(1.2,.3),'cooling_strong':(1.,.2),'cooling_weak':(1.,.6)}


def trace_power(directory,r,bins=64):
    """Integrate each event energy exactly into bins; no short phase is steady."""
    ticks=r['ticks'];energy=np.zeros((bins,32));ledger={};removed=0;stream=r['variant'].startswith('known_fifo')
    def deposit(start,finish,tile,joules):
        if joules==0:return
        lo=min(bins-1,int(start*bins/ticks));hi=min(bins-1,int(max(start,finish-1)*bins/ticks))
        if finish==start:energy[lo,tile]+=joules;return
        for b in range(lo,hi+1):
            overlap=max(0,min(finish,(b+1)*ticks/bins)-max(start,b*ticks/bins))
            energy[b,tile]+=joules*overlap/(finish-start)
    with gzip.open(directory/r['events_file'],'rt') as f:
        for line in f:
            e=json.loads(line);kind=e['kind'];work=e['work'];tile=e['tile'];a,b=e['start_tick'],e['finish_tick']
            coeff=0
            if kind=='dram':
                total=work*3.432e-12;logic=total*.8*.6;dram=total-logic
                deposit(a,b,tile,logic);deposit(a,b,tile+16,dram);ledger['memory_access_j']=ledger.get('memory_access_j',0)+total
                if stream:
                    extra=work*COEFFICIENTS['fifo_and_steering_pj_byte']*1e-12
                    deposit(a,b,tile,extra);ledger['fifo_steering_j']=ledger.get('fifo_steering_j',0)+extra
                continue
            if kind=='mac':coeff=COEFFICIENTS['mac_pj_flop']
            elif kind=='vector':coeff=COEFFICIENTS['vector_pj_op']
            elif kind=='link':coeff=COEFFICIENTS['noc_pj_byte_hop']
            elif kind in ('sram_read','sram_write'):
                # The known fusion timing probe retains old activity in its
                # ledger; physical audit removes ONLY its declared2KiB spills.
                if r['variant']=='known_fifo_known_fusion' and e['stage'] in ('up','down','expert_up','expert_down','attention_local'):
                    removed+=min(2048,work);work=max(0,work-2048)
                coeff=COEFFICIENTS['sram_pj_byte']
            joules=work*coeff*1e-12;deposit(a,b,tile,joules)
            ledger[kind+'_j']=ledger.get(kind+'_j',0)+joules
    if not np.isclose(energy.sum(),sum(ledger.values()),rtol=1e-9,atol=1e-12):raise ValueError('Event energy bins do not close')
    return energy,ledger,removed


def cold_peak(audit,segments):
    z=np.zeros_like(audit.eigenvalues);peak=25.
    for s in segments:
        power=np.asarray(s['power_w']);eq=audit.lu.solve(np.r_[power,np.zeros(audit.n)])
        zeq=audit.vectors.T@(audit.sqrt_mass*eq);times=np.linspace(0,s['duration_s'],17)
        t=25+audit.transform[:2*audit.n]@(zeq[:,None]+(z-zeq)[:,None]*np.exp(-audit.eigenvalues[:,None]*times))
        peak=max(peak,float(t.max()));z=zeq+(z-zeq)*np.exp(-audit.eigenvalues*s['duration_s'])
    return peak


def idle_pace(audit,segments,p0):
    """Keep active power/rates fixed and insert idle intervals after each bin.

    This is a conditional duty-cycle construction, not a fitted DVFS curve.
    Bin boundaries approximate drainable event checkpoints; no new controller
    timing or voltage-energy relation is inferred from temperatures.
    """
    def checked(alpha):
        paced=[]
        for segment in segments:
            paced.append(segment)
            if alpha>1: paced.append(dict(name=segment['name']+'_idle',duration_s=segment['duration_s']*(alpha-1),power_w=p0.tolist()))
        result=audit.audit(paced)
        return result,result['logic_peak_upper_c']<=85+1e-7 and result['dram_peak_upper_c']<=85+1e-7
    raw,feasible=checked(1.)
    if feasible:return dict(factor=1.,unpaced=raw,paced=raw)
    lo=1.;hi=2.;best,feasible=checked(hi)
    while not feasible:
        lo=hi;hi*=2;best,feasible=checked(hi)
        if hi>1e6:raise ValueError('Active-bin burst itself exceeds thermal limit; refine checkpoints')
    for _ in range(18):
        mid=(lo+hi)/2;result,okay=checked(mid)
        if okay:hi=mid;best=result
        else:lo=mid
    return dict(factor=hi,unpaced=raw,paced=best)


def evaluate(r,energy,ledger,p,cooling,scale=1.,backend='scipy',bins=64,grid=4,pacing_mode='uniform',physical_contract=None):
    if cooling<=0 or scale<=0 or r['time_us']<=0 or np.any(energy<0) or energy.shape!=(bins,32):raise ValueError('Invalid physical energy/time/boundary')
    profile=json.loads(json.dumps(p));profile['parameters']['package_top_resistance_k_w']['value']=cooling
    tc=thermal_config(profile);cost=organization_cost(profile,2,'fixed_compute');stream=r['variant'].startswith('known_fifo')
    if grid not in (4,8):raise ValueError('Unsupported convergence grid')
    tc['tile_pitch_m']*=4/grid
    active_area=cost['active_area_mm2']+(COEFFICIENTS['fifo_steering_area_mm2'] if stream else 0)
    static_delta=0.
    if physical_contract is not None:
        active_area=physical_contract['active_area_mm2']
        if active_area+physical_contract['reserved_unidentified_area_mm2']>121+1e-8:raise ValueError('Committed area exceeds budget')
        static_delta=physical_contract['variable_area_static_delta_w']
    if active_area>121:raise ValueError('Area budget exceeded')
    # All private storage is reallocated within36MiB; no capacity oracle is
    # evaluated as paid hardware. Background has explicit physical location.
    p0=np.r_[np.full(16,(3.2+cost['periphery_static_w']+.5+(COEFFICIENTS['fifo_steering_static_w'] if stream else 0)+static_delta)/16),np.full(16,4.8/16)]
    duration=r['time_us']*1e-6;dt=duration/bins
    powers=p0[None,:]+energy*scale/dt
    if grid==8:
        def refined(x):return np.repeat(np.repeat(x.reshape(-1,2,4,4),2,axis=2),2,axis=3).reshape(-1,128)/4
        powers=refined(powers);p0=refined(p0)[0]
    n=grid*grid
    h,_,numerical=response(grid,tc,backend);mean=powers.mean(axis=0)
    spatial_steady=25+h@mean;layer_steady=25+layer_response(h)@mean
    cfg=dict(grid=grid,thermal=tc);capacity=dict(silicon_volumetric_capacity_j_m3k=1.63e6,lid_volumetric_capacity_j_m3k=3.45e6,samples_per_segment=9)
    audit=PeriodicAudit(cfg,capacity)
    segments=[dict(name='bin'+str(i),duration_s=dt,power_w=power.tolist()) for i,power in enumerate(powers)]
    if pacing_mode not in ('uniform','idle_bins'):raise ValueError('Unknown pacing construction')
    paced=idle_pace(audit,segments,p0) if pacing_mode=='idle_bins' else audit.pace(segments,p0)
    factor=paced['factor'];energy_token=(energy.sum()*scale+p0.sum()*duration*factor)/r['meta']['tokens']
    dynamic_mean=mean-p0;layer=layer_response(h)
    base_temp=25+layer@p0;layer_dynamic=layer@dynamic_mean
    if base_temp.max()>=85:raise ValueError('Background alone violates layer thermal limit')
    layer_pace=max(1.,float(np.max(layer_dynamic/(85-base_temp))))
    spatial_base=25+h@p0;spatial_dynamic=h@dynamic_mean
    if spatial_base.max()>=85:raise ValueError('Background alone violates spatial limit')
    spatial_pace=max(1.,float(np.max(spatial_dynamic/(85-spatial_base))))
    return dict(workload=r['workload'],variant=r['variant'],time_us=r['time_us'],unpaced_tokens_s=r['meta']['tokens']/duration,
        t2_spatial_steady_pace_factor=spatial_pace,t2_spatial_steady_tokens_s=r['meta']['tokens']/(duration*spatial_pace),
        t1_layer_pace_factor=layer_pace,t1_layer_sustainable_tokens_s=r['meta']['tokens']/(duration*layer_pace),pacing_mode=pacing_mode,
        sustainable_tokens_s=r['meta']['tokens']/(duration*factor),pace_factor=factor,energy_per_token_j=float(energy_token),
        logic_mean_w=float(mean[:n].sum()),dram_mean_w=float(mean[n:].sum()),power_cooling_necessary_bound_w=60/cooling,
        t1_layer_steady_peak_c=float(layer_steady.max()),t2_steady_peak_c=float(spatial_steady.max()),cold_token_sampled_peak_c=cold_peak(audit,segments),
        periodic_logic_peak_c=paced['paced']['logic_peak_upper_c'],periodic_dram_peak_c=paced['paced']['dram_peak_upper_c'],
        node_peak_upper_c=paced['paced']['node_peak_upper_c'],mean_power_w=mean.tolist(),
        unpaced_periodic_peak_c=max(paced['unpaced']['logic_peak_upper_c'],paced['unpaced']['dram_peak_upper_c']),
        area_mm2=active_area,sram_bytes=physical_contract['sram_bytes'] if physical_contract else 36*2**20,energy_ledger_j=ledger,energy_scale=scale,cooling_top_k_w=cooling,grid=grid,bins=bins,
        thermal_numerical=numerical,periodic=audit.record,energy_balance_error_k=paced['paced']['mean_energy_balance_error_k'],
        scope='Conditional event-derived periodic RC schedule, uniform pacing; not measured tokens/s, calibrated package or optimal thermal scheduler')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--h3',required=True);ap.add_argument('--output',required=True);ap.add_argument('--thermal-backend',choices=('hits','scipy'),default='scipy');a=ap.parse_args()
    directory=Path(a.h3);out=Path(a.output)
    if out.exists():raise ValueError('Never overwrite evidence')
    out.mkdir(parents=True);p=load_exploration();records=[]
    (out/'assumptions.json').write_text(json.dumps(dict(coefficients=COEFFICIENTS,scenarios=SCENARIOS,
        source_commit=revision(),memory_energy_scope='Aggregate full-row anchor, not independent ACT/PRE calibration; HB/peripheral included, no double charge',
        physical_heat_scope='Equivalent DRAM layer, memory array vs logic peripheral split; tier-dependent thermal source depth unresolved',
        disabled_feedback=['Temperature-dependent refresh','Leakage-temperature curves'],thermal_backend=a.thermal_backend),indent=2)+'\n')
    all_results=json.loads((directory/'summary.json').read_text())
    for r in all_results:
        if r.get('status')=='FAILED_FINITE_SCHEDULE' or r['variant'] not in ('sram_baseline','known_fifo_known_fusion'):continue
        energy,ledger,removed=trace_power(directory,r)
        for name,(scale,cooling) in SCENARIOS.items():
            result=evaluate(r,energy,ledger,p,cooling,scale,a.thermal_backend);result.update(scenario=name,removed_declared_sram_spill_bytes=removed)
            records.append(result);print(r['workload'],r['variant'],name,result['sustainable_tokens_s'],result['periodic_logic_peak_c'],flush=True)
        (out/'partial.json').write_text(json.dumps(records,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__=='__main__':main()
