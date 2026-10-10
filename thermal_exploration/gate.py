"""Conservative screening labels, never a claim of validated hardware novelty."""

GATE_POLICY = "placement-cost-layer-control-v2"


def classify(*, placement, paid, controls_complete, net_t0, net_t1_layer,
             net_t2, matched_t2, speedup_gate=1.05, interaction_gate=1.01):
    spatial = net_t2 / net_t1_layer
    # Requiring weak T0/T1_layer gains prevents a general pooling gain from
    # automatically being called a thermal architecture candidate.
    thermal_signal = (net_t0 <= 1.01 and net_t1_layer <= 1.01
                      and spatial > interaction_gate)
    eligible_layout = placement in ("free", "shared", "migration")
    passed = bool(controls_complete and eligible_layout and paid and thermal_signal
                  and net_t2 > speedup_gate and matched_t2 > speedup_gate)
    if not controls_complete:
        label = "incomplete_controls"
    elif placement == "fixed" and net_t2 > speedup_gate:
        label = "fixed_placement_signal"
    elif placement == "independent_oracle":
        label = "independent_layout_oracle"
    elif passed:
        label = "architecture_candidate"
    elif not paid and eligible_layout and net_t2 > speedup_gate:
        label = "ideal_upper_bound_signal"
    elif net_t0 > 1.01 or net_t1_layer > 1.01:
        label = "general_or_mixed_gain"
    elif net_t2 > 1.01:
        label = "spatial_signal_below_gate"
    else:
        label = "no_material_gain"
    return {"screening_class": label, "architecture_gate_pass": passed,
            "placement_controls_complete": bool(controls_complete),
            "paid_connection_costs_included": bool(paid),
            "thermal_specific_signal": bool(thermal_signal),
            "gate_policy": GATE_POLICY,
            "gate_requires_execution_and_physical_validation": True}
