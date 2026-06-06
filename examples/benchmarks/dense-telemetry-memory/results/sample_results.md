# Dense Telemetry Memory Results

Scenario A: context-overhead and latency sprint on dense ICU telemetry logs.

| Backend | Accuracy | Avg retrieved tokens | Total ingestion tokens | p95 latency ms | Stale conflict rate | Signal/noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| append_only_log | 22.2% | 27.56 | 243 | 0.0961 | 11.1% | 0.29 |
| windowed_recent_log | 11.1% | 4.22 | 243 | 0.018 | 0.0% | 0.84 |
| active_telemetry_digest | 100.0% | 29.33 | 243 | 0.0523 | 0.0% | 0.58 |

## Cross-session degradation (accuracy)

- **append_only_log**: shift-01=22%, shift-02=22%, shift-03=22%, shift-04=22%, shift-05=22%, shift-06=22%, shift-07=22%
- **windowed_recent_log**: shift-01=22%, shift-02=0%, shift-03=0%, shift-04=11%, shift-05=11%, shift-06=0%, shift-07=11%
- **active_telemetry_digest**: shift-01=33%, shift-02=44%, shift-03=44%, shift-04=56%, shift-05=56%, shift-06=78%, shift-07=100%

The active telemetry digest keeps one current fact per clinical key, suppresses superseded vitals and contraindicated medications, and retrieves only question-relevant evidence. Append-only logs demonstrate token inflation and stale conflicts; recent-window logs trade footprint for lost durable allergies and baseline diagnoses.
