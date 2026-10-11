"""Three bounded existing-mechanism references after physical clock repair."""
import argparse,json,sys
from pathlib import Path
import subprocess
from thermal_exploration.run_g4 import native_build,verify_upstream,RAMULATOR_COMMIT
from thermal_exploration.run_d1 import run_case
from thermal_exploration.run import revision

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--ramulator-root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();root=Path(a.ramulator_root);out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
 if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=RAMULATOR_COMMIT:raise ValueError('Wrong upstream pin')
 verify_upstream(root);sys.path[:0]=[str(root/'python'),str(root)];exe=native_build(root,out);rows=[]
 for name in ('baseline','subarray_overlap_2','row_cycle_oracle'):
  r=run_case(exe,root,out,name);rows.append(r);(out/'partial.json').write_text(json.dumps(rows,indent=2)+'\n')
 for name in ('baseline','subarray_overlap_2','row_cycle_oracle'):
  r=run_case(exe,root,out,name,independent_commands=True);rows.append(r);(out/'partial.json').write_text(json.dumps(rows,indent=2)+'\n')
 for ordering in ('bank_row_interleave','bank_column_interleave'):
  r=run_case(exe,root,out,'baseline',ordering=ordering);rows.append(r);(out/'partial.json').write_text(json.dumps(rows,indent=2)+'\n')
 (out/'summary.json').write_text(json.dumps(dict(source_commit=revision(),logic_tick_ns=.25,dram_tick_ns=.5,ratio=2,records=rows,scope='Existing mechanism timing proxies only; not SALP circuitry or calibrated device. All reference requests/commands retained.'),indent=2)+'\n')
if __name__=='__main__':main()
