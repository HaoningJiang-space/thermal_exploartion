"""Verify the relocated W2W evidence without executing either simulator."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    migration = json.loads((root/'migration.json').read_text())
    for name, identity in migration['files'].items():
        path = root/name
        if path.stat().st_size != identity['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != identity['sha256']:
            raise ValueError('Relocated file identity differs: '+name)
    evidence = root/'evidence/native-study'
    manifest = json.loads((evidence/'manifest.json').read_text())
    for name, identity in manifest['files'].items():
        path = evidence/name
        if path.stat().st_size != identity['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != identity['sha256']:
            raise ValueError('Original evidence identity differs: '+name)
    registration = json.loads((evidence/'registration.json').read_text())
    proof = json.loads((evidence/'independent-readback.json').read_text())
    if (not proof['passed'] or not proof['baseline_complete_physical_record_equal']
            or not proof['same_native_addresses_bytes_and_macs']
            or proof['execution_source_commit'] != registration['source_commit']
            or proof['execution_source_commit'] != migration['execution_source_commit']
            or proof['analysis_source_commit'] != migration['analysis_source_commit']
            or set(proof['cases']) != set(registration['cases'])
            or proof['files'] != manifest['raw_result_files']):
        raise ValueError('Frozen execution/readback identities differ')
    for case, row in proof['cases'].items():
        completion = json.loads((evidence/'completions'/f'{case}.json').read_text())
        if (not completion['complete'] or completion['source_commit'] != registration['source_commit']
                or completion['input_sha256'] != registration['cases'][case]['input_sha256']
                or completion['makespan_ps'] != row['makespan_ps']
                or completion['drained_ps'] != row['drained_ps']
                or completion['audit']['native_bytes'] != row['native_bytes']
                or row['native_bytes'] != 151031808):
            raise ValueError('Completion identity differs: '+case)
        bound = row['payload_work_bounds']
        if sum(bound['per_gateway_bytes'].values()) != row['native_bytes'] or sum(bound['per_domain_bytes'].values()) != row['native_bytes']:
            raise ValueError('Endpoint byte accounting differs: '+case)
    return dict(status='PASS',cases=len(proof['cases']),relocated_files=len(migration['files']),
        original_evidence_files=len(manifest['files']),backend='W2W V3',
        scope='Transfer and saved-receipt verification; no new native execution or thermal_exploration model qualification.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'results/w2w-cold-service-2026-10-11')
    args=parser.parse_args()
    print(json.dumps(verify(args.root),indent=2))
