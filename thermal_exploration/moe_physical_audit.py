"""First-principles limits on interpreting the abstract MoE MAC program.

The component interpreter materializes psums for every M/K tile. The legacy
MoE byte-block law assumes register retention instead. Neither numerical
semantic checks nor matching interpreters proves that retention implementable.
This comparison is a specified component dataflow, NOT a universal lower bound.
"""
from math import ceil


def divisor(size, limit):
    return next(n for n in range(min(size, limit), 0, -1) if size % n == 0)


def audit_registered_reuse(p, c):
    kernels = {r['node']: r for r in p['meta']['kernel_ledger']}
    jobs = {j['expert']: j for j in p['meta']['jobs']}
    records = []
    for s in p['meta']['semantic_ledger']:
        b = len(s['tokens'])
        i = s['intermediate'][1] - s['intermediate'][0]
        if s['kind'] == 'gate_up':
            m, k, projections, source_k = i, c['hidden_size'], 2, c['hidden_size'] // 16
        else:
            m, k, projections = s['rows'][1] - s['rows'][0], i, 1
            source_k = jobs[s['expert']]['width'] // 16
        mb = divisor(m, 32)
        kb = divisor(k, min(128, source_k))
        while source_k % kb:
            kb = divisor(k, kb - 1)
        kt = k // kb
        inputs = projections * (m // mb) * k * b * 2
        psum_read = projections * m * b * 4 * (kt - 1)
        psum_write = projections * m * b * 4 * kt
        r = kernels[s['node']]
        charged = sum(z['operand_bytes'] for z in r['microtile_ledger'])
        records.append(dict(expert=s['expert'], tile=s['tile'], projection=s['kind'],
                            tokens=b, m=m, k=k, projections=projections,
                            component_m_block=mb, component_k_block=kb,
                            abstract_operand_bytes=charged,
                            component_input_bytes=inputs,
                            component_psum_read_bytes=psum_read,
                            component_psum_write_bytes=psum_write,
                            final_output_bytes=projections*m*b*4,
                            abstract_mac_psum_write_bytes=0,
                            retained_output_bytes_before_final_store=projections*m*b*4))
    peak = max((r['retained_output_bytes_before_final_store'] for r in records), default=0)
    return dict(status='NOT_QUALIFIED_PHYSICAL_MAC_CONTRACT',
                blockers=['Byte-block ledger has no actual M/K matrix coordinates',
                          'Matrix RF capacity and read/write ports are unspecified',
                          'Partial-sum register retention has no allocation/lifetime audit'],
                retained_output_requirement_bytes_per_tile=peak,
                requirement_scope='Outputs have no SRAM materialization until the '
                'whole local kernel completes; this excludes additional operand/weight RF',
                component_policy_comparison=records,
                interpretation='Component M/K policy pays SRAM partial traffic. '
                'Its extra bytes are a dataflow difference, not a universal lower bound '
                'or evidence that a sufficiently sized RF could not implement reuse.',
                architecture_g3_g4_qualified=False, hardware_go=False)
