"""Small analytical evidence report; no command-energy or thermal curve fitting."""
import numpy as np
from .hardware_contract import load_profile,power_inventory,geometry
from .organization import values,organization_cost


def report(profile):
    reference=load_profile("configs/platforms/stratum_micro2025.json")
    power=power_inventory(reference);peak=power["mac_at_reported_peak_w"]
    # One aggregate observation cannot identify ACT/PRE/RD/background/refresh.
    # Normalize columns: rank, rather than mixed-unit condition numbers, is
    # the identifiable statement. ACT and PRE also co-vary in row cycling.
    x=np.ones((1,5));rank=int(np.linalg.matrix_rank(x))
    v=values(profile);row=profile["resources"]["row_buffer_bytes"]
    critical=[]
    for paths in (1,2,4,8):
        for target in (8.,16.,30.3407407407,32.):
            critical.append(dict(paths=paths,target_tb_s=target,
                maximum_tFAW_ns_for_ACT_domain_bound=16*4*paths*row/(1000*target),
                maximum_tRRD_ns_for_ACT_domain_bound=16*paths*row/(1000*target),
                minimum_useful_bytes_per_ACT_for_bank_bound=target*1000*34.56/256,
                scope="necessary no-refresh bounds, fixed domain assumptions; not achieved throughput"))
    return dict(reference_accounting=power,
        activity_ratio_if_Figure_compute_were_MAC_only=power["figure_compute_group_w"]/peak,
        activity_ratio_status="conditional arithmetic only; Figure15 group scope unresolved; paper says full tensor-core utilization",
        topology_peak_tflops=geometry(reference)["topology_peak_tflops"],
        identifiability=dict(observations=1,unknown_coefficients=["ACT","PRE","RD/WR","background","refresh"],
                            normalized_observation_rank=rank,nullity=5-rank,
                            status="Unidentified; no independent Stratum command-power measurements; no coefficients fitted"),
        critical_ACT_bounds=critical,
        cooling_necessary_total_power_upper_w=60/v["package_top_resistance_k_w"],
        cooling_scope="top-only passive steady network; internal resistances further reduce feasibility",
        area_controls=[organization_cost(profile,k,"shared_area") for k in (1,2,4,8)],
        information_priority=[
            "ACT and Column sharing domains: partitions must be electrically independent to obtain assumed bandwidth gains",
            "Peripheral marginal area and switching cost versus compute/RF density: determines area-optimal K",
            "Cooling and heat-source location: determines whether optimum change is global or spatial",
            "HB port budget: above fastest-tier bank ceiling, extra interface cannot improve that necessary bound"],
        scope="Architecture assumptions and critical-value analysis, not device calibration")
