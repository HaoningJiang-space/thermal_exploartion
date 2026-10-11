# Generated DRAM clock qualification and withdrawn diagnosis

The initial October 11 diagnosis in commits 01009c4–1f28785 was **incorrect**.
It inspected Python `resolve()['tCK_ps']=500` and assumed each native tick was
0.5 ns. The pinned Ramulator HBM3 model has `tick_multiplier=2`. Its serializer
doubles all timing counts and divides `tCK_ps` by two. Generated native ticks
are 0.25 ns, matching the Logic driver. For example, Python RCD 5 CK and CK 500 ps
become native RCD 10 ticks and tick 250 ps: both describe 2.5 ns.

The previous internal organization/D1/D2/H2 drivers advanced the device once
per 0.25 ns Logic tick. That conversion was already correct. The recent divide
by two instead **stretched every DRAM timing by two**, relative to HB/Logic/NoC.
The measured 13.21 TB/s is therefore a slow-DRAM control, not a corrected physical
anchor. The original 26.599 TB/s remains an assumed-surrogate measurement, not
device calibration. Historical artifacts are unchanged; their clock conversion
is not invalidated by this withdrawn diagnosis.

The new `ClockContract` verifies the **serialized native configuration**, not
the pre-conversion Python CK. Native drivers return to ratio 1; emitted commands
are independently replayed under the same generated tick contract. Ratio 2 runs
are retained as retired slow-timing controls and are excluded from the primary
architecture results. No ratios or rates are silently multiplied to invent a
new result; primary service and representative kernels are rerun.

The pinned upstream defines the conversion in
[DRAMStandard.to_config](https://github.com/CMU-SAFARI/ramulator2/blob/c6c7a5de0cef35935d6fad7369e6271406798865/python/ramulator/dram/spec.py)
and `HBM3.tick_multiplier=2`. Inspect the experiment's resolved and serialized
timings together. The rising-edge-only Column slot occurs once per 0.5 ns CK in
this contract, not once per 1 ns. A 1024 B payload therefore has a shared-command
chip ceiling of 32.768 TB/s across 16 physical regions; HB remains fixed at
32 TB/s. Independent command domains do not imply a free bandwidth gain.
