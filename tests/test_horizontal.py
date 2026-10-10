import unittest
from thermal_exploration.horizontal import Traffic,route,gemm,redistribution,moe,capacity_bounds,scaling_example


class HorizontalAudit(unittest.TestCase):
    def test_multicast_not_repeated_unicast_and_reduction_conserved(self):
        t=Traffic();t.broadcast(0,range(16),128,"input")
        self.assertEqual(t.totals()["Broadcast"],15*128)
        t.reduce(range(16),0,32,"output")
        self.assertEqual(t.totals()["Reduction"],15*32*4)
        self.assertEqual(sum(t.vector_ops.values()),15*32)
        self.assertEqual(route(0,15),[(0,1),(1,2),(2,3),(3,7),(7,11),(11,15)])

    def test_same_matrix_and_endpoints_across_partitions(self):
        work=[]
        for rows in (1,2,4,8,16):
            t,w,p=gemm(4096,4096,32,rows,16//rows)
            self.assertEqual(sum(t.vector_ops.values()),(p['column_parts']-1)*4096*32)
            work.append((w['weight_bytes'],w['mac_flops'],w['input_bytes'],w['output_bytes']))
        self.assertEqual(len(set(work)),1)
        with self.assertRaises(ValueError):gemm(4096,4096,32,8,4)
        with self.assertRaises(ValueError):gemm(4096,4096,0)

    def test_permutation_and_all_expert_assignments_are_retained(self):
        t,w,_=redistribution(); aligned,wa,_=redistribution(True)
        self.assertEqual(w,wa)
        self.assertGreater(t.totals()['Redistribution'],0)
        self.assertEqual(aligned.totals()['Redistribution'],0)
        a,work,_=moe();b,other,_=moe(7)
        self.assertEqual(work,other)
        self.assertEqual(work['assignments'],512)
        self.assertEqual(work['logical_dispatch_bytes'],work['logical_combine_bytes'])
        dispatch=sum(r['bytes'] for r in a.records if r['commodity'].startswith('dispatch'))
        combine=sum(r['bytes'] for r in a.records if r['commodity'].startswith('combine'))
        self.assertEqual(dispatch,combine)

    def test_negative_capacity_and_scoped_oracles(self):
        t,w,_=gemm(1024,16384,32)
        full=capacity_bounds(t,w,32,26.599)
        narrow=capacity_bounds(t,w,32,26.599,8)
        slow_hb=capacity_bounds(t,w,.1,26.599)
        infinite=capacity_bounds(t,w,32,26.599,relax='infinite_noc')
        self.assertGreaterEqual(narrow['completion_necessary_lower_us'],full['completion_necessary_lower_us'])
        self.assertGreater(slow_hb['resource_lower_us']['dram_hb'],full['resource_lower_us']['dram_hb'])
        self.assertLessEqual(infinite['completion_necessary_lower_us'],full['completion_necessary_lower_us'])
        self.assertEqual(full['byte_hops_by_kind'],infinite['byte_hops_by_kind'])
        r,wr,_=redistribution()
        ordinary=capacity_bounds(r,wr,32,26.599)
        collectives=capacity_bounds(r,wr,32,26.599,relax='zero_collectives')
        self.assertEqual(ordinary['completion_necessary_lower_us'],collectives['completion_necessary_lower_us'])
        with self.assertRaises(ValueError):capacity_bounds(t,w,0,26.599)

    def test_cut_direction_and_scaling_example(self):
        t=Traffic();t.unicast('All-to-all',0,3,1024,'a')
        w=dict(weight_bytes=1024,mac_flops=0,metric_work=1024,metric_scale=1e9,metric='GB/s')
        bounds=capacity_bounds(t,w,32,26.599)
        cuts={(r['axis'],r['direction']):r for r in bounds['cuts']}
        self.assertEqual(cuts['x','low_to_high']['bytes_by_kind']['All-to-all'],1024)
        self.assertEqual(cuts['x','high_to_low']['bytes_by_kind']['All-to-all'],0)
        example=scaling_example(8)
        self.assertEqual(example['vertical_bytes_cycle'],4096)
        self.assertEqual(example['one_direction_cut_bytes_cycle'],256)
        self.assertAlmostEqual(example['cut_pressure'],1.6)
