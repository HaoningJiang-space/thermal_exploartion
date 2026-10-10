import unittest
from thermal_exploration.command_power import command_energy
from thermal_exploration.organization import load_exploration,lp_config
from thermal_exploration.known_mechanisms import adapt,validate
from thermal_exploration.hb_trace import streaming_trace


class TraceEnergy(unittest.TestCase):
    def setUp(self):self.p=load_exploration()
    def test_more_ACT_same_useful_bytes_increases_power_without_double_refresh_proxy(self):
        activity=dict(counts={'ACT':1,'PREpb':1,'RD':4,'REFab':0},useful_bytes=4096,duration_ns=100)
        low=lp_config(self.p,2,10,energy_mode='trace_driven',command_activity=activity)
        activity['counts']['ACT']=4;activity['counts']['PREpb']=4
        high=lp_config(self.p,2,10,energy_mode='trace_driven',command_activity=activity)
        self.assertGreater(high['hardware']['dram_pj_per_byte'],low['hardware']['dram_pj_per_byte'])
        self.assertEqual(high['hardware']['dram_static_w'],self.p['parameters']['dram_background_w']['value']/16)
    def test_missing_activity_and_inconsistent_density_fail(self):
        with self.assertRaises(ValueError):lp_config(self.p,2,10,energy_mode='trace_driven')
        with self.assertRaises(ValueError):
            lp_config(self.p,2,10,act_per_byte=1,energy_mode='trace_driven',command_activity=dict(counts={'ACT':1},useful_bytes=4096,duration_ns=100))
    def test_timing_only_keeps_fixed_energy_while_trace_uses_density(self):
        a=lp_config(self.p,2,10,act_per_byte=.01);b=lp_config(self.p,2,20,act_per_byte=.02)
        self.assertEqual(a['hardware']['dram_pj_per_byte'],b['hardware']['dram_pj_per_byte'])
        self.assertEqual(a['energy_contract']['mode'],'timing_only')
    def test_subarrays_partition_rows_preserve_addresses_and_capacity(self):
        r=adapt(streaming_trace(2,2048),2);validate(r,2)
        self.assertEqual({q['addr_vec'][2] for q in r},{0,1})
        self.assertEqual({q['addr_vec'][5] for q in r},{0})
        self.assertEqual(256*2*16384*4096,32*2**30)
        r[0]['addr_vec'][5]=16384
        with self.assertRaises(ValueError):validate(r,2)


if __name__=='__main__':unittest.main()
