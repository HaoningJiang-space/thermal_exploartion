"""Resource payment and unchanged full application for service diagnostics."""
import unittest
from tools.run_cold_service_gate import CASES, experiment_inputs


class ColdServiceGate(unittest.TestCase):
    def test_every_diagnostic_keeps_full_captured_ffn_and_data_addresses(self):
        _, graph, data = experiment_inputs('baseline')
        self.assertEqual(len({t.id.split('/')[0] for t in graph.tasks if t.id.startswith('e')}), 8)
        self.assertEqual(sum(r.size_bytes for t in graph.tasks for r in t.reads), 151031808)
        for case in CASES:
            machine, candidate, row = experiment_inputs(case)
            self.assertEqual(candidate, graph)
            self.assertEqual(machine.stack.compute_clusters, experiment_inputs('baseline')[0].stack.compute_clusters)
            for field in ('weights','compute_reference_weights','metadata','network_policy'):
                self.assertEqual(row[field], data[field])

    def test_mc_entries_and_finite_return_reservations_are_paid(self):
        base, _, _ = experiment_inputs('baseline')
        mc, _, _ = experiment_inputs('mc16')
        self.assertEqual(mc.stack.resource_budget.gateway_descriptor_slots, 2*base.stack.resource_budget.gateway_descriptor_slots)
        self.assertEqual(mc.stack.resource_budget.gateway_staging_bytes, 2*base.stack.resource_budget.gateway_staging_bytes)
        self.assertEqual(mc.stack.dram_domains, base.stack.dram_domains)
        ret, _, row = experiment_inputs('return_capacity_relaxed')
        self.assertEqual(row['resources']['native']['reserved_return_bytes'], 16*131072)
        self.assertEqual(ret.stack.bank_groups, base.stack.bank_groups)

    def test_collection_override_does_not_change_physical_control_or_rates(self):
        base, _, original = experiment_inputs('baseline')
        collection, _, row = experiment_inputs('collection_minimum')
        self.assertEqual(collection, base)
        self.assertEqual(row['resources'], original['resources'])
        self.assertEqual(row['diagnostic']['data_collection_delay_override_ps'], 3760)
        gaps, _, _ = experiment_inputs('native_minimum_gaps')
        self.assertEqual(gaps.stack.native_policy.nBL, base.stack.native_policy.nBL)
        self.assertEqual(gaps.stack.native_policy.nREFI, base.stack.native_policy.nREFI)
        self.assertEqual(gaps.stack.dram_domains, base.stack.dram_domains)


if __name__ == '__main__':
    unittest.main()
