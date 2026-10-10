import unittest
from thermal_exploration.decode_graph import Graph,execute,ffn,attention,moe


class DecodeGraphTests(unittest.TestCase):
    def test_resource_and_dependency_serialization(self):
        g=Graph();a=g.add('mac',0,2000,ticks=4);b=g.add('mac',0,2000,ticks=5)
        c=g.add('vector',1,16,(a,b),ticks=2);g.output=[c]
        r=execute(g);self.assertEqual(r['ticks'],11)

    def test_credit_negative_control(self):
        g=Graph();a=g.add('dram',0,1024,ticks=1);b=g.add('mac',0,2000,(a,),ticks=1)
        g.lease(a,b,('return',0),65537);g.output=[b]
        with self.assertRaises(ValueError):execute(g)
        self.assertEqual(execute(g,'ideal_buffer')['ticks'],2)

    def test_work_conservation_and_same_output_problem(self):
        for builder in (lambda:ffn(1),lambda:attention(1,8192),lambda:moe(2)):
            g=builder();r=execute(g)
            self.assertEqual(r['activity']['dram'],g.meta['weight_bytes'])
            self.assertEqual(r['activity']['mac'],g.meta['mac_flops'])
            ideal=execute(g,'infinite_noc')
            self.assertEqual(r['activity'],ideal['activity'])

    def test_tier_capacity_is_not_infinite(self):
        g=attention(16,131072)
        mem=[n for n in g.nodes if n.kind=='dram']
        self.assertEqual(sum(n.work for n in mem),8*2**30)
        self.assertEqual(sum(n.work for n in mem if n.tier==0),4*2**30)

    def test_invalid_dependency_rejected(self):
        with self.assertRaises(ValueError):Graph().add('mac',0,1,(0,),ticks=1)


if __name__=='__main__':unittest.main()
