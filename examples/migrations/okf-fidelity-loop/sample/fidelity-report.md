# OKF round-trip fidelity report

Source bundle: `sample/bundle-gen0`

| Generation | Memories | Content bytes | Footer marks | Drift vs source |
| --- | --- | --- | --- | --- |
| 0 (source) | 129 | 37,527 | 130 | +0 B |
| 1 (round trip 1) | 129 | 38,081 | 130 | +554 B |
| 2 (round trip 2) | 129 | 38,081 | 130 | +554 B |
| 3 (round trip 3) | 129 | 38,081 | 130 | +554 B |
| 4 (round trip 4) | 129 | 38,081 | 130 | +554 B |

**Converged at generation 2** — every later round trip reproduces it byte for byte.
