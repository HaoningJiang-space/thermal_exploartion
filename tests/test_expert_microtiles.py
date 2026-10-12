import unittest
from thermal_exploration.decode_graph import Graph,execute
from thermal_exploration.expert_microtiles import microtile_kernel
from thermal_exploration.crossover_execution import Profile,pipeline

class MicrotileTests(unittest.TestCase):
 def test_isolated_pipeline_identity_and_finite_bytes(self):
  for b in (1,8,22):
   for tier in (0,7):
    spans=((tier,262144),);g=Graph();g.meta['buffer_caps']={'weight_descriptor':256,'return_descriptor':1024}
    end,r=microtile_kernel(g,0,spans,b,Profile(),262144,[],'kernel');g.output=[end]
    z=execute(g);ref=pipeline(spans,b,Profile())
    self.assertLessEqual(abs(z['ticks']-ref['ticks']),1)
    for kind in ('dram','hb','mac','sram_read'):self.assertEqual(z['activity'][kind],ref['activity'][kind])
    self.assertLessEqual(z['buffer_high']["('weight_fifo', 0)"],262144)
    self.assertLessEqual(z['buffer_high']["('return', 0)"],65536)
 def test_actual_operand_service_releases_before_arithmetic_tail(self):
  g=Graph();g.meta['buffer_caps']={'weight_descriptor':256,'return_descriptor':1024}
  end,r=microtile_kernel(g,0,((0,32768),),22,Profile(),32768,[],'kernel')
  ready=g.join([r['microtile_ledger'][0]['return_nodes'][-1]])
  packet=g.add('sram_read',0,256,(ready,),('read',0),1,'network');g.output=[g.join((end,packet))]
  z=execute(g);events={e['id']:e for e in z['events']};mac=r['microtile_ledger'][0]['node']
  self.assertLess(events[packet]['finish_tick'],events[mac]['finish_tick'])
 def test_oracles_separate_serialization_and_flight(self):
  g=Graph(256,True);g.output=[g.transfer(0,1,256,[])]
  z={mode:execute(g,mode) for mode in ('baseline','link_only','flight_only','infinite_noc')}
  self.assertEqual(z['baseline']['ticks']-z['link_only']['ticks'],32)
  self.assertEqual(z['baseline']['ticks']-z['flight_only']['ticks'],8)
  self.assertEqual(z['infinite_noc']['activity'],z['baseline']['activity'])
 def test_coissued_operand_cannot_gain_extra_port(self):
  g=Graph();g.meta['buffer_caps']={'weight_descriptor':256,'return_descriptor':1024}
  end,r=microtile_kernel(g,0,((0,32768),),22,Profile(),32768,[],'kernel')
  mac=r['microtile_ledger'][0]['node'];operand=g.meta['coissued_nodes'][mac][0]
  g.nodes[operand].ticks=g.nodes[mac].ticks+1;g.output=[end]
  with self.assertRaisesRegex(ValueError,'co-issued'):execute(g)

if __name__=='__main__':unittest.main()
