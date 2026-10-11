import unittest
from thermal_exploration.clock_contract import ClockContract
class ClockTests(unittest.TestCase):
 def test_elapsed_time_and_noninteger_rejection(self):
  c=ClockContract()
  for t in range(32):self.assertEqual(t*c.dram_ns,c.command_logic_tick(t)*c.logic_ns)
  for t in range(32):self.assertEqual(sum(c.should_tick(x) for x in range(t)),t//2)
  with self.assertRaises(ValueError):ClockContract(.25,.3125).ratio()
 def test_rcd_cannot_be_compressed_into_logic_ticks(self):
  c=ClockContract();act=7;read=12
  self.assertEqual((c.command_logic_tick(read)-c.command_logic_tick(act))*.25,2.5)
  self.assertNotEqual((read-act)*.25,2.5)
if __name__=='__main__':unittest.main()
