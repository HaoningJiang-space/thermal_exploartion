# Internal DRAM / Logic clock-domain erratum

The October 11 crossover audit found a physical-time mismatch in the older
internal HB surrogate executions: `hb_trace.py` quantized DRAM timing at 0.5 ns,
but internal organization/D1, D2 and H2 drivers advanced that device once every
reported 0.25 ns Logic tick. State/timing checks in DRAM cycles still passed.
They did not check the physical time conversion. Timing parameters were thus
too fast by a factor of two relative to Logic/HB/NoC resources.

The corrected drivers advance DRAM after every two Logic ticks and translate
DRAM response/command timestamps into Logic ticks at interfaces. Standard G4
HBM3 uses the DRAM clock as its reporting domain and keeps the generic driver's
default ratio of one; its existing reference checks are not this affected path.

Published artifacts remain immutable. The old D1 26.599 TB/s is no longer an
independently grounded physical service anchor. Old Stage 1–4 calculations can
be read as conditional results under that assumed service budget, **not** as
validated performance of the stated 0.5 ns device. Old H2–H3 latency agreements
were agreements within the faulty clock contract and do not qualify the
corrected physical-time model. D2/organization/D1 absolute rates and relative
comparisons with fixed HB/Logic budgets require reruns before physical claims.
G1/G2 analytical negative results retain their original assumption scope.

The new experiment preserves nominal-service controls, remeasures a bounded
streaming service point, and reruns detailed QKV/FIFO cases. It does not silently
edit historical numbers or extrapolate a corrected scalar to every access.
