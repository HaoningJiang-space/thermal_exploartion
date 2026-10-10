import unittest
from thermal_exploration.model_contract import load_model,tensors,capacity

class ModelContractTests(unittest.TestCase):
    def test_all_parameters_and_gated_projections(self):
        llama=load_model('llama31_8b');rows=tensors(llama)
        self.assertEqual(sum(t['elements'] for t in rows),8030261248)
        self.assertEqual(len([t for t in rows if t['layer']==0 and t['name'].endswith(('.gate','.up','.down'))]),3)
        qwen=load_model('qwen15_moe');q=tensors(qwen)
        self.assertEqual(sum(t['elements'] for t in q),14315784192)
        self.assertEqual(len([t for t in q if t['layer']==0 and t['family']=='routed']),180)
        self.assertEqual(sum(t['bytes'] for t in q if t['layer']==0 and t['family']=='shared'),3*2048*5632*2)
    def test_full_layer_kv_and_context_boundary(self):
        c=load_model('llama31_8b');r=capacity(c,16,131072)
        self.assertFalse(r['capacity_feasible']);self.assertGreater(r['all_layer_kv_bytes'],256*2**30)
        c=load_model('qwen15_moe');r=capacity(c,2,8192)
        self.assertTrue(r['capacity_feasible']);self.assertFalse(r['runnable'])
        self.assertTrue(capacity(c,2,8192,allow_context_extension=True)['runnable'])
    def test_no_activated_expert_capacity_shortcut(self):
        c=load_model('qwen15_moe');r=capacity(c,1,2048,dram_bytes=8*2**30)
        self.assertFalse(r['capacity_feasible'])

if __name__=='__main__':unittest.main()
