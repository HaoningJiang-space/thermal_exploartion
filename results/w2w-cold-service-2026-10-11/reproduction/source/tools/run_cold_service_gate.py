"""Full-size cold FFN interventions bound to its original captured routing.

This diagnoses the published 38.504 us MC-full window. It is one original
decode token, not complete-request or complete-Transformer performance.
Native Ramulator and BookSim, refresh, control and all application tasks run.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import gzip
import json
from pathlib import Path
import time
from types import SimpleNamespace

from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.experiments.run_co_placement import inputs
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha

CASES = ('baseline', 'mc16', 'native_minimum_gaps', 'collection_minimum',
         'gateway_output_relaxed', 'native_round_robin', 'return_capacity_relaxed')


def experiment_inputs(case):
    machine, graph, cache, data = inputs('up_local_compute', 'cold')
    if case not in CASES or cache is not None:
        raise ValueError('Registered cold intervention required')
    stack = machine.stack
    label = dict(case=case, diagnostic=case != 'baseline')
    if case == 'mc16':
        stack = replace(stack, name=stack.name+'-mc16-diagnostic', resource_budget=None,
            gateways=tuple(replace(g, descriptor_slots=16, staging_bytes=65536)
                           for g in stack.gateways),
            bank_groups=tuple(replace(g, mc_slots=16) for g in stack.bank_groups))
        label['scope'] = ('Double shared MC/grouped descriptors and associated finite '
            'return storage/control credits; keep native read queues and all service rates.')
    elif case == 'native_minimum_gaps':
        policy = replace(stack.native_policy, nCL=1, nRCD=1, nRP=1, nRAS=1, nRC=2,
                         nWR=1, nRTP=1, nCWL=1, nWTR=1, nRTW=1, nRFC=1)
        stack = replace(stack, name=stack.name+'-array-gaps-diagnostic', native_policy=policy)
        label['scope'] = ('Optimistic uncalibrated row/CAS/refresh gaps; native command '
            'scheduler remains active, nBL=1, nREFI=1037, 128 domains and 3.76 ns bus unchanged. '
            'This does not idealize the native data bus or establish device feasibility.')
    elif case == 'collection_minimum':
        label.update(data_collection_delay_override_ps=3760,
            scope='Only data propagation shortened to one native tick; original wire geometry, '
                  'control/ACK propagation, resource ledger and service rates retained. '
                  'Deliberate timing counterfactual, not a legal physical machine.')
    elif case == 'gateway_output_relaxed':
        stack = replace(stack, name=stack.name+'-gateway-output-diagnostic', resource_budget=None,
            gateways=tuple(replace(g, data_bytes_per_cycle=4096) for g in stack.gateways))
        label['scope'] = ('Raise Gateway output from 32 to 4096 B/ns, charging the new output '
            'budget. Native/HB, collection, staging, MC and actual BookSim/RX remain fixed. '
            'This does not idealize NoC.')
    elif case == 'native_round_robin':
        stack = replace(stack, name=stack.name+'-round-robin-diagnostic',
            native_policy=replace(stack.native_policy, descriptor_policy='round_robin'))
        label['scope'] = ('Change only native descriptor selection from row_batched to '
            'round_robin; all finite resources, command timings and physical rates fixed. '
            'A scheduling foil, not a new hardware design.')
    elif case == 'return_capacity_relaxed':
        stack = replace(stack, name=stack.name+'-return-capacity-diagnostic', resource_budget=None,
            dram_domains=tuple(replace(d, return_atoms=1024) for d in stack.dram_domains))
        label['scope'] = ('Raise per-domain atom return reservations from 64 to 1024; '
            'pay the reservation budget. MC/grouped slots, native command queues, Gateway '
            'output, geometry, control and BookSim/RX remain fixed. Finite diagnostic, not equal cost.')
    else:
        label['scope'] = 'Unchanged original Up-local cold FFN; must match every saved physical record.'
    data.update(machine=asdict(stack), resources=inventory(stack), diagnostic=label)
    return compile_machine(stack), graph, data


def prepare(root, historical, corpus):
    manifest = json.loads((corpus/'manifest.json').read_text())
    coverage = json.loads((corpus/'coverage-audit.json').read_text())
    if not coverage['passed'] or file_sha(corpus/'manifest.json') != coverage['normalized_manifest_sha256']:
        raise ValueError('Independently audited complete captured corpus required')
    logical = json.loads(Path('configs/workloads/c0_b1.json').read_text())
    candidates = [r for r in manifest['requests'] if r['id'] == logical['request_ids'][0]]
    if len(candidates) != 1:
        raise ValueError('Original cold request must exist exactly once in the real corpus')
    witness = candidates[0]
    capture_path = corpus/witness['path']
    if file_sha(capture_path) != witness['file_sha256']:
        raise ValueError('Original capture changed')
    capture = json.load(gzip.open(capture_path, 'rt'))
    if digest(capture) != witness['normalized_sha256']:
        raise ValueError('Captured content changed')
    # Published cold selection is original layer 0, zero-based decode step 16.
    if tuple(capture['decode']['0'][16]) != tuple(logical['token_experts'][0]):
        raise ValueError('Published cold graph differs from original ranked routing')
    proof = json.loads((historical/'independent-readback.json').read_text())
    old = historical/'cases/up_local_compute/result.json.gz'
    if not proof['passed'] or file_sha(old) != proof['files']['cases/up_local_compute/result.json.gz']['sha256']:
        raise ValueError('Independently audited historical cold baseline required')
    root.mkdir(parents=True, exist_ok=False)
    (root/'inputs').mkdir()
    rows = {}
    common = None
    for case in CASES:
        _, _, data = experiment_inputs(case)
        fixed = {k:data[k] for k in ('graph','metadata','weights','compute_reference_weights','network_policy')}
        if common is not None and fixed != common:
            raise ValueError('Intervention changed application work, placement or addresses')
        common = fixed
        with gzip.open(root/'inputs'/f'{case}.json.gz', 'wt') as f:
            json.dump(data, f)
        rows[case] = dict(input_sha256=digest(data), diagnostic=data['diagnostic'], resources=data['resources'])
    write_json(root/'registration.json', dict(schema='w2w.cold-service-diagnostics.v1',
        source_commit=revision(), cases=rows, historical_root=str(historical.resolve()),
        historical_proof_sha256=file_sha(historical/'independent-readback.json'),
        historical_result_sha256=file_sha(old), max_ps=6000000000,
        trace_witness=dict(request_id=witness['id'], layer='0', zero_based_decode_step=16,
            ranked_experts=capture['decode']['0'][16], raw_capture_sha256=witness['raw_sha256'],
            normalized_capture_sha256=witness['normalized_sha256'], dataset_revision=manifest['dataset_revision'],
            corpus_manifest_sha256=file_sha(corpus/'manifest.json'), coverage_audit_sha256=file_sha(corpus/'coverage-audit.json')),
        scope='Entire published 8-expert cold FFN, actual captured token; no smaller shape, '
              'task omission or synthetic routing. One-token selected-layer timing, not complete-request timing.',
        contract='Separate diagnosis from architecture. Full native execution and saved-result audit; '
                 'unchanged compute/SRAM/HB/NoC, addresses and traffic. No automatic retry or performance filtering.'))


def run(root, case, binary):
    from w2w.system.kernel import execute_system
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    reg = json.loads((root/'registration.json').read_text())
    machine, graph, data = experiment_inputs(case)
    if revision() != reg['source_commit'] or digest(data) != reg['cases'][case]['input_sha256']:
        raise ValueError('Registered source or input changed')
    directory = root/'cases'/case
    directory.mkdir(parents=True, exist_ok=False)
    before = time.monotonic()
    native = VerticalRWDL(machine, request_control=True, refresh=True, gateway_trace_bin_ps=1000000)
    if case == 'collection_minimum':
        native.paths = {k:SimpleNamespace(pipeline_cycles=p.pipeline_cycles, delay_ps=3760)
                        for k,p in native.paths.items()}
    try:
        r = execute_system(machine, graph, native=native, compute_contexts=2, fetch_contexts=2,
            read_issue_policy='round_robin', operand_readiness='contiguous_prefix',
            time_advance='boundaries', max_ps=reg['max_ps'],
            activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary, directory=directory/'network', **data['network_policy']))
    finally:
        native.close()
    a = audit_vertical_result(r)
    b = audit_request_control(r)
    if case == 'collection_minimum':
        a.update(physical_collection_charged=False, diagnostic_collection_override_ps=3760)
    if (sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute') != data['metadata']['macs']
            or Counter(e['task'] for e in r['events'] if e['kind']=='task_finish') != Counter({t.id:1 for t in graph.tasks})):
        raise ValueError('Complete application work was not executed exactly once')
    r.update(source_commit=revision(), diagnostic=data['diagnostic'])
    with gzip.open(directory/'result.json.gz', 'wt', compresslevel=3) as f:
        json.dump(r, f)
    write_json(directory/'completion.json', dict(complete=True, case=case, source_commit=revision(),
        input_sha256=digest(data), makespan_ps=r['makespan_ps'], drained_ps=r['drained_ps'],
        wall_seconds=time.monotonic()-before, audit=a, control_audit=b,
        booksim_sha256=r['network']['identity']['binary_sha256'], bridge_sha256=r['native']['bridge_sha256']))
    print(json.dumps(dict(complete=True,case=case,makespan_ps=r['makespan_ps'])), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--case', choices=CASES)
    p.add_argument('--historical', type=Path)
    p.add_argument('--corpus', type=Path)
    p.add_argument('--booksim-binary', type=Path)
    args = p.parse_args()
    if args.prepare:
        if args.historical is None or args.corpus is None:
            p.error('Original historical evidence and complete audited corpus required')
        prepare(args.root, args.historical, args.corpus)
    else:
        if args.booksim_binary is None:
            p.error('Accepted native binary required')
        run(args.root, args.case, args.booksim_binary)
