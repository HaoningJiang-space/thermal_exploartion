import json
from pathlib import Path
import unittest

import numpy as np
from scipy.linalg import expm

from thermal_exploration.periodic import PeriodicAudit
from thermal_exploration.thermal import assemble


class PeriodicClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.cfg=json.loads((root/"configs/pilot.json").read_text())
        cls.g2=json.loads((root/"configs/g2.json").read_text())
        cls.audit=PeriodicAudit(cls.cfg,cls.g2["transient"])

    def test_constant_power_cycle_equals_steady_temperature(self):
        p=np.r_[np.full(16,1.2),np.full(16,2.1)]
        expected=25+self.audit.lu.solve(np.r_[p,np.zeros(16)])[:32]
        r=self.audit.audit([{"name":"constant","duration_s":0.00002,"power_w":p.tolist()}])
        np.testing.assert_allclose(r["node_peak_lower_c"],expected,atol=1e-7)
        np.testing.assert_allclose(r["node_peak_upper_c"],expected,atol=1e-7)

    def test_periodic_closure_and_mean_energy_balance(self):
        p=np.r_[np.full(16,2.0),np.full(16,.4)]
        q=np.r_[np.full(16,.5),np.full(16,3.0)]
        r=self.audit.audit([{"name":"a","duration_s":.00001,"power_w":p.tolist()},
                            {"name":"b","duration_s":.0006,"power_w":q.tolist()}])
        self.assertLess(r["periodic_closure_error_k"],1e-6)
        self.assertLess(r["mean_energy_balance_error_k"],1e-6)
        self.assertTrue(np.all(np.asarray(r["node_peak_upper_c"])>=np.asarray(r["node_peak_lower_c"])-1e-8))
        for s in r["segment_audits"]:self.assertLessEqual(s["maximum_interpolation_bound_gap_c"],.002)

    def test_modal_propagator_matches_independent_matrix_exponential(self):
        a=assemble(4,self.cfg["thermal"]).toarray();mass=self.audit.sqrt_mass**2;t=.00012
        expected=expm(-a/mass[:,None]*t)
        modal=(self.audit.transform*np.exp(-self.audit.eigenvalues*t)[None,:])@self.audit.vectors.T*self.audit.sqrt_mass[None,:]
        np.testing.assert_allclose(modal,expected,atol=1e-10)

    def test_pacing_preserves_dynamic_energy_and_meets_peak_limit(self):
        p0=np.r_[np.full(16,.5),np.full(16,.3)]
        p=p0+np.r_[np.full(16,8.0),np.full(16,8.0)]
        r=self.audit.pace([{"name":"hot","duration_s":.0001,"power_w":p.tolist()}],p0)
        self.assertGreater(r["factor"],1)
        self.assertLessEqual(r["paced"]["logic_peak_upper_c"],85+1e-7)
        self.assertLessEqual(r["paced"]["dram_peak_upper_c"],85+1e-7)


if __name__=="__main__":unittest.main()
