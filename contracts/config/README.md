# Runtime feature configuration

`runtime-features-v1.schema.json` reserves the cross-service names for the selected
decision engine and trend algorithm. Environment adapters parse those strings into
language-native enums before application work starts. Unknown names fail closed.

Decision engines are selected as `fixture`, `semif`, `rules`, or `llm`. Trend
algorithms are `simple_rate_change` and `candidate_statistical`. The measured
promotion gate currently retains `simple_rate_change` as the default; both values
resolve through typed registries and unknown values fail before work starts.
