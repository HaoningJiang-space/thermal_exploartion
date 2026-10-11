"""Independent saved-result checks and measured full-FFN diagnostic effects."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from tools.check_simulator_equivalence import canonical
from w2w.analysis.memory_service_causality import explain_pool_window
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.validation.request_control import audit_request_control
from w2w.validation.vertical_access import audit_vertical_result
from w2w.workloads.moe_trace import file_sha


def analyze(root):
    reg = json.loads((root/'registration.json').read_text())
    historical = Path(reg['historical_root'])
    if file_sha(historical/'independent-readback.json') != reg['historical_proof_sha256']:
        raise ValueError('Historical proof changed')
    oldpath = historical/'cases/up_local_compute/result.json.gz'
    if file_sha(oldpath) != reg['historical_result_sha256']:
        raise ValueError('Historical raw identity changed')
    rows, files, tools = {}, {}, set()
    expected_work = None
    baseline_data = None
    for case, registered in reg['cases'].items():
        data = json.load(gzip.open(root/'inputs'/f'{case}.json.gz', 'rt'))
        path = root/'cases'/case/'result.json.gz'
        complete = json.loads((path.parent/'completion.json').read_text())
        r = json.load(gzip.open(path, 'rt'))
        if (digest(data) != registered['input_sha256'] or not complete['complete']
                or r['source_commit'] != reg['source_commit'] or complete['source_commit'] != reg['source_commit']
                or complete['input_sha256'] != registered['input_sha256'] or r['graph'] != data['graph']
                or r['spec']['stack'] != data['machine'] or r['diagnostic'] != data['diagnostic']
                or complete['makespan_ps'] != r['makespan_ps'] or complete['drained_ps'] != r['drained_ps']):
            raise ValueError('Registered source/input/execution identity differs')
        a = audit_vertical_result(r)
        b = audit_request_control(r)
        if case == 'collection_minimum':
            a.update(physical_collection_charged=False, diagnostic_collection_override_ps=3760)
        if a != complete['audit'] or b != complete['control_audit']:
            raise ValueError('Independent conservation differs from worker receipt')
        if (r['compute_execution']['contexts_per_cluster'] != 2
                or r['fetch_execution']['contexts_per_cluster'] != 2
                or r['fetch_execution']['read_issue_policy'] != 'round_robin'
                or r['operand_readiness']['policy'] != 'contiguous_prefix' or 'weight_cache' in r):
            raise ValueError('Registered shared-service or cold-cache policy changed')
        finished = Counter(e['task'] for e in r['events'] if e['kind']=='task_finish')
        if finished != Counter({t['id']:1 for t in data['graph']['tasks']}):
            raise ValueError('Application tasks missing or duplicated')
        requests = Counter((e['task'], e['memory'], e['bank'], e['word_address'], e['bytes'])
                           for e in r['events'] if e['kind']=='read_issue')
        work = dict(requests=requests, channel_atoms=r['native']['channel_atoms'],
                    gateway_bytes=r['native']['gateway_bytes'],
                    macs=sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute'))
        if work['macs'] != data['metadata']['macs']:
            raise ValueError('Arithmetic work changed')
        if expected_work is not None and work != expected_work:
            raise ValueError('Intervention changed actual requests, physical native work or arithmetic')
        expected_work = work
        if baseline_data is None:
            baseline_data = data
        for field in ('graph','metadata','weights','compute_reference_weights','network_policy'):
            if data[field] != baseline_data[field]:
                raise ValueError('Frozen application or mapping differs')
        tool = (r['network']['identity']['binary_sha256'], r['native']['bridge_sha256'])
        if tool != (complete['booksim_sha256'], complete['bridge_sha256']):
            raise ValueError('Native tool identity differs from completion')
        tools.add(tool)
        if case == 'baseline':
            old = json.load(gzip.open(oldpath, 'rt'))
            audit_vertical_result(old)
            audit_request_control(old)
            tools.add((old['network']['identity']['binary_sha256'], old['native']['bridge_sha256']))
            plain = dict(r)
            plain.pop('diagnostic')
            if canonical(plain) != canonical(old):
                raise ValueError('Baseline changed complete historical physical record')
            del old
        last_gate = max((t for t in r['tasks'] if t.endswith('/gate')),
                        key=lambda t:r['tasks'][t]['finish_ps'])
        stack = r['spec']['stack']
        gateway_rates = {g['id']:g['data_bytes_per_cycle']/r['spec']['noc_period_ps']
                         for g in stack['gateways']}
        domains = stack['dram_domains']
        domain_bytes = {d['id']:r['native']['channel_atoms'].get(str(i),
                       r['native']['channel_atoms'].get(i,0))*16 for i,d in enumerate(domains)}
        bounds = dict(global_gateway_payload_ps=a['native_bytes']/sum(gateway_rates.values()),
            busiest_gateway_payload_ps=max(v/gateway_rates[g] for g,v in r['native']['gateway_bytes'].items()),
            busiest_native_domain_payload_ps=max(domain_bytes[d['id']]*d['period_ps']/(d['data_bits']/8)
                                                 for d in domains),
            per_gateway_bytes=r['native']['gateway_bytes'], per_domain_bytes=domain_bytes,
            scope='Necessary payload-work bounds at fixed executed placement; ignore command gaps, refresh, dependencies and drain.')
        targets = sorted({'e62/b6/gate','e62/b7/gate','e62/b8/gate',last_gate})
        tail = {t:dict(r['tasks'][t]) for t in targets}
        # The timing counterfactual intentionally does not follow the geometry
        # contract required by the ordinary descriptor reader. Never relabel it.
        diagnosis = None
        if case != 'collection_minimum':
            d = explain_pool_window(r, 'e62/b8/gate')
            diagnosis = {k:v for k,v in d.items() if k not in
                         ('target_descriptors','pool_ownership_witnesses','full_intervals_ps')}
        rows[case] = dict(makespan_ps=r['makespan_ps'], drained_ps=r['drained_ps'],
            native_bytes=a['native_bytes'], completed_tasks=sum(finished.values()),
            wall_seconds=complete['wall_seconds'], diagnostic=data['diagnostic'], resources=data['resources'],
            fixed_block_tail=tail, final_gate=last_gate, e62_b8_pool=diagnosis,
            payload_work_bounds=bounds,
            native_reservation_stall_attempts=r['native']['reservation_stall_attempts'],
            native_queue_stall_attempts=r['native']['queue_stall_attempts'],
            mc_pool_peak=r['mc_pool_peak'], gateway_queue_peak_bytes=r['native']['gateway_queue_peak_bytes'])
        files[str(path.relative_to(root))] = dict(sha256=file_sha(path), bytes=path.stat().st_size)
        del r
    if len(tools) != 1:
        raise ValueError('Compared cases or original baseline used different native binaries')
    reference = rows['baseline']['makespan_ps']
    for row in rows.values():
        row['completion_reduction_percent'] = 100*(1-row['makespan_ps']/reference)
        row['measured_makespan_change_ps'] = reference-row['makespan_ps']
        row['fixed_gate_finish_change_ps'] = (rows['baseline']['fixed_block_tail']['e62/b8/gate']['finish_ps']
                                              - row['fixed_block_tail']['e62/b8/gate']['finish_ps'])
    return dict(schema='w2w.cold-service-diagnostics-readback.v1', passed=True,
        execution_source_commit=reg['source_commit'], analysis_source_commit=revision(),
        registration_sha256=file_sha(root/'registration.json'), trace_witness=reg['trace_witness'],
        cases=rows, files=files, native_tools=list(next(iter(tools))),
        baseline_complete_physical_record_equal=True, same_native_addresses_bytes_and_macs=True,
        scope=reg['scope'], limits=[
            'Measured interventions on one actual cold token; not entire captured-request performance.',
            'Minimum native gaps keep real data-bus bandwidth; no doubled-domain or fully ideal DRAM claim.',
            'Gateway output relaxation retains real BookSim/RX; it does not establish an ideal-NoC bound.',
            'MC16 and return-capacity diagnostics increase separately accounted finite resources.',
            'Collection override is deliberately nonphysical; no geometry-calibrated hardware benefit.',
            'Slot phase fractions overlap execution and cannot be added as recoverable makespan.',
            'No calibrated area/energy, numerical inference or architecture novelty is established.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('Never overwrite a saved readback')
    record = analyze(args.root)
    write_json(args.output, record)
    print(json.dumps(dict(passed=True, makespans={k:v['makespan_ps'] for k,v in record['cases'].items()})))
