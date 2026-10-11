import unittest
from thermal_exploration.tensor_execution import CASES, build, hardware


class TensorContractTests(unittest.TestCase):
    def test_partition_work_and_address_conservation(self):
        for name in ('row_blocked_m','column_blocked_m','2d_blocked_k','row_local_first'):
            with self.subTest(name=name):
                x=build(CASES[name],64,1024,8);c=x['contract']
                self.assertEqual(sum(t['flops'] for t in x['tasks']),2*64*1024*8)
                self.assertEqual(len({r['address'] for r in x['requests']}),c['requests'])
                self.assertEqual(c['dram_bytes'],c['weight_bytes'])
                for t in x['tasks']:
                    if t['parent']>=0:self.assertLess(t['parent'],t['id'])

    def test_padded_rows_pay_for_overfetch(self):
        a=build(CASES['column_rowmajor_m'],64,1024,8)['contract']
        b=build(CASES['column_padded_m'],64,1024,8)['contract']
        self.assertEqual(a['weight_bytes'],b['weight_bytes'])
        self.assertGreater(b['dram_bytes'],a['dram_bytes'])
        self.assertGreater(b['allocated_weight_bytes'],a['allocated_weight_bytes'])

    def test_full_partial_and_private_sram(self):
        c=hardware(CASES['column_blocked_m'])
        self.assertEqual(c['partial_bytes_per_tile'],128*1024)
        for fixed in c['static_sram_per_tile']:
            self.assertLessEqual(fixed+c['metadata_reserve']+c['weight_buffer']+c['response_buffer']+c['reduce_buffer'],c['sram_per_tile'])

    def test_invalid_contract_rejected(self):
        with self.assertRaises(ValueError):hardware(dict(CASES['column_blocked_m'],weight_buffer=4*2**20))
        with self.assertRaises(ValueError):hardware(CASES['column_blocked_m'],65,1024,8)

    def test_input_groups_have_real_canonical_producers(self):
        for m,n,b in ((64,1024,8),(2048,1408,2),(6144,4096,4)):
            x=build(CASES['row_fifo_k'],m,n,b);kb=x['contract']['k_block']
            for group in x['inputs']:
                first=group['id']*kb;owner=group['source']*(n//16)
                self.assertGreaterEqual(first,owner)
                self.assertLessEqual(first+kb,owner+n//16)
        with self.assertRaises(ValueError):hardware(CASES['row_fifo_k'],2048,1408,1)


if __name__=='__main__':unittest.main()
