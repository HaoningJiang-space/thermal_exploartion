"""Two explicit energy contracts. Coefficients are assumptions, not fitted devices."""
import math
from .organization import values


def command_energy(p,counts,useful_bytes,duration_ns,paths=2,selector_events=0):
    if useful_bytes<=0 or duration_ns<=0 or selector_events<0:raise ValueError("Invalid trace totals")
    if any(not math.isfinite(n) or n<0 or int(n)!=n for n in counts.values()):raise ValueError("Invalid command counts")
    v=values(p);row=p["resources"]["row_buffer_bytes"]
    row_energy=v["access_energy_pj_byte"]*v["activation_share"]*row
    # 75/25 ACT/PRE partition is an explicit assumption. Full-row ACT+PRE
    # energy agrees with the prior aggregate scale, but is not identifiable.
    act=counts.get("ACT",0)*row_energy*.75
    pre=counts.get("PREpb",0)*row_energy*.25
    # One PREab closes8 physical banks under K32; count actual commands, never
    # charge the same refresh-induced reopen again as a static proxy.
    pre+=counts.get("PREab_rows",counts.get("PREab",0)*(16//paths))*row_energy*.25
    rd=counts.get("RD",0)+counts.get("RDA",0);wr=counts.get("WR",0)+counts.get("WRA",0)
    transfer_pj=(rd+wr*1.2)*1024*v["access_energy_pj_byte"]*(1-v["activation_share"])
    logic_transfer=transfer_pj*v["logic_memory_share"]*(1+v["extra_path_dynamic_fraction"]*(paths-1))
    dram_transfer=transfer_pj*(1-v["logic_memory_share"])
    refresh=counts.get("REFab",0)*(16//paths)*v["refresh_nj_per_bank"]*1000
    selector=selector_events*10.  # 0.01 nJ/selection, assumed control activity
    parts=dict(ACT_pj=act,PRE_pj=pre,DRAM_RD_WR_pj=dram_transfer,Logic_RD_WR_pj=logic_transfer,
               refresh_pj=refresh,Logic_selector_pj=selector)
    return dict(components=parts,total_command_energy_pj=sum(parts.values()),
        dram_dynamic_pj_per_useful_byte=(act+pre+dram_transfer)/useful_bytes,
        logic_dynamic_pj_per_useful_byte=(logic_transfer+selector)/useful_bytes,
        refresh_power_w=refresh/duration_ns/1000,
        ACT_per_useful_byte=counts.get("ACT",0)/useful_bytes,
        evidence="Trace activity multiplied by labeled assumed coefficients; not independent power calibration")
