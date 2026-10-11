import unittest
from thermal_exploration.crossover_execution import *
from thermal_exploration.model_contract import *
from thermal_exploration.layer_execution import resident_layout,tile_pipeline

class CrossoverTests(unittest.TestCase):
 def test_default_kernel_and_negative_resources(self):
  args=(((0,2**20),(7,2**20)),4)
  old=tile_pipeline(*args,True,keep_events=False);new=pipeline(*args)
  self.assertEqual(old['ticks'],new['ticks']);self.assertEqual(old['activity'],new['activity'])
  slow=pipeline(*args,Profile(hb_tb_s=8))
  self.assertGreater(slow['ticks'],new['ticks'])
  compute=pipeline(((0,2**20),),32)
  fewer=pipeline(((0,2**20),),32,Profile(compute_tflops=64,sram_mib=47))
  self.assertGreater(fewer['ticks'],compute['ticks'])
  self.assertEqual(sum((compute['mac_busy_ticks'],compute['missing_data_ticks'])),compute['ticks'])
 def test_tier_and_bank_controls_preserve_work(self):
  slow=pipeline(((7,2**20),),1)
  for isolation in ('bank_cycle','uniform_fast_tier','hb_only','ingress_only','mac_only'):
   r=pipeline(((7,2**20),),1,Profile(isolation=isolation))
   self.assertEqual(r['activity']['dram'],slow['activity']['dram']);self.assertEqual(r['activity']['mac'],slow['activity']['mac'])
  self.assertLess(pipeline(((7,2**20),),1,Profile(isolation='uniform_fast_tier'))['ticks'],slow['ticks'])
 def test_finite_prefix_and_operand_readiness(self):
  r=pipeline(((0,2**20),),4,lead=10**6)
  self.assertLessEqual(r['prefetched_bytes'],262144)
  self.assertTrue(all(start>=0 for start,*rest in r['mac_blocks']))
  self.assertGreaterEqual(r['ticks'],r['mac_busy_ticks'])
 def test_area_and_workspace_not_free(self):
  self.assertAlmostEqual(Profile().area()['total_committed_mm2'],121)
  self.assertTrue(Profile(192,24).area()['area_feasible'])
  self.assertFalse(Profile(192,36).area()['area_feasible'])
  self.assertFalse(Profile(256,12).budget(32,2048,5632)['feasible'])
 def test_complete_schedule_conservation_and_global_dependency(self):
  c=load_model('llama31_8b');a=capacity(c,4,8192);layout=resident_layout(c,a,'B3_3d_placement')
  serial=CrossoverExecution(c,a,layout).token(4,8192)
  r=CrossoverExecution(c,a,layout,schedule='prefetch_collective').token(4,8192)
  for k in ('dram','mac','hb'):self.assertEqual(r['activity'][k],serial['activity'][k])
  self.assertEqual(r['activity']['mac'],expected_mac_flops(c,4,8192))
  self.assertLess(r['ticks'],serial['ticks'])
  events={e['stage']:e for e in r['events']}
  self.assertGreaterEqual(events['layer0.residual_postnorm_partial']['start_tick'],events['layer0.o_reduce']['finish_tick'])
  self.assertGreaterEqual(events['layer1.input_norm_partial_stats']['start_tick'],events['layer0.residual']['finish_tick'])
  self.assertEqual(sum(r['critical_path_ticks'].values()),r['ticks'])
 def test_router_causality_and_large_cohort_lifetime(self):
  c=load_model('qwen15_moe');a=capacity(c,32,512);layout=resident_layout(c,a,'B3_3d_placement')
  routes=[[[i%60,(i+1)%60,(i+2)%60,(i+3)%60] for i in range(32)] for l in range(24)]
  r=CrossoverExecution(c,a,layout,schedule='prefetch_collective').token(32,512,routes)
  narrow=CrossoverExecution(c,a,layout,profile=Profile(192,24),schedule='prefetch_collective');narrow.layer(0,32,512,routes[0])
  self.assertTrue(all(e.get('live_expert_workspace_bytes',0)<=narrow.expert_workspace_bytes for e in narrow.events))
  self.assertEqual(r['activity']['mac'],expected_mac_flops(c,32,512,routes))
  for entry in r['prefetch_ledger']:
   if entry['identity_ready_tick']:self.assertGreaterEqual(entry['start_tick']-entry['lead_ticks'],entry['identity_ready_tick'])
  self.assertTrue(all(e.get('live_expert_workspace_bytes',0)<=r['sram_budget']['expert_workspace_bytes'] for e in r['events']))
  self.assertFalse(any(e['stage'].endswith('.dispatch') for e in r['events']))
if __name__=='__main__':unittest.main()
