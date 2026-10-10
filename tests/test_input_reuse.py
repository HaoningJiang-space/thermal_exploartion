import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('reuse',Path(__file__).parents[1]/'scripts/derive_input_reuse.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class InputReuseTests(unittest.TestCase):
    def event(self,name,a,b):return dict(id=a,deps=[],step=0,stage='layer0.'+name,start_tick=a,finish_tick=b,critical_reason='communication',activity={'0':{'link':32}})
    def test_translation_and_conservation(self):
        events=[self.event('ffn_input_distribution',0,10),self.event('router',10,12),self.event('dispatch',12,17),self.event('routed_down',17,30)]
        out,removed,reason,ticks=m.transform(events,8,2048)
        self.assertEqual(ticks,5);self.assertEqual(out[-1]['finish_tick'],25);self.assertEqual(removed['link'],32)
        self.assertEqual(out[-1]['deps'],[out[-2]['id']])
    def test_no_free_capacity_or_missing_producer(self):
        with self.assertRaises(ValueError):m.transform([self.event('dispatch',0,5)],1,2048)
        with self.assertRaises(ValueError):m.transform([],64,4096)

if __name__=='__main__':unittest.main()
