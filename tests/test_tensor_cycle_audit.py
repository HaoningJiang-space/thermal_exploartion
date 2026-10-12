import importlib.util,unittest
from pathlib import Path
from thermal_exploration.tensor_execution import build,CASES
from thermal_exploration.tensor_cycle import execute_tensor
spec=importlib.util.spec_from_file_location('cycle_audit',Path(__file__).parents[1]/'scripts/qualify_p4_cycles.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CycleReplayTests(unittest.TestCase):
 def test_observer_replay_and_early_consumption(self):
  model=build(CASES['row_fifo_k'],512,1024,1);r=execute_tensor(model)
  self.assertEqual(module.audit(r,model['contract'])['status'],'PASS_INDEPENDENT_COMPONENT_REPLAY')
  r['tasks'][0]['start']=0
  with self.assertRaisesRegex(ValueError,'Early component'):module.audit(r,model['contract'])
 def test_free_storage_and_credit_rejected(self):
  model=build(CASES['column_fifo64'],512,1024,1);r=execute_tensor(model)
  event=r['lease_events'][0];old=event['delta'];event['delta']=2**30
  with self.assertRaisesRegex(ValueError,'byte lease'):module.audit(r,model['contract'])
  event['delta']=old;r['queue_events'][0]['delta']=9
  with self.assertRaisesRegex(ValueError,'router credit'):module.audit(r,model['contract'])
 def test_straddled_output_packet_waits_for_all_microtiles(self):
  model=build(CASES['row_fifo32'],1408,256,1);r=execute_tensor(model)
  self.assertEqual(module.audit(r,model['contract'])['status'],'PASS_INDEPENDENT_COMPONENT_REPLAY')
  group=next(g for g in model['reductions'] if g['start_byte']==64)
  from thermal_exploration.tensor_execution import reduction_tasks
  ids=reduction_tasks(model,group,0);self.assertEqual(len(ids),2)
  self.assertNotEqual(model['tasks'][ids[0]]['m_start'],model['tasks'][ids[1]]['m_start'])
  vector=next(v for v in r['vectors'] if v['group']==group['id'] and v['tile']==0)
  vector['start']=min(r['tasks'][i]['finish'] for i in ids)
  with self.assertRaisesRegex(ValueError,'Early output packet'):module.audit(r,model['contract'])

if __name__=='__main__':unittest.main()
