import copy,json,unittest
from pathlib import Path
import numpy as np
from thermal_exploration.expert_execution import expert_graph
from thermal_exploration.crossover_execution import Profile
from thermal_exploration.model_contract import load_model,capacity
from thermal_exploration.layer_execution import resident_layout
from thermal_exploration.decode_graph import execute,Graph
from thermal_exploration.moe_numerical import compare,check_ledger,bf16


class P4Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.capture=json.loads((Path(__file__).parent/'fixtures/qwen15_b32_layer0_step0.json').read_text())
  cls.c=load_model('qwen15_moe')
 def layout(self,c,b,tp):return resident_layout(c,capacity(c,b,512),'B3_3d_placement',self.capture['training_expected_activations'],tp)
 def test_shared_owner_union_requires_all_endpoints(self):
  routes=self.capture['routes'][:8];layout=self.layout(self.c,8,4)
  graphs={}
  for scheme in ('broadcast_all','destination_only','decoupled'):
   graphs[scheme],meta=expert_graph(self.c,layout,0,routes,Profile(),schedule='barrier',order='static',dispatch_scheme=scheme)
   check_ledger(self.c,routes,meta)
   if scheme=='destination_only':self.assertTrue(all(x['targets']==list(range(16)) for x in meta['input_delivery']))
  traffic=lambda g:sum(n.work for n in g.nodes if n.kind=='link' and n.stage in ('dispatch','shared_dispatch','routed_dispatch'))
  self.assertEqual(traffic(graphs['broadcast_all']),traffic(graphs['destination_only']))
  self.assertGreater(traffic(graphs['decoupled']),traffic(graphs['broadcast_all']))
 def test_real_b32_row_ready_uses_existing_credits_and_starts_early(self):
  layout=self.layout(self.c,32,16)
  g,meta=expert_graph(self.c,layout,0,self.capture['routes'],Profile(),schedule='barrier',order='static',down_partition='row',reduction_scheme='row_ready')
  result=execute(g);events={e['id']:e for e in result['events']}
  local=max(events[j['terminal']]['finish_tick'] for j in meta['jobs'])
  first=min(e['start_tick'] for e in result['events'] if e['stage']=='combine')
  self.assertLess(first,local)
  self.assertLessEqual(max(result['credit_group_high'].values()),65536)
  self.assertLessEqual(max(result['private_sram_high'].values()),g.meta['private_sram_budget_bytes'])
  self.assertEqual(sum(n.work for n in g.nodes if n.kind=='link' and n.stage=='combine'),15*32*2048*4)
  self.assertEqual(result['activity']['mac'],meta['mac_flops'])
 def test_credit_classes_cannot_create_storage(self):
  g=Graph();g.meta.update(buffer_caps={'a':32768,'b':49152},credit_groups={'output':dict(members=['a','b'],capacity=65536)})
  g.output=[g.join(())]
  with self.assertRaisesRegex(ValueError,'physical storage'):execute(g)
 def test_shard_token_and_weight_slot_numerics_and_mutations(self):
  c=dict(self.c,hidden_size=256,moe_intermediate_size=32,shared_expert_intermediate_size=128)
  routes=self.capture['routes'][:8]
  # Functional test only; formal numerical records use captured probabilities.
  probs=np.tile(np.array([.4,.3,.2,.1],np.float32),(8,1))
  for tp in (4,16):
   for down in ('column','row'):
    g,meta=expert_graph(c,self.layout(c,8,tp),0,routes,Profile(),schedule='barrier',order='static',down_partition=down,reduction_scheme='row_ready')
    for dtype in ('FP32','BF16'):self.assertEqual(compare(c,routes,probs,meta,dtype)['status'],'PASS_NUMERICAL')
    damaged=copy.deepcopy(meta);rec=next(x for x in damaged['semantic_ledger'] if x['kind']=='down' and x['expert']!='shared')
    rec['routing_slots'][0]=(rec['routing_slots'][0]+1)%4
    with self.assertRaisesRegex(ValueError,'weight binding'):check_ledger(c,routes,damaged)
    damaged=copy.deepcopy(meta);damaged['semantic_ledger'].pop()
    with self.assertRaisesRegex(ValueError,'coverage'):check_ledger(c,routes,damaged)
 def test_bf16_rounds_ties_to_even(self):
  np.testing.assert_array_equal(bf16(np.array([1+1/256,1+3/256],np.float32)),[1,1+1/64])

if __name__=='__main__':unittest.main()
