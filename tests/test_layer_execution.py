import json
import unittest
from collections import defaultdict
from thermal_exploration.layer_execution import *
from thermal_exploration.model_contract import *

class LayerExecutionTests(unittest.TestCase):
    def test_kernel_ports_and_negative_control(self):
        r=tile_pipeline(((0,262144),),4,False)
        for kind,limit in [('sram_read',256),('sram_write',128)]:
            changes=defaultdict(float)
            for k,a,b,work,tier in r['events']:
                if k==kind and work and b>a:
                    changes[a]+=work/(b-a);changes[b]-=work/(b-a)
            live=0
            for time,delta in sorted(changes.items()):
                live+=delta;self.assertLessEqual(live,limit+1e-7)
        slow=tile_pipeline(((0,262144),),4,False,ports=.5)
        self.assertGreater(slow['ticks'],r['ticks'])
        self.assertLessEqual(r['max_response_bytes'],65536)
        self.assertLessEqual(r['max_live_weight_bytes'],524288)
    def test_independent_return_granularity(self):
        coarse=tile_pipeline(((0,4*2**20),),1,True,packet_bytes=32768,keep_events=False)
        coarse_ideal=tile_pipeline(((0,4*2**20),),1,True,'ideal_buffer',packet_bytes=32768,keep_events=False)
        fine=tile_pipeline(((0,4*2**20),),1,True,packet_bytes=1024,keep_events=False)
        fine_ideal=tile_pipeline(((0,4*2**20),),1,True,'ideal_buffer',packet_bytes=1024,keep_events=False)
        self.assertGreater(coarse['ticks']/coarse_ideal['ticks'],1.05)
        self.assertEqual(fine['ticks'],fine_ideal['ticks'])
        self.assertEqual(fine['dram_bytes'],coarse['dram_bytes'])
    def test_global_and_regional_residency(self):
        c=load_model('qwen15_moe');a=capacity(c,8,2048);l=resident_layout(c,a,'B3_3d_placement',tp=4)
        self.assertTrue(all(x<=256*2**20 for row in l['used_bytes'] for x in row))
        self.assertGreater(sum(map(sum,l['used_bytes'])),a['resident_weights_bytes']+a['all_layer_kv_bytes'])
    def test_complete_model_flops_and_actual_dependencies(self):
        c=load_model('llama31_8b');a=capacity(c,1,2048);l=resident_layout(c,a,'B3_3d_placement')
        r=LayerExecution(c,a,l,'B3_3d_placement').token(1,2048)
        self.assertEqual(r['activity']['mac'],expected_mac_flops(c,1,2048))
        names=[e['stage'] for e in r['events']]
        self.assertLess(names.index('layer0.qkv'),names.index('layer0.rope'))
        self.assertLess(names.index('layer0.kv_update'),names.index('layer0.split_kv_attention'))
        self.assertLess(names.index('layer0.silu_multiply'),names.index('layer0.paired_down'))
        self.assertGreater(names.index('layer1.input_norm'),names.index('layer0.residual'))
        self.assertEqual(sum(r['critical_path_ticks'].values()),r['ticks'])
    def test_route_identity_and_all_experts_resident(self):
        c=load_model('qwen15_moe');a=capacity(c,1,2048);l=resident_layout(c,a,'B3_3d_placement')
        data=json.loads((ROOT/'configs/routing/hda_qwen_projected.json').read_text());routes=[x[:1] for x in data['routes']]
        r=LayerExecution(c,a,l,'B3_3d_placement').token(1,2048,routes)
        self.assertEqual(r['activity']['mac'],expected_mac_flops(c,1,2048,routes))
        self.assertEqual(len([x for x in l['tensors'] if '.expert' in x]),24*60*3)
        with self.assertRaises(ValueError):LayerExecution(c,a,l,'B3_3d_placement').token(1,2048,[[[0,0,1,2]]]*24)

if __name__=='__main__':unittest.main()
