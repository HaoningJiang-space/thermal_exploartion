import unittest
from thermal_exploration.tensor_execution import build,CASES
from thermal_exploration.tensor_cycle import execute_tensor

class TensorCycleTests(unittest.TestCase):
 def test_finite_services_and_readiness(self):
  model=build(CASES['column_fifo64'],512,1024,1);result=execute_tensor(model)
  reads={r['id']:r for r in result['reads']}
  for t in result['tasks']:
   self.assertTrue(all(reads[r]['hb_done']<=t['start'] for r in t['requests']))
  for p in result['ports']:
   self.assertLessEqual(p['read_bytes'],256);self.assertLessEqual(p['write_bytes'],128);self.assertLessEqual(p['vector_ops'],16);self.assertLessEqual(p['fifo_operand_bytes'],500)
  for tile in range(16):
   spans=sorted((r['start'],r['finish']) for r in result['vectors'] if r['tile']==tile)
   self.assertTrue(all(a[1]<=b[0] for a,b in zip(spans,spans[1:])))
  self.assertEqual(result['activity']['mac'],model['contract']['mac_flops'])
  self.assertEqual(result['activity']['fifo_operand'],model['contract']['dram_bytes'])
 def test_reject_changed_ports_and_insufficient_leases(self):
  model=build(CASES['row_fifo_k'],512,1024,1);model['contract']['sram_read_bytes_per_tick']=512
  with self.assertRaisesRegex(ValueError,'physical rate'):execute_tensor(model)
  model=build(CASES['row_fifo_k'],512,1024,1);model['contract']['sram_per_tile']=1
  with self.assertRaisesRegex(ValueError,'Physical resource'):execute_tensor(model)
 def test_true_qwen_dimension_without_padding(self):
  model=build(CASES['row_fifo32'],1408,2048,1)
  self.assertEqual(model['contract']['m_block'],22);self.assertEqual(model['contract']['packet_bytes'],32)
  self.assertEqual(model['contract']['mac_flops'],2*1408*2048)
  self.assertEqual(model['contract']['dram_bytes'],2*1408*2048)
  self.assertTrue(all(t['m_count']==22 for t in model['tasks']))

if __name__=='__main__':unittest.main()
