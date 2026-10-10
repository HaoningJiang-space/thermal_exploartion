import unittest
import numpy as np
from thermal_exploration.organization import load_exploration
from thermal_exploration.run_h5 import evaluate


class EventThermalTests(unittest.TestCase):
    def test_short_burst_is_not_steady_temperature(self):
        r=dict(time_us=1,variant='sram_baseline',workload='pulse',meta={'tokens':1})
        e=np.zeros((64,32));e[:,0]=1e-9
        x=evaluate(r,e,{'pulse':float(e.sum())},load_exploration(),.3)
        self.assertLess(x['cold_token_sampled_peak_c'],x['periodic_logic_peak_c'])
        self.assertLess(x['energy_balance_error_k'],1e-6)

    def test_nonphysical_input_is_rejected(self):
        r=dict(time_us=1,variant='sram_baseline',workload='bad',meta={'tokens':1})
        with self.assertRaises(ValueError):evaluate(r,-np.ones((64,32)),{},load_exploration(),.3)
        with self.assertRaises(ValueError):evaluate(r,np.zeros((64,32)),{},load_exploration(),0)


if __name__=='__main__':unittest.main()
