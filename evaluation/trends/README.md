# Trend detector evaluation

Two registered algorithms are evaluated on the same deterministic 10,000-record
synthetic corpus and four planted incidents:

- `simple_rate_change` pools binary rates over the current seven days and previous
  28 days, then applies support, absolute-change, and relative-change gates.
- `candidate_statistical` applies the same operational gates and additionally
  requires a Beta-Binomial posterior probability of at least `0.98` in the expected
  direction. Each window uses an independent Beta(1,1) prior.

Event identifiers are withheld from both detectors and used only to construct truth
intervals. Consecutive candidate days form alert episodes, which are matched
one-to-one to planted events. Each report also evaluates the same seed after all
planted event rules are removed.

| Metric | Simple rate | Statistical candidate |
| --- | ---: | ---: |
| Incident recall | 1.0000 | 1.0000 |
| Episode precision | 0.3077 | 0.3636 |
| Alert episodes | 13 | 11 |
| False episodes | 9 | 7 |
| False episodes / 100 evaluable series-days | 0.5409 | 0.4207 |
| Mean detection delay | 7.25 days | 8.00 days |
| No-incident alert episodes | 9 | 6 |

The promotion gate requires non-decreasing recall, higher precision, a lower false
episode rate, non-increasing mean delay, and a lower no-incident alert rate. The
candidate passes four criteria but increases mean delay by 0.75 days. The generated
decision therefore retains `simple_rate_change` as the default while keeping
`candidate_statistical` selectable for inspection.

Reproduce all three checked-in reports:

```sh
cd services/decision-worker
uv run --locked feedback-trends evaluate --algorithm simple_rate_change
uv run --locked feedback-trends evaluate --algorithm candidate_statistical
uv run --locked feedback-trends compare
```

The configs and reports record generator and configuration hashes, per-event delay,
episode starts, exact window counts and rates, posterior probability where
applicable, and detector exclusion reasons. The dashboard fixtures are generated
from these reports with `scripts/build_trend_dashboard_fixture.py`.

This comparison uses one synthetic seed. The `0.98` candidate threshold was explored
on that seed and is not held out, there is no multiple-testing correction, and
neither detector is calibrated for live traffic. Posterior probability is conditional
on the configured prior and binary-window model; it is not a probability that an
alert is correct.
