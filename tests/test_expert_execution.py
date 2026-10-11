import unittest
from collections import Counter
from thermal_exploration.expert_execution import RowBlockedExecution,slice_spans,expert_graph
from thermal_exploration.crossover_execution import Profile,CrossoverExecution
from thermal_exploration.layer_execution import resident_layout
from thermal_exploration.model_contract import load_model,capacity,expected_mac_flops
from thermal_exploration.tensor_execution import hardware,CASES
from thermal_exploration.decode_graph import execute,Graph

class ExpertTests(unittest.TestCase):
 def test_paid_native_profiles_and_negative_storage(self):
  c=hardware(dict(CASES['row_fifo_k'],compute_tflops=152,sram_mib=18),6144,4096,4)
  self.assertEqual(c['mac_flops_per_tick'],2375);self.assertEqual(c['sram_per_tile'],1179648)
  with self.assertRaises(ValueError):hardware(dict(CASES['row_fifo_k'],sram_mib=1),6144,4096,16)
 def test_disjoint_rows_preserve_tier_bytes(self):
  parts=((0,8192),(3,16384),(7,32768));seen=Counter()
  for row in range(0,2048,64):seen.update(dict(slice_spans(parts,row,row+64,2048)))
  self.assertEqual(seen,dict(parts))
 def test_row_block_removes_schedule_failure_without_dropping_work(self):
  c=load_model('qwen15_moe');a=capacity(c,32,512);l=resident_layout(c,a,'B3_3d_placement')
  routes=[[[i%60,(i+1)%60,(i+2)%60,(i+3)%60] for i in range(32)] for layer in range(24)]
  old=CrossoverExecution(c,a,l,profile=Profile(152,18),schedule='prefetch_collective')
  with self.assertRaisesRegex(ValueError,'Cohort'):old.layer(0,32,512,routes[0])
  e=RowBlockedExecution(c,a,l,profile=Profile(152,18),schedule='prefetch_collective');e.layer(0,32,512,routes[0])
  ref=CrossoverExecution(c,a,l,schedule='prefetch_collective');ref.layer(0,32,512,routes[0])
  for kind in ('dram','hb','mac'):self.assertEqual(e.work[kind],ref.work[kind])
  self.assertLessEqual(max(x['live_bytes'] for x in e.row_ledger),e.expert_workspace_bytes)
 def test_graph_expert_work_and_real_collective(self):
  c=load_model('qwen15_moe');a=capacity(c,1,512);routes=[[0,1,2,3]]
  for tp in (1,4,16,'hybrid'):
   l=resident_layout(c,a,'B3_3d_placement',tp=tp);g,meta=expert_graph(c,l,0,routes,Profile())
   r=execute(g);ideal=execute(g,'infinite_noc')
   self.assertEqual(r['activity']['mac'],meta['mac_flops']);self.assertLessEqual(ideal['ticks'],r['ticks'])
   self.assertEqual(ideal['activity'],r['activity']);self.assertEqual(meta['token_expert_assignments'],4)
   self.assertEqual(meta['actual_dram_bytes'],meta['active_weight_bytes'])
   self.assertEqual(meta['counts'],{0:1,1:1,2:1,3:1})
 def test_coupled_ports_are_shared_and_private_credit_backpressures(self):
  g=Graph();g.meta['coupled_resources']={}
  a=g.add('mac',0,10,resource=('mac',0),ticks=10);g.meta['coupled_resources'][a]=[('read',0)]
  b=g.add('sram_read',0,10,resource=('read',0),ticks=10);g.output=[g.join((a,b))]
  r=execute(g);events={x['id']:x for x in r['events']}
  self.assertTrue(events[a]['finish_tick']<=events[b]['start_tick'] or events[b]['finish_tick']<=events[a]['start_tick'])

if __name__=='__main__':unittest.main()
