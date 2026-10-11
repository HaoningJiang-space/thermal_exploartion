import unittest
from thermal_exploration.clock_contract import ClockContract
class ClockTests(unittest.TestCase):
 def test_command_domain_remap_does_not_add_banks(self):
  from thermal_exploration.hb_trace import encoded,address_vector,command_domain_vector
  banks=set()
  for tile in range(16):
   for bank in range(16):
    v=address_vector(encoded(tile,bank,123,3),2);w=command_domain_vector(v)
    old=v[0]*16+v[1]*8+v[3]*2+v[4]
    new=w[0]*8+w[3]*2+w[4]
    self.assertEqual(old,new);self.assertEqual(v[5:],w[5:]);banks.add(new)
  self.assertEqual(len(banks),256)
 def test_elapsed_time_and_noninteger_rejection(self):
  c=ClockContract()
  for t in range(32):self.assertEqual(t*c.dram_ns,c.command_logic_tick(t)*c.logic_ns)
  for t in range(32):self.assertEqual(sum(c.should_tick(x) for x in range(t)),t)
  with self.assertRaises(ValueError):ClockContract(.25,.3125).ratio()
 def test_python_ck_is_not_the_native_tick(self):
  class HalfCycleDevice:
   timing_params=['nRCDRD','tCK_ps'];tick_multiplier=2
   def resolve(self):return {},dict(tCK_ps=500,nRCDRD=5)
   def to_config(self):return dict(timing=[10,250])
  device=HalfCycleDevice();c=ClockContract();v=c.validate_device(device)
  self.assertEqual(v['dram_CK_ns'],.5);self.assertEqual(v['dram_tick_ns'],.25)
  self.assertEqual(device.to_config()['timing'][0]*c.dram_ns,2.5)
  with self.assertRaises(ValueError):ClockContract(.25,.5).validate_device(device)
if __name__=='__main__':unittest.main()
