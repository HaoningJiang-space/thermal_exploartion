"""One official ATLAS cloud-DRAM interleave matrix subcase, not full AE."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml

PIN='b2787399408e32d327c820daee96d4e6610f551a'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--atlas',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    root=Path(a.atlas).resolve();out=Path(a.output).resolve()
    if out.exists():raise ValueError('Preserve immutable experiment outputs')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=PIN:raise ValueError('ATLAS source pin mismatch')
    exe=root/'simulator/build/bin/test_dram'
    if not exe.exists():raise ValueError('Build official test_dram target first')
    out.mkdir(parents=True)
    records=[]
    for bit,repeat in [(0,0),(0,1),(7,0)]:
        name=f'interleave{bit}-repeat{repeat}'
        dram=yaml.safe_load((root/'configs/architecture/dram/hb_dram_16ch.yaml').read_text())
        dram['MemorySystem']['AddrMapper']['channel_lowest_bit']=bit
        d=out/(name+'-dram.yaml');d.write_text(yaml.safe_dump(dram,sort_keys=False))
        chip=yaml.safe_load((root/'configs/architecture/chip/test_chip_16ch.yaml').read_text())
        chip['architecture']['dram']['config_path']=str(d)
        c=out/(name+'-chip.yaml');c.write_text(yaml.safe_dump(chip,sort_keys=False))
        args=[str(exe),str(c),'matrix','64','2048','2048','16','512','128','1','1','0','2','0']
        result=subprocess.run(args,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log=re.sub(re.escape(str(root)),'<atlas-root>',result.stdout)
        log=re.sub(re.escape(str(out)),'<case-root>',log)
        (out/(name+'.log')).write_text(log)
        if result.returncode:raise RuntimeError('Official ATLAS subprocess failed; retained log')
        quantities={}
        for key,pattern in [('latency_s',r'Latency:\s*([\d.eE+\-]+)\s*s'),('bandwidth_gb_s',r'BW:\s*([\d.eE+\-]+)\s*GB/s'),('bandwidth_utilization',r'BW Util:\s*([\d.eE+\-]+)')]:
            match=re.search(pattern,log)
            if not match:raise ValueError('Missing official simulator observable: '+key)
            quantities[key]=float(match[1])
        records.append(dict(case=name,interleave_bit=bit,repeat=repeat,**quantities,log_sha256=hashlib.sha256(log.encode()).hexdigest()))
        # Export portable configuration separately from the executed absolute
        # path, which is not part of the public hardware contract.
        chip['architecture']['dram']['config_path']=d.name;c.write_text(yaml.safe_dump(chip,sort_keys=False))
    if records[0]['latency_s']!=records[1]['latency_s']:raise ValueError('Deterministic official matrix replay changed')
    record=dict(upstream_repo='https://github.com/pku-gsun/ATLAS-MICRO-2026',upstream_commit=PIN,
        case_source='tests/dram_dse_cloud.py:dse_interleave + tests/dram_test.py:test_matrix_access',
        tensor=dict(M=64,K=2048,N=2048,tM=16,tK=512,tN=128,input_row_major=True,output_row_major=True,weight_row_major=False,element_bytes=2,dataflow='OS'),
        records=records,deterministic_replay='PASS',
        scope='Official cloud DRAM AE subcase only; no full-model/chip/thermal reproduction and no Stratum equivalence',
        build_environment=dict(platform='POSIX; see build log',binary_sha256=hashlib.sha256(exe.read_bytes()).hexdigest()),
        source_patches={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['patches/ramulator2.patch','patches/booksim2.patch']})
    (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(records,indent=2))


if __name__=='__main__':main()
