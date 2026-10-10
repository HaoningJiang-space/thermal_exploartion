# Preserved integration failures

No failed attempt below contributes a performance measurement or a physical claim.
All successful cases are preserved, including both negative controls.

| Attempt | Observed failure | Correction / final scope |
|---|---|---|
| First official invocation | A controller-test filename did not exist; pytest exit 4, no test execution | Correct documented test directory; 128 unique tests pass. [Log](failed-official-path.log) |
| G4 at 3de8498 | Source guard rejected build-generated C++ formatting before any trace ran | Compare generated-source tokens/includes and record hashes; executable model changes still rejected |
| G4 at 8bc1653 | Required row_policy missing; zero issued commands | Explicit Open policy, matching the declared controller contract. [Log](failed-missing-row-policy.log) |
| G4 at 140b83e | Default External frontend allocated one core's statistics for 16 source IDs; native abort, no valid result | Own 16-source frontend adapter; all per-source counts checked against aggregate counts. [Log](failed-source-count.log) |
| Final a7d3f94 | None | 5/5 finite cases, independent state replay, all 18704 requests and 23580 commands validated |

The full unsuccessful run directories remain outside the source checkout on the execution host.
The public records preserve the failure reason and source revision. No partial timing from an aborted run is reused.
The later 54-test project regression record is [final-tests.log](final-tests.log), source c6442e1.
