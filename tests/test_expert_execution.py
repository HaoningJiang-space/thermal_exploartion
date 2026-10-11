import unittest,json
from pathlib import Path
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
 def test_hot_experts_do_not_duplicate_shared_inputs_or_deadlock(self):
  c=load_model('qwen15_moe');a=capacity(c,32,512);layout=resident_layout(c,a,'B3_3d_placement')
  g,meta=expert_graph(c,layout,0,[[0,1,2,3]]*32,Profile(),schedule='overlap')
  result=execute(g)
  self.assertEqual(result['activity']['mac'],meta['mac_flops'])
  traffic=sum(n.work for n in g.nodes if n.kind=='link' and n.stage=='dispatch')
  self.assertEqual(traffic,15*32*2048*2)
  for job in meta['jobs']:self.assertEqual(job['count'],32)
 def test_known_local_fusion_preserves_weights_and_reduces_once(self):
  c=load_model('qwen15_moe');a=capacity(c,8,512);layout=resident_layout(c,a,'B3_3d_placement')
  route=[[0,1,2,3]]*8
  fused,meta=expert_graph(c,layout,0,route,Profile(),combine_scheme='fused')
  eager,other=expert_graph(c,layout,0,route,Profile(),combine_scheme='eager')
  row,packed=expert_graph(c,layout,0,route,Profile(),down_partition='row')
  self.assertEqual(meta['mac_flops'],other['mac_flops']);self.assertEqual(meta['actual_dram_bytes'],other['actual_dram_bytes'])
  self.assertEqual(packed['actual_dram_bytes'],meta['actual_dram_bytes']);self.assertEqual(packed['mac_flops'],meta['mac_flops'])
  traffic=lambda g:sum(n.work for n in g.nodes if n.kind=='link' and n.stage=='combine')
  self.assertEqual(traffic(fused),15*2048*8*4);self.assertEqual(traffic(eager),5*traffic(fused))
  self.assertGreater(fused.meta['fixed_sram_bytes'][0],eager.meta['fixed_sram_bytes'][0])
  self.assertEqual(execute(row)['activity']['mac'],meta['mac_flops'])
 def test_captured_b32_fused_reduction_drains_finite_row_cohorts(self):
  capture=json.loads((Path(__file__).parent/'fixtures/qwen15_b32_layer0_step0.json').read_text())
  c=load_model('qwen15_moe');a=capacity(c,32,512)
  layout=resident_layout(c,a,'B3_3d_placement',capture['training_expected_activations'],16)
  g,meta=expert_graph(c,layout,0,capture['routes'],Profile(),schedule='barrier')
  result=execute(g);events={e['id']:e for e in result['events']}
  self.assertEqual(result['activity']['mac'],meta['mac_flops'])
  local_done=max(events[j['terminal']]['finish_tick'] for j in meta['jobs'])
  self.assertGreaterEqual(min(e['start_tick'] for e in result['events'] if e['stage']=='combine'),local_done)
  self.assertLessEqual(max(v for k,v in result['buffer_high'].items() if k.startswith("('output'")),65536)
  self.assertEqual(sum(n.work for n in g.nodes if n.kind=='link' and n.stage=='combine'),15*32*2048*4)

if __name__=='__main__':unittest.main()
