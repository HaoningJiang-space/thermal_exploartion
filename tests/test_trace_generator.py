import copy
import unittest
from thermal_exploration.trace_generator import (gemv,hbm3_address,inverse_hbm3_address,
    row_conflict,streaming,validate_trace,verify_gemv_consumption)
from thermal_exploration.run_g4 import generated_cpp_tokens,validate_events


class AddressedTraces(unittest.TestCase):
    def test_codegen_guard_allows_formatting_but_rejects_timing_changes(self):
        a='#include "a.h"\n#include "b.h"\nint nFAW=24; // original\n'
        b='#include "b.h"\n#include "a.h"\nint nFAW = 24; /* generated */\n'
        self.assertEqual(generated_cpp_tokens(a),generated_cpp_tokens(b))
        self.assertNotEqual(generated_cpp_tokens(a),generated_cpp_tokens(b.replace('24','25')))

    def test_mapping_is_bijective_and_has_full_bank_row_geometry(self):
        addresses=list(range(0,64*1024*2,32))+[2**20,2**30-32]
        vectors=[hbm3_address(a) for a in addresses]
        self.assertEqual(len({tuple(v) for v in vectors}),len(addresses))
        self.assertEqual([inverse_hbm3_address(v) for v in vectors],addresses)
        self.assertEqual(len({tuple(hbm3_address(i*32)[:5]) for i in range(64)}),64)
        with self.assertRaises(ValueError):hbm3_address(1)

    def test_conflict_is_one_bank_alternating_rows_and_dependency_chain(self):
        req=row_conflict(16)
        self.assertEqual(len({tuple(r["target_bank"]) for r in req}),1)
        self.assertEqual([r["addr_vec"][5] for r in req],[0,1]*8)
        self.assertEqual(req[-1]["dependency"],[14])

    def test_gemv_work_and_address_coverage(self):
        req=gemv();c=validate_trace(req)
        self.assertEqual(c,dict(request_count=1032,read_bytes=33024,useful_flops=32768))
        self.assertEqual(len({r["address"] for r in req}),1032)
        events=[dict(id=r["id"],consumed=r["id"]+1) for r in req]
        self.assertEqual(verify_gemv_consumption(req,events)["result_max_absolute_error"],0)
        with self.assertRaises(ValueError):verify_gemv_consumption(req,events[:-1])

    def test_bad_address_dependency_and_duplicate_request_fail(self):
        req=streaming(4);bad=copy.deepcopy(req);bad[1]["dependency"]=[3]
        with self.assertRaises(ValueError):validate_trace(bad)
        bad=copy.deepcopy(req);bad[1]["addr_vec"][5]+=1
        with self.assertRaises(ValueError):validate_trace(bad)
        bad=copy.deepcopy(req);bad[1]["id"]=0
        with self.assertRaises(ValueError):validate_trace(bad)

    def test_request_lifetime_validation_rejects_early_dependency(self):
        req=row_conflict(2)
        ev=[dict(id=i,accepted=3*i,completed=3*i+1,consumed=3*i+2,address=r["address"],size=32,source=0,useful_flops=0)
            for i,r in enumerate(req)]
        stats=dict(accepted=2,returned=2,consumed=2,useful_bytes=64,useful_flops=0,ticks=6,frontend_cycle_states={"test":6})
        self.assertEqual(validate_events(req,ev,stats)["request_count"],2)
        ev[1]["accepted"]=1
        with self.assertRaises(ValueError):validate_events(req,ev,stats)


if __name__=="__main__":unittest.main()
