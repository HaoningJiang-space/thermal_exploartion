"""Independent P4-B event replay. Qualification failures remain separate."""
import argparse,gzip,hashlib,json
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor

TOL=1e-7
PHYSICAL_KINDS={'dram','hb','mac','read','write','fifo_consume','vector','link'}
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')

def replay(raw,point):
 nodes=raw['nodes'];events={e['id']:e for e in raw['events']};meta=raw['meta']
 if set(events)!=set(range(len(nodes))):raise ValueError('Incomplete event graph')
 resources=defaultdict(list);credits=defaultdict(list);private=defaultdict(list);activity=Counter();maxwaiterror=0
 for node in nodes:
  ev=events[node['id']];start=ev['start_tick'];end=ev['finish_tick'];ready=max((events[d]['finish_tick'] for d in node['deps']),default=0)
  if start < -TOL or end<start-TOL or ready>start+TOL:raise ValueError('Noncausal event')
  if any(ev[k]!=node[k] for k in ('kind','tile','work','stage')):raise ValueError('Event semantic mismatch')
  if 'wait_ticks' in ev:
   err=abs(sum(ev['wait_ticks'].values())-(start-ready));maxwaiterror=max(maxwaiterror,err)
   if err>TOL or min(ev['wait_ticks'].values(),default=0)<-TOL:raise ValueError('Wait partition not closed')
  duration=end-start
  if duration>TOL:
   for resource in [node['resource']]+meta.get('coupled_resources',{}).get(str(node['id']),[]):resources[tuple(resource)].append((start,end,node['id']))
  if node['kind'] in ('sram_read','sram_write','fifo_read'):
   rate={'sram_read':256,'sram_write':128,'fifo_read':500}[node['kind']]
   if node['work']>duration*rate+TOL:raise ValueError('Free operand port capacity')
  for key,amount,last in node['leases']:
   until=events[last]['finish_tick'];key=tuple(key)
   if last<node['id'] or until<start-TOL:raise ValueError('Invalid lease lifetime')
   if until<=start+TOL:continue
   credits[key]+=[(start,1,amount),(until,0,-amount)];private[key[1]]+=[(start,1,amount),(until,0,-amount)]
  activity[ev['kind']]+=ev['work']
 for ranges in resources.values():
  ordered=sorted(ranges)
  if any(a[1]>b[0]+TOL for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping physical resource')
 def peak(changes):
  used=high=0
  for _,_,change in sorted(changes):
   used+=change
   if used<0:raise ValueError('Lease accounting underflow')
   high=max(high,used)
  if used:raise ValueError('Unreleased credit')
  return high
 caps={'weight':524288,'weight_fifo':262144,'return':65536,'receive':65536,'workspace':1048576,'transmit':65536,'output':262144,**{f'router{i}':4096 for i in range(4)}}
 caps.update(meta.get('buffer_caps',{}));peaks={}
 for key,changes in credits.items():
  high=peak(changes);peaks[str(key)]=high
  if high>caps[key[0]] or high>point['buffer_high'][str(key)]:raise ValueError('Credit peak mismatch')
 max_output=0
 for name,group in meta.get('credit_groups',{}).items():
  if sum(caps[k] for k in group['members'])>group['capacity']:raise ValueError('Storage invented by partition')
  for tile in range(16):
   high=peak([change for member in group['members'] for change in credits[(member,tile)]]);max_output=max(max_output,high)
   if high>group['capacity'] or high>point['credit_group_high'][str((name,tile))]:raise ValueError('Physical output storage exceeded')
 private_high=max((peak(changes)+meta['fixed_sram_bytes'][tile] for tile,changes in private.items()),default=0)
 if private_high>meta['private_sram_budget_bytes']:raise ValueError('Private SRAM exceeded')
 for parent,partners in meta.get('coissued_nodes',{}).items():
  master=events[int(parent)]
  for child in partners:
   ev=events[child]
   if abs(ev['start_tick']-master['start_tick'])>TOL or ev['finish_tick']>master['finish_tick']+TOL:raise ValueError('Illegal coissued window')
 for kernel in raw.get('kernels',[]):
  for block in kernel.get('microtile_ledger',[]):
   start=events[block['node']]['start_tick']
   if any(events[r]['finish_tick']>start+TOL for r in block['return_nodes']):raise ValueError('Premature operand consumption')
  for packet in kernel.get('packet_ledger',[]):
   if any(nodes[packet[k]]['work']!=packet['bytes'] for k in ('dram','hb')):raise ValueError('Duplicated weight fetch')
 if activity!=Counter(point['packet_dag_activity']):raise ValueError('Packet activity mismatch')
 if abs(sum(point['critical_chain_ticks'].values())+point['critical_gap_ticks']-point['ticks'])>TOL:raise ValueError('Critical chain not closed')
 path=point['critical_path']
 for a,b in zip(path,path[1:]):
  if events[b['id']]['parent']!=a['id']:raise ValueError('Critical parent mismatch')
 if any(events[e['id']]['start_tick']!=e['start_tick'] or events[e['id']]['finish_tick']!=e['finish_tick'] for e in path):raise ValueError('Critical event mismatch')
 reserved={str(k):sum(b-a for a,b,_ in v) for k,v in resources.items() if k[0] in PHYSICAL_KINDS}
 return dict(status='PASS_INDEPENDENT_EVENT_REPLAY',nodes=len(nodes),physical_resources=len(reserved),delay_resources=sum(k[0] not in PHYSICAL_KINDS for k in resources),private_peak_bytes=private_high,output_partition_peak_bytes=max_output,max_wait_closure_error_ticks=maxwaiterror,reserved_ticks=reserved,credit_peaks=peaks,critical_kind_ticks=dict(Counter({kind:sum(e['finish_tick']-e['start_tick'] for e in path if e['kind']==kind) for kind in {e['kind'] for e in path}})))

def replay_file(path,point):return replay(json.loads(gzip.decompress(path.read_bytes())),point)

def compact(r):
 out={k:v for k,v in r.items() if k not in ('kernel_service_windows','critical_path','prefetch_ledger','row_block_ledger','communication_audit')}
 if r['execution_grain']!='macro':
  out['raw_scope']=r['scope']
  out['scope']='Captured routing, separate finite service windows and eager operand policy; full MoE timing qualification not established; not complete LLM tokens/s'
 detail=r.get('communication_audit',{})
 out['communication_audit_summary']={k:v for k,v in detail.items() if k not in ('semantic_ledger','input_delivery')}
 semantics=[{k:v for k,v in entry.items() if k not in ('node','accumulate_node')} for entry in detail.get('semantic_ledger',[])]
 out['semantic_sha256']=hashlib.sha256(json.dumps(semantics,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 out['input_delivery_sha256']=hashlib.sha256(json.dumps(detail.get('input_delivery'),sort_keys=True,separators=(',',':')).encode()).hexdigest()
 out['critical_path_sha256']=hashlib.sha256(json.dumps(r['critical_path'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--old-points',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 launch=read(a.root/'launcher-manifest.json');old=read(a.old_points);points=[];numerical=[];manifest=[];exact=[];pending=[]
 with ProcessPoolExecutor(max_workers=a.workers) as pool:
  for run in launch['runs']:
   directory=a.root/run['directory'];prov=read(directory/'provenance.json');params=prov['params'];rows=read(directory/'summary.json')
   if run['exit_code'] or (a.root/(run['directory']+'.exit')).read_text().strip()!='0':raise ValueError('Failed process')
   if prov['source_dirty'] or prov['source_commit']!=launch['source'] or sha(params['routes'])!=prov['routing_sha256']:raise ValueError('Source/route mismatch')
   wanted={('none','baseline')}
   if params['tp']==16 and params['down']=='row':wanted|={('none',n) for n in ('link_only','flight_only','infinite_noc')}|{('mac_only','baseline')}
   if {(r['isolation'],r['noc_mode']) for r in rows}!=wanted:raise ValueError('Incomplete frozen grid')
   nums=read(directory/'numerical.json')
   if len(nums)!=2 or any(n['status']!='PASS_NUMERICAL' for n in nums):raise ValueError('Numerical failure')
   numerical.extend(dict(n,experiment=run['directory']) for n in nums)
   for rec in rows:
    path=directory/(rec['label']+'.json');event=directory/rec['event_file']
    if rec!=read(path) or sha(event)!=rec['event_sha256'] or rec['status']!='PASS_ACCOUNTING':raise ValueError('Point integrity failure')
    if sum(k['dram_bytes'] for k in rec['kernel_service_windows'])!=rec['actual_dram_bytes'] or sum(k['mac_flops'] for k in rec['kernel_service_windows'])!=rec['mac_flops']:raise ValueError('Work mismatch')
    row=compact(rec);row.update(experiment=run['directory'],point_sha256=sha(path));points.append(row);pending.append((row,pool.submit(replay_file,event,rec)))
    if rec['execution_grain']=='macro' and (rec['noc_mode'] in ('baseline','infinite_noc')) and rec['isolation']=='none':
     matches=[o for o in old if o['batch']==rec['batch'] and int(o['tp'])==rec['tp'] and o['step']==0 and o['layer']==0 and o['down_partition']==rec['down_partition'] and o['dispatch_scheme']=='broadcast_all' and o['reduction_scheme']=='row_ready_128' and o['isolation']==('infinite_noc' if rec['noc_mode']=='infinite_noc' else 'none')]
     fields=('ticks','activity','mac_flops','actual_dram_bytes','critical_chain_ticks','critical_gap_ticks')
     if len(matches)!=1 or any(matches[0][k]!=row[k] for k in fields):raise ValueError('Exact P4-A regression failure')
     exact.append(dict(label=rec['label'],old_label=matches[0]['label'],fields=fields,status='EXACT_P4_A_REPLAY'))
   manifest.append(dict(directory=run['directory'],exit_code=0,source=prov['source_commit'],routing_sha256=prov['routing_sha256'],selected_experts=prov['selected_experts'],params={k:Path(v).name if k in ('routes','output') else v for k,v in params.items()},summary_sha256=sha(directory/'summary.json'),layout_sha256=sha(directory/'resident-layout.json')))
  for row,future in pending:row['event_replay']=future.result();print(row['label'],row['time_us'],'PASS',flush=True)
 if len(points)!=48 or len(numerical)!=48 or len(manifest)!=24 or len(exact)!=10:raise ValueError('Incomplete P4-B matrix')
 index={(r['batch'],r['tp'],r['down_partition'],r['execution_grain'],r['isolation'],r['noc_mode']):r for r in points};paired=[]
 for b in (8,32):
  for tp in (4,16):
   for down in ('row','column'):
    rows=[index[b,tp,down,g,'none','baseline'] for g in ('macro','fine_fixed','fine_prefetch')]
    if any(any(r[k]!=rows[0][k] for k in ('mac_flops','actual_dram_bytes','counts','semantic_sha256','input_delivery_sha256')) for r in rows):raise ValueError('Grain changes semantics')
    common=('mac','dram','hb','sram_read','sram_write','vector','link')
    if any(any(r['activity'].get(k,0)!=rows[0]['activity'].get(k,0) for k in common) for r in rows):raise ValueError('Grain changes work')
    paired.append(dict(batch=b,tp=tp,down_partition=down,macro_us=rows[0]['time_us'],fine_fixed_us=rows[1]['time_us'],fine_prefetch_us=rows[2]['time_us'],reservation_delta_us=rows[0]['time_us']-rows[1]['time_us'],prefetch_delta_us=rows[1]['time_us']-rows[2]['time_us'],common_activity={k:rows[0]['activity'].get(k,0) for k in common}))
 probes=[]
 for b in (8,32):
  for g in ('macro','fine_fixed','fine_prefetch'):
   base=index[b,16,'row',g,'none','baseline']
   for isolation,noc in (('none','link_only'),('none','flight_only'),('none','infinite_noc'),('mac_only','baseline')):
    r=index[b,16,'row',g,isolation,noc]
    if r['activity']!=base['activity']:raise ValueError('Oracle changes work')
    probes.append(dict(batch=b,grain=g,isolation=isolation,noc_mode=noc,base_us=base['time_us'],probe_us=r['time_us'],removed_us=base['time_us']-r['time_us'],speedup_pct=100*(base['time_us']/r['time_us']-1),latency_reduction_pct=100*(1-r['time_us']/base['time_us'])))
 dump(a.output/'all-points.json',points);dump(a.output/'numerical.json',numerical);dump(a.output/'run-manifest.json',manifest);dump(a.output/'paired-comparisons.json',paired);dump(a.output/'counterfactuals.json',probes)
 dump(a.output/'audit.json',dict(status='PASS_ACCOUNTING_NOT_FULL_FIDELITY',source=launch['source'],performance_points=48,numerical_comparisons=48,runs=24,exact_legacy_replays=exact,independent_event_replays=48,max_numerical_absolute_error=max(r['max_absolute_error'] for r in numerical),max_numerical_relative_l2_error=max(r['relative_l2_error'] for r in numerical),scope='One actual s0/l0 route, B8 subset of B32; finite accounting does not independently qualify fullMoE timing'))

if __name__=='__main__':main()
