---
name: sentiment_scan
track: core
kind: local_formatter
provider: none
requires_env: []
inputs: [items, topic]
outputs: [counts, overall_sentiment, examples]
side_effect: false
---
# sentiment_scan

Classifies already-collected items (from `lookup`, `social_search`,
`get_twitter`, or `fetch`) into positive/negative/neutral buckets using a
small local VI+EN keyword lexicon, and returns counts plus a few example
items per bucket. Use when the user asks about sentiment, reaction, or
public opinion (e.g. "mọi người phản ứng thế nào", "dư luận tích cực hay
tiêu cực") about items already in context — do not call this to fetch new
data first. Purely local: no external API, deterministic, safe to call
repeatedly. This is a lightweight keyword heuristic, not an ML model — treat
`overall_sentiment` as a rough signal, not a certainty.
