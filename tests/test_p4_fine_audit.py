"""Negative controls for independent physical replay, not performance inputs."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('fine_audit',Path(__file__).parents[1]/'scripts/audit_p4_fine.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def fixture():
 nodes=[dict(id=i,kind=k,tile=0,work=w,deps=[] if i==0 else [0],resource=[r,0],ticks=1,stage='expert',leases=[]) for i,(k,w,r) in enumerate((('hb',16,'hb'),('mac',32,'mac'),('sram_read',256,'read')))]
 events=[dict(id=n['id'],kind=n['kind'],tile=0,work=n['work'],stage='expert',start_tick=0 if n['id']==0 else 1,finish_tick=1 if n['id']==0 else 2,parent=-1 if n['id']==0 else 0,wait_ticks={'queue_wait':0}) for n in nodes]
 path=[dict(id=i,kind=nodes[i]['kind'],start_tick=i,finish_tick=i+1) for i in (0,1)]
 raw=dict(nodes=nodes,events=events,meta=dict(fixed_sram_bytes=[0]*16,private_sram_budget_bytes=64,buffer_caps={'return':64},coissued_nodes={'1':[2]}),kernels=[dict(microtile_ledger=[dict(node=1,return_nodes=[0])])])
 point=dict(buffer_high={},credit_group_high={},packet_dag_activity={'hb':16,'mac':32,'sram_read':256},critical_chain_ticks={'expert':2},critical_gap_ticks=0,ticks=2,critical_path=path)
 return raw,point

class FineAuditTests(unittest.TestCase):
 def test_valid_replay_and_illegal_capacity(self):
  raw,point=fixture();self.assertEqual(audit.replay(raw,point)['status'],'PASS_INDEPENDENT_EVENT_REPLAY')
  raw['nodes'][2]['work']=raw['events'][2]['work']=512;point['packet_dag_activity']['sram_read']=512
  with self.assertRaisesRegex(ValueError,'Free operand'):audit.replay(raw,point)
 def test_premature_consumption_rejected(self):
  raw,point=fixture();raw['events'][1]['start_tick']=.5
  with self.assertRaisesRegex(ValueError,'Noncausal'):audit.replay(raw,point)
 def test_extra_buffer_rejected(self):
  raw,point=fixture();raw['nodes'][0]['leases']=[(['return',0],128,1)];point['buffer_high'][str(('return',0))]=128
  with self.assertRaisesRegex(ValueError,'Credit peak'):audit.replay(raw,point)
