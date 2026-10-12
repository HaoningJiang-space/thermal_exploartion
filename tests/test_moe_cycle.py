"""Small semantic/negative controls only, never performance evidence."""
import csv,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from thermal_exploration.model_contract import load_model,capacity
from thermal_exploration.layer_execution import resident_layout
from thermal_exploration.moe_cycle_program import program
from thermal_exploration.moe_cycle import execute
from thermal_exploration.moe_cycle_audit import replay
from thermal_exploration.run_moe_cycles import HEADERS
from thermal_exploration.moe_numerical import compare

class FullMoECycleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=dict(load_model('qwen15_moe'),hidden_size=512,moe_intermediate_size=256,shared_expert_intermediate_size=512,num_hidden_layers=1,num_experts=8,num_experts_per_tok=2)
  cls.routes=[[0,4]];cls.layout=resident_layout(cls.c,capacity(cls.c,1,512),'B3_3d_placement',tp=4)
 def test_shared_full_chain_and_independent_replay(self):
  p=program(self.c,self.layout,0,self.routes)
  self.assertEqual([j['expert'] for j in p['meta']['jobs']],[0,4,'shared'])
  self.assertEqual(p['meta']['jobs'][0]['owners'],p['meta']['jobs'][1]['owners'])
  self.assertEqual(compare(self.c,self.routes,[[.3,.7]],p['meta'])['status'],'PASS_NUMERICAL')
  with tempfile.TemporaryDirectory() as temp:
   prefix=Path(temp)/'run';handles={k:open(str(prefix)+'-'+k+'.csv','w',newline='') for k in HEADERS};writers={k:csv.writer(f) for k,f in handles.items()}
   for k,h in HEADERS.items():writers[k].writerow(h)
   try:z=execute(p,lambda k,row:writers[k].writerow(row))
   finally:
    for f in handles.values():f.close()
   self.assertEqual(z['activity']['mac'],p['meta']['mac_flops']);self.assertEqual(replay(p,prefix,z)['status'],'PASS_INDEPENDENT_FULL_PROGRAM_REPLAY')
   # A shared producer cannot be removed just because output timing matches.
   q=deepcopy(p);mac=next(n for n in q['nodes'] if n['kind']==4);mac['work']+=1
   with self.assertRaisesRegex(ValueError,'Activity|MAC'):replay(q,prefix,z)
   q=deepcopy(p);q['private_budget']=1
   with self.assertRaisesRegex(ValueError,'capacity'):replay(q,prefix,z)
 def test_subset_is_explicit_and_weight_slots_unchanged(self):
  p=program(self.c,self.layout,0,self.routes,selected=[0,4],shared=False,grain='fine_prefetch')
  self.assertEqual([j['expert'] for j in p['meta']['jobs']],[0,4]);self.assertEqual(p['contract']['grain'],'fine_prefetch')
  self.assertEqual(compare(self.c,self.routes,[[.3,.7]],p['meta'],'BF16')['status'],'PASS_NUMERICAL')
  self.assertEqual(len(set(r['address'] for r in p['request_identity'])),len(p['request_identity']))
  with self.assertRaisesRegex(ValueError,'absent'):program(self.c,self.layout,0,self.routes,selected=[7])
 def test_fixed_fp32_order_with_grouped_bf16_tokens(self):
  routes=[[0,4]]*8;l=resident_layout(self.c,capacity(self.c,8,512),'B3_3d_placement',tp=4)
  p=program(self.c,l,0,routes,down='column')
  r=compare(self.c,routes,[[.3,.7]]*8,p['meta'],'BF16',accumulation='fixed_k')
  self.assertEqual(r['tolerance'],dict(rtol=2e-4,atol=2e-6));self.assertEqual(r['accumulation'],'fixed_k')
if __name__=='__main__':unittest.main()
