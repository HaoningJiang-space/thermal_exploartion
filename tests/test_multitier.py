import unittest
from thermal_exploration.multitier import contract,request_identity,tier_timings,TierLegality

class MultiTierContract(unittest.TestCase):
    def test_capacity_and_common_work(self):
        for q in (1024,4096,65536):
            c=contract(q)
            assert c['total_bytes']==6*2**30>c['fast_tier_capacity_bytes']
            assert c['useful_flops']==7*2**30
            last=request_identity(c['requests']-1,q,'compact')
            assert last['tier']==1 and last['vec'][5]==6143
            with self.assertRaises(ValueError):request_identity(c['requests'],q,'compact')
            with self.assertRaises(ValueError):request_identity(0,q,'bad')

    def test_striping_really_uses_all_tiers(self):
        assert {request_identity(i,4096,'striped')['tier'] for i in range(0,512,64)}==set(range(8))
        assert request_identity(0,4096,'compact')['vec']==[0,0,0,0,0,0,0]

    def test_slow_tier_keeps_shared_bank_and_restoration(self):
        t=tier_timings();assert all(t['ras_ticks'][i]>=120 for i in range(8))
        check=TierLegality();v=[0,0,0,0,0,7*4096,0]
        check.issue('ACT',v,0)
        with self.assertRaises(ValueError):check.issue('RD',v,10)
        with self.assertRaises(ValueError):check.issue('PREpb',v,120)
        check.issue('RD',v,t['rcd_ticks'][7]+2);check.issue('PREpb',v,t['ras_ticks'][7]+2)
        with self.assertRaises(ValueError):check.issue('ACT',[0,0,0,0,0,0,0],t['rc_ticks'][7]-1)
        check.issue('ACT',[0,0,0,0,0,0,0],t['rc_ticks'][7])

    def test_refresh_wildcard_does_not_skip_slow_restoration(self):
        c=TierLegality();v=[0,1,0,0,0,7*4096,0];c.issue('ACT',v,0)
        wildcard=[0,-1,-1,-1,-1,-1,-1]
        with self.assertRaises(ValueError):c.issue('PREab',wildcard,122)
        c.issue('PREab',wildcard,tier_timings()['ras_ticks'][7]+2)
