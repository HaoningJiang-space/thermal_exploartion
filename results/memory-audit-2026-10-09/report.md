# HB–DRAM necessary rate audit

Illustrative parameter assumptions; optimistic independent rate ceilings, no command-level schedule or physical validation.
All resources remain Local. The subarray control is an uncharged known-mechanism oracle, not a new architecture.

16 TB/s HB, conventional bank serialization, gradient cooling:

| Traffic | Workload | Noheat limiting ceiling | Internal ceiling TB/s | T0 useful TB/s | T1 layer useful TB/s | T2 useful TB/s | Thermal loss vs T0 | Timing-only relaxation loss at T2 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full_row_spread | batch1_gemv | HB | 16.3840 | 16.0000 | 5.1793 | 5.4523 | 65.92% | 0.00% |
| full_row_spread | batch32_gemm | Logic_consumption | 16.3840 | 8.1250 | 2.0703 | 2.0750 | 74.46% | 0.00% |
| quarter_row_spread | batch1_gemv | DRAM_internal | 6.5536 | 6.5536 | 4.2636 | 4.4545 | 32.03% | 0.76% |
| quarter_row_spread | batch32_gemm | DRAM_internal | 6.5536 | 6.5536 | 1.9169 | 1.9345 | 70.48% | 0.00% |
| small_row_spread | batch1_gemv | DRAM_internal | 0.8192 | 0.8192 | 0.8192 | 0.8192 | 0.00% | 51.64% |
| small_row_spread | batch32_gemm | DRAM_internal | 0.8192 | 0.8192 | 0.8192 | 0.8192 | 0.00% | 29.22% |
| small_row_concentrated | batch1_gemv | DRAM_internal | 0.0910 | 0.0910 | 0.0910 | 0.0910 | 0.00% | 94.63% |
| small_row_concentrated | batch32_gemm | DRAM_internal | 0.0910 | 0.0910 | 0.0910 | 0.0910 | 0.00% | 92.14% |

Loss columns describe different counterfactuals and must not be added together.
Small useful bytes/ACT and bank concentration are already targets of locality, mapping, Tracker and SALP techniques.
tRRD/tFAW and column-domain scope require actual HB device information. No unresolved HB-specific bottleneck is established.
