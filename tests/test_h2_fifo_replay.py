import unittest
from scripts.audit_h2_fifo import replay


class FifoReplayTests(unittest.TestCase):
    def test_independent_credits_and_fifo_order(self):
        a=(0,4,0);b=(1,0,0);flit=('X',0,0,0)
        events=[(0,1,0,0,'inject',(a,flit)),(1,0,0,0,'pop',(a,flit,[b])),
                (9,-1,1,0,'arrival',(b,flit)),(9,0,1,0,'pop',(b,flit,[]))]
        self.assertEqual(replay(events),1)
        with self.assertRaises(ValueError):replay(events[1:])

    def test_ninth_reserved_flit_rejected(self):
        key=(0,4,0)
        events=[(0,1,0,0,'inject',(key,('X',0,i,0))) for i in range(9)]
        with self.assertRaises(ValueError):replay(events)


if __name__=='__main__':unittest.main()
