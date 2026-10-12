"""Small semantic/negative controls only, never performance evidence."""
import csv,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from thermal_exploration.model_contract import load_model,capacity
from thermal_exploration.layer_execution import resident_layout
from thermal_exploration.moe_cycle_program import program
from thermal_exploration.moe_cycle_program import FlitGraph
from thermal_exploration.moe_cycle import execute
from thermal_exploration.moe_cycle_audit import replay
from thermal_exploration.run_moe_cycles import HEADERS
from thermal_exploration.moe_numerical import compare

class FullMoECycleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=dict(load_model('qwen15_moe'),hidden_size=512,moe_intermediate_size=256,shared_expert_intermediate_size=512,num_hidden_layers=1,num_experts=8,num_experts_per_tok=2)
  cls.routes=[[0,4]]*8;cls.layout=resident_layout(cls.c,capacity(cls.c,8,512),'B3_3d_placement',tp=4)
 def test_shared_full_chain_and_independent_replay(self):
  p=program(self.c,self.layout,0,self.routes)
  self.assertEqual([j['expert'] for j in p['meta']['jobs']],[0,4,'shared'])
  self.assertEqual(len(p['meta']['shared_gate_ledger']),16)
  self.assertEqual(p['meta']['jobs'][0]['owners'],p['meta']['jobs'][1]['owners'])
  self.assertEqual(compare(self.c,self.routes,[[.3,.7]]*8,p['meta'],accumulation='fixed_k')['status'],'PASS_NUMERICAL')
  with tempfile.TemporaryDirectory() as temp:
   prefix=Path(temp)/'run';handles={k:open(str(prefix)+'-'+k+'.csv','w',newline='') for k in HEADERS};writers={k:csv.writer(f) for k,f in handles.items()}
   for k,h in HEADERS.items():writers[k].writerow(h)
   try:z=execute(p,lambda k,row:writers[k].writerow(row))
   finally:
    for f in handles.values():f.close()
   self.assertEqual(z['activity']['mac'],p['meta']['mac_flops']);self.assertEqual(replay(p,prefix,z)['status'],'PASS_INDEPENDENT_FULL_PROGRAM_REPLAY')
   # A shared producer cannot be removed just because output timing matches.
   q=deepcopy(p);mac=next(n for n in q['nodes'] if n['kind']==4);mac['work']+=1
   with self.assertRaisesRegex(ValueError,'Activity|MAC|actual service'):replay(q,prefix,z)
   q=deepcopy(p);q['private_budget']=1
   with self.assertRaisesRegex(ValueError,'capacity'):replay(q,prefix,z)
 def test_subset_is_explicit_and_weight_slots_unchanged(self):
  p=program(self.c,self.layout,0,self.routes,selected=[0,4],shared=False,grain='fine_prefetch')
  self.assertEqual([j['expert'] for j in p['meta']['jobs']],[0,4]);self.assertEqual(p['contract']['grain'],'fine_prefetch')
  self.assertEqual(compare(self.c,self.routes,[[.3,.7]]*8,p['meta'],'BF16',accumulation='fixed_k')['status'],'PASS_NUMERICAL')
  self.assertEqual(len(set(r['address'] for r in p['request_identity'])),len(p['request_identity']))
  with self.assertRaisesRegex(ValueError,'absent'):program(self.c,self.layout,0,self.routes,selected=[7])
 def test_fixed_fp32_order_with_grouped_bf16_tokens(self):
  routes=[[0,4]]*8;l=resident_layout(self.c,capacity(self.c,8,512),'B3_3d_placement',tp=4)
  p=program(self.c,l,0,routes,down='column')
  r=compare(self.c,routes,[[.3,.7]]*8,p['meta'],'BF16',accumulation='fixed_k')
  self.assertEqual(r['tolerance'],dict(rtol=2e-4,atol=2e-6));self.assertEqual(r['accumulation'],'fixed_k')
 def test_real_88_element_shard_tail_is_paid(self):
  g=FlitGraph();g.broadcast(0,list(range(16)),88*2,stage='hidden_allgather')
  self.assertEqual(sum(n.work for n in g.nodes if n.kind=='sram_read'),192)
  self.assertEqual(sum(n.work for n in g.nodes if n.kind=='sram_write'),192*15)
  self.assertEqual(sum(n.work for n in g.nodes if n.kind=='link'),192*15)
  self.assertEqual(sum(g.meta['flit_valid_bytes'].values()),176*15)
  self.assertIn(16,g.meta['flit_valid_bytes'].values())
  from thermal_exploration.moe_cycle_program import KINDS
  from thermal_exploration.moe_transport_semantics import check
  p=dict(nodes=[dict(id=n.id,kind=KINDS.index(n.kind),tile=n.tile,work=n.work,deps=n.deps,valid_bytes=g.meta.get('flit_valid_bytes',{}).get(n.id,32)) for n in g.nodes],hidden_copies=[dict(expert=12,tokens=[8],source=0,owners=list(range(16)),width=1408,first=0,last=len(g.nodes))])
  self.assertEqual(check(p)['tail_copies'],1)
  next(n for n in p['nodes'] if n['kind']==5 and n['valid_bytes']==16)['valid_bytes']=32
  with self.assertRaisesRegex(ValueError,'mask'):check(p)
 def test_fifo_order_not_implied_by_finite_credit(self):
  from thermal_exploration.moe_fifo_audit import check_fifo
  p={'router':[dict(first=0,users=[1,2],key=[0,1,0]),dict(first=3,users=[4],key=[0,1,0])]}
  # Just two occupied slots, but a younger flit passes the blocked multicast
  # head. Byte capacity and producer dependencies alone both permit this.
  t={0:dict(finish=9),1:dict(start=9),2:dict(start=1025),3:dict(finish=13),4:dict(start=13)}
  self.assertEqual(check_fifo(p,t)['violations'],1)
  t[4]['start']=1026
  self.assertEqual(check_fifo(p,t)['status'],'PASS_FIFO_HEAD_ORDER')
  t[4]['start']=1025
  self.assertEqual(check_fifo(p,t)['input_service_overruns'],1)
 def test_matching_frontends_do_not_qualify_unbounded_rf(self):
  from thermal_exploration.moe_physical_audit import audit_registered_reuse
  p=program(self.c,self.layout,0,self.routes)
  r=audit_registered_reuse(p,self.c)
  self.assertFalse(r['architecture_g3_g4_qualified'])
  self.assertFalse(r['hardware_go'])
  gate=next(x for x in r['component_policy_comparison'] if x['projection']=='gate_up')
  self.assertGreater(gate['component_psum_read_bytes'],0)
  self.assertGreater(gate['component_psum_write_bytes'],gate['final_output_bytes'])
if __name__=='__main__':unittest.main()
