"""Verify physical units after CK-to-native-tick serialization, independently."""
import argparse,json,sys
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--ramulator-root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();root=Path(a.ramulator_root);sys.path[:0]=[str(root/'python'),str(root)];from ramulator.dram.hbm3 import HBM3
 source=Path(a.source);summary=json.loads((source/'summary.json').read_text());records=[]
 for r in summary['records']:
  cfg=json.loads((source/r['name']/'config.json').read_text());native=cfg['memory_system']['controllers'][0]['dram'];timing=dict(zip(HBM3.timing_params,native['timing']));period=timing['tCK_ps']/1000
  physical={k:timing['n'+k]*period for k in ('RCDRD','RAS','RP','RC')};checks={k:abs(physical[k]-r['timing_ns'][k])<1e-9 for k in physical}
  if period!=.25 or not all(checks.values()) or summary['ratio']!=1:raise ValueError('Native tick/CK or timing-unit mismatch')
  records.append(dict(case=r['name'],native_period_ns=period,python_CK_ns=period*HBM3.tick_multiplier,physical_timing_ns=physical,timing_checks=checks,physical_banks=r['resources']['physical_banks'],commands=r['commands']['commands'],command_state_timing_validation=r['commands']['status']))
 Path(a.output).write_text(json.dumps(dict(status='PASS',upstream_tick_multiplier=HBM3.tick_multiplier,records=records,scope='Generated native timing and Logic conversion; software contract only, no device calibration'),indent=2)+'\n')
 print('PASS generated physical unit checks',len(records))
if __name__=='__main__':main()
