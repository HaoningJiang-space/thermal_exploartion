"""Independent periodic audit of the frozen, linear RC phase-power model.

Modal propagation is exact for constant power in each segment. An interpolation
error bound from |d²T/dt²| bounds peaks between samples. Material capacities
are explicit uncalibrated assumptions, not HiTS physical validation.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import eigh
from scipy.sparse.linalg import splu

from .thermal import assemble


class PeriodicAudit:
    def __init__(self,cfg,transient):
        self.cfg=cfg;self.grid=cfg["grid"];self.n=self.grid**2;tc=cfg["thermal"]
        area=tc["tile_pitch_m"]**2
        capacity=np.r_[np.full(self.n,transient["silicon_volumetric_capacity_j_m3k"]*area*tc["logic_thickness_m"]),
                       np.full(self.n,transient["silicon_volumetric_capacity_j_m3k"]*area*tc["dram_thickness_m"]),
                       np.full(self.n,transient["lid_volumetric_capacity_j_m3k"]*area*tc["lid_thickness_m"])]
        if min(capacity)<=0:raise ValueError("Positive heat capacities required")
        self.sqrt_mass=np.sqrt(capacity);a=assemble(self.grid,tc)
        scaled=a.toarray()/self.sqrt_mass[:,None]/self.sqrt_mass[None,:]
        self.eigenvalues,self.vectors=eigh(scaled)
        if min(self.eigenvalues)<=0:raise RuntimeError("Thermal operator is not dissipative")
        self.transform=self.vectors/self.sqrt_mass[:,None]
        self.lu=splu(a.tocsc());self.samples=transient["samples_per_segment"]
        self.record={"backend":"independent modal linear-RC audit",
                     "minimum_time_constant_s":float(1/max(self.eigenvalues)),
                     "maximum_time_constant_s":float(1/min(self.eigenvalues)),
                     "modal_operator_relative_residual":float(np.linalg.norm(scaled@self.vectors-self.vectors*self.eigenvalues)/np.linalg.norm(scaled))}

    def audit(self,segments,peak_error_tolerance_c=0.002):
        tc=self.cfg["thermal"];mu=self.eigenvalues;period=sum(s["duration_s"] for s in segments)
        if period<=0:raise ValueError("Positive cycle duration required")
        equilibria=[];beta=np.zeros_like(mu)
        for segment in segments:
            power=np.asarray(segment["power_w"])
            forcing=np.r_[power,np.zeros(self.n)]
            equilibrium=self.lu.solve(forcing)
            z_eq=self.vectors.T@(self.sqrt_mass*equilibrium)
            equilibria.append(z_eq)
            decay=np.exp(-mu*segment["duration_s"])
            beta=decay*beta-np.expm1(-mu*segment["duration_s"])*z_eq
        start=beta/(-np.expm1(-mu*period));initial=start.copy()
        node_lower=np.full(2*self.n,-np.inf);node_upper=node_lower.copy();segment_records=[]
        integral=np.zeros(3*self.n);energy=np.zeros(3*self.n)
        for segment,z_eq in zip(segments,equilibria):
            duration=segment["duration_s"]
            coefficients=self.transform[:2*self.n]*(start-z_eq)[None,:]
            equilibrium=self.transform[:2*self.n]@z_eq
            sample_count=max(9,self.samples)
            while True:
                # Uniform samples plus geometric samples resolve fast modes near transitions.
                times=np.unique(np.r_[0,np.linspace(0,duration,sample_count),
                                      duration*np.geomspace(1e-7,1,sample_count)])
                decays=np.exp(-mu[:,None]*times[None,:])
                temperature=tc["ambient_c"]+equilibrium[:,None]+coefficients@decays
                lower=np.max(temperature,axis=1)
                second_bound=(np.abs(coefficients)*mu[None,:]**2)@decays[:,:-1]
                interval_upper=np.maximum(temperature[:,:-1],temperature[:,1:])+second_bound*np.diff(times)[None,:]**2/8
                upper=np.max(interval_upper,axis=1)
                gap=float(np.max(upper-lower))
                if gap<=peak_error_tolerance_c or sample_count>=8193:break
                sample_count=2*sample_count-1
            if gap>peak_error_tolerance_c:raise RuntimeError("Periodic peak bound did not converge")
            integral+=self.transform@(z_eq*duration+(start-z_eq)*(-np.expm1(-mu*duration))/mu)
            energy+=np.r_[np.asarray(segment["power_w"]),np.zeros(self.n)]*duration
            node_lower=np.maximum(node_lower,lower);node_upper=np.maximum(node_upper,upper)
            segment_records.append({"name":segment["name"],"duration_s":duration,"sample_times":len(times),
                                    "peak_lower_c":float(max(lower)),"peak_upper_c":float(max(upper)),"maximum_interpolation_bound_gap_c":gap})
            start=np.exp(-mu*duration)*start-np.expm1(-mu*duration)*z_eq
        closure=float(np.max(np.abs(self.transform@(start-initial))))
        if closure>1e-6:raise RuntimeError("Periodic thermal closure failed")
        mean_error=float(np.max(np.abs(integral/period-self.lu.solve(energy/period))))
        if mean_error>1e-6:raise RuntimeError("Periodic mean violates steady energy balance")
        return {"logic_peak_lower_c":float(max(node_lower[:self.n])),"logic_peak_upper_c":float(max(node_upper[:self.n])),
                "dram_peak_lower_c":float(max(node_lower[self.n:])),"dram_peak_upper_c":float(max(node_upper[self.n:])),
                "periodic_closure_error_k":closure,"node_peak_lower_c":node_lower.tolist(),"node_peak_upper_c":node_upper.tolist(),
                "segment_audits":segment_records,"period_s":period,
                "mean_energy_balance_error_k":mean_error,
                "scope":"frozen constant phase powers; assumed capacities; fluid DVFS schedules"}

    def pace(self,segments,p0):
        """Stretch all segments and reduce dynamic power to preserve useful work/energy.

        This constructs an admissible schedule in the phase-constant-power model;
        it does not reoptimize transient mapping and is not a measured speedup.
        """
        p0=np.asarray(p0);tc=self.cfg["thermal"]
        def checked(alpha):
            paced=[dict(s,duration_s=s["duration_s"]*alpha,
                        power_w=(p0+(np.asarray(s["power_w"])-p0)/alpha).tolist()) for s in segments]
            r=self.audit(paced)
            feasible=(r["logic_peak_upper_c"]<=tc["logic_limit_c"]+1e-7 and
                      r["dram_peak_upper_c"]<=tc["dram_limit_c"]+1e-7)
            return r,feasible
        raw,feasible=checked(1.0)
        if feasible:return {"factor":1.0,"unpaced":raw,"paced":raw}
        lo=1.0;hi=2.0
        best,feasible=checked(hi)
        while not feasible:
            lo=hi;hi*=2;best,feasible=checked(hi)
            if hi>1e6:raise RuntimeError("Unable to construct a thermally admissible paced cycle")
        # Bisection is only a schedule search; the final upper peak bound is checked.
        for _ in range(18):
            mid=(lo+hi)/2;r,okay=checked(mid)
            if okay:hi=mid;best=r
            else:lo=mid
        return {"factor":hi,"unpaced":raw,"paced":best}
