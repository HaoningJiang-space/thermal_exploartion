"""Physical clock-domain contract; command cycles never mean Logic cycles."""
from dataclasses import dataclass
from math import isclose
@dataclass(frozen=True)
class ClockContract:
 logic_ns:float=.25
 dram_ns:float=.5
 def ratio(self):
  value=self.dram_ns/self.logic_ns
  if min(self.logic_ns,self.dram_ns)<=0 or not isclose(value,round(value)) or value<1:raise ValueError('Clock ratio must be a positive integer')
  return round(value)
 def command_logic_tick(self,dram_tick):return dram_tick*self.ratio()
 def should_tick(self,logic_tick):return logic_tick%self.ratio()==self.ratio()-1
 def validate_device(self,dram):
  reported=dram.resolve()[1]['tCK_ps']/1000
  if not isclose(reported,self.dram_ns):raise ValueError('DRAM model period differs from execution clock contract')
  return dict(logic_tick_ns=self.logic_ns,dram_tick_ns=self.dram_ns,logic_ticks_per_dram_tick=self.ratio(),command_trace_clock='DRAM',request_trace_clock='Logic',boundary_rule='DRAM tick completes after each ratio Logic ticks; callback depart multiplied by ratio')
