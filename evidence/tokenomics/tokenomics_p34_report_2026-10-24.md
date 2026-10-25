# Tokenomics from per-call usage logs (P34, 2026-10-24)

Sources: `evidence/tokenomics/usage_log_snapshot_p34.jsonl` (snapshot of `data/live/usage_log.jsonl`) and `evidence/usage/usage_log_p33.jsonl`; 30 API calls. All costs are **estimates at OpenAI's published standard rates**, not billed amounts.

## Assumptions and scenarios

- L1 Rates: OpenAI's published standard-tier rates (pricing file); Portkey/Azure billing to the course account is not verified and Portkey's own fees, if any, are not included.
- L2 Token categories per call: uncached input = input_tokens - cached_read_tokens - cache_write_tokens; reasoning tokens are part of output_tokens and are not added again.
- L3 Cache-write duration: the API did not return the 30-minute / 12-hour split, so writes are priced under two scenarios (W30, W12).
- L4 Portkey HITs (header x-portkey-cache-status = HIT) replay the original call's usage and are priced under two scenarios (HIT_FREE, HIT_AS_REPLAYED); they are never counted as provider usage by default.
- L5 Calls without a usable usage object (failed calls) are counted but not priced.

- **W30**: cache writes at the 30-minute rate (the guide's default; the app sets no TTL)
- **W12**: cache writes at the 12-hour rate (upper bound)
- **HIT_FREE**: Portkey response-cache HITs are not billed by the model provider ($0); consistent with the HIT responses lacking Azure headers, not verified
- **HIT_AS_REPLAYED**: HITs billed as if their replayed usage were new (upper bound)

## Calls by kind

| Workflow | Calls | Reached provider (MISS) | Portkey HIT (replayed usage) | Failed |
|---|---|---|---|---|
| chat | 12 | 10 | 2 | 0 |
| extraction | 5 | 3 | 2 | 0 |
| photo_analysis | 4 | 2 | 2 | 0 |
| photo_followup | 4 | 4 | 0 | 0 |
| safety_screen | 5 | 3 | 2 | 0 |

## Measured token categories (mean per provider call)

| Workflow | Uncached input | Cached read | Cache write | Output (incl. reasoning) | Reasoning |
|---|---|---|---|---|---|
| chat | 3 | 1,652 | 557 | 111 | 46 |
| extraction | 945 | 0 | 0 | 213 | 0 |
| photo_analysis | 126 | 0 | 1,441 | 794 | 364 |
| photo_followup | 3 | 0 | 1,670 | 43 | 22 |
| safety_screen | 381 | 0 | 0 | 16 | 0 |

## Estimated cost: P32 vs P34

| Unit | P32 point (P32 caching bounds) | P34, writes at 30 min (W30) | P34, writes at 12 h (W12) | Change (W30 vs P32 point) |
|---|---|---|---|---|
| chat (per question) | $0.000462 ($0.000258–$0.000519) | $0.000284 | $0.000424 | -39% |
| extraction (per call) | $0.000265 ($0.000254–$0.000268) | $0.000201 | $0.000201 | -24% |
| safety_screen (per call) | $0.000082 ($0.000082–$0.000082) | $0.000046 | $0.000046 | -44% |
| photo_analysis (per call) | $0.000539 ($0.000371–$0.000586) | $0.000590 | $0.000770 | +9% |
| photo_followup (per call) | $0.000238 ($0.000066–$0.000286) | $0.000230 | $0.000439 | -3% |

P34 costs are for calls that reached the provider (MISS); Portkey HITs are excluded here and shown below.

## What changed and why

- Method: P32 had only per-question totals, so it priced all input at the uncached rate (point) with all-cached / all-written bounds, and counted possible Portkey repeats as billed (A2, A5). P34 prices each logged call from the token categories the API reported, and separates Portkey HITs (priced only in scenarios).
- Chat (-): P34 questions used more input (4,424 vs 2,514 tokens per question, 2.0 requests each) but 75% of chat input was a cached read at 0.1x; output fell from 422 to 222 tokens. Different questions were asked, so part of the change is the question mix.
- Extraction (-): no caching in either run (prompts below 1,024 tokens); output was lower (213 vs 334 tokens). Most P32 records came from the P30/P31 injection evaluation (attack reports produced long outputs); P34 used three ordinary reports.
- Safety screen (-): no caching in either run (prompts below 1,024 tokens); output was lower (16 vs 81 tokens). Most P32 records came from the P30/P31 injection evaluation (attack reports produced long outputs); P34 used three ordinary reports.
- Photo analysis: most input (1,441 of 1,567 tokens) was a cache write at 1.25x (W30) or 2.5x (W12) and none was read back, so input cost is above P32's all-uncached point estimate; the net change also reflects output (794 vs 704 tokens). Under W12 both photo workflows cost more than P32's point estimate.
- Photo follow-up: most input (1,670 of 1,672 tokens) was a cache write at 1.25x (W30) or 2.5x (W12) and none was read back, so input cost is above P32's all-uncached point estimate; the net change also reflects output (43 vs 93 tokens). Under W12 both photo workflows cost more than P32's point estimate.
- Sample size: P34 has 2-5 provider calls per workflow; differences of this size can come from the inputs chosen, not only from pricing method.

## All logged calls under each scenario (total USD)

| Scenario | Total |
|---|---|
| W30+HIT_FREE | $0.004264 |
| W30+HIT_AS_REPLAYED | $0.006099 |
| W12+HIT_FREE | $0.006156 |
| W12+HIT_AS_REPLAYED | $0.008428 |

## Prompt-cache writes vs reads (provider calls)

| Workflow | Tokens written | Tokens read | Write premium paid (W30) |
|---|---|---|---|
| chat | 5,574 | 16,515 | $0.000139 |
| extraction | 0 | 0 | $0.000000 |
| photo_analysis | 2,882 | 0 | $0.000072 |
| photo_followup | 6,678 | 0 | $0.000167 |
| safety_screen | 0 | 0 | $0.000000 |

## Optimization worth testing next: Make photo follow-ups reuse the prompt cache

- **Observed:** 4 provider follow-up calls each wrote about 1,670 tokens to the prompt cache and read 0, although the questions on the same photo share the instructions, earlier analysis, and image. Today the stable content and the question are sent as one user message.
- **Change to test:** Send the stable part (earlier analysis + image) as its own message before the question, so the cached prefix ends before the part that changes; measure cached_read_tokens on the 2nd and later questions about the same photo.
- **Estimated saving:** about $0.000192 per 2nd-or-later follow-up on the same photo (~83% of a follow-up's W30 cost), if the prefix is read at the cached rate instead of written. Not yet measured.
- **Quality and safety:** Same content and instructions, only split into messages; prompt caching returns fresh model outputs (unlike Portkey's response cache), so answers should not go stale. Must be checked by re-asking the same questions and comparing answers, and by confirming the image is still treated as untrusted content. The first question on a photo still pays the write.
- **Considered but not chosen:**
  - Skipping or sampling the safety screen: about 19% of a report-intake cost at P34 rates, but it would weaken the P31 defense.
  - Leaning on Portkey's response cache: free repeats, but a cached answer can be stale when the shelter or inventory data behind an identical question has changed.
  - Lower reasoning effort or shorter outputs: savings on output tokens, but extraction and vision accuracy would need re-evaluation first.
