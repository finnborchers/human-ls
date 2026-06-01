# Benchmark Tests Status - 2026-05-14

This file documents the current benchmark test status for the 120 reviewed hospital reviews benchmark.

## Benchmark Setup

- Reference benchmark:
  - `analysis/llm/benchmark_comparison/benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json`
- Evaluation sample:
  - `analysis/llm/samples/review_labels_benchmark_ids_120.txt`
- Compare script:
  - `scripts/compare_benchmark.py`
- Plot script:
  - `scripts/plot_benchmark.py`

The benchmark compares model-predicted `problem_labels` and `strength_labels` against the reviewed benchmark labels.

## Dashboard Status

### Cost and request status

- Total API requests so far: `1,187`
- Total spend so far: `$0.70`

### Token usage

- Total tokens so far: `1,762,828`

By day:

| Date | Total tokens | Input tokens | Output tokens |
|---|---:|---:|---:|
| 2026-05-12 | 595,300 | 434,900 | 160,400 |
| 2026-05-13 | 304,700 | 299,000 | 5,600 |
| 2026-05-14 | 1,087,000 | 1,029,000 | 57,743 |

Note: the dashboard values above are recorded as reported during the runs and serve as a project status snapshot.

## Tested Variants

### `V1`

- Files:
  - `scripts/prompt_flat_v1.py`
  - `scripts/analyze_llm_flat_v1_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_120_labled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_120_plot.png`
- Setup:
  - flat extraction prompt
  - full metadata in prompt
  - model alias `gpt-4.1-mini`
- Result:
  - exact matches: `46`
  - matched labels: `577`
  - missing labels: `102`
  - extra labels: `44`
- Bucket breakdown:
  - positive: exact `23`, matched `128`, missing `9`, extra `18`
  - negative: exact `10`, matched `134`, missing `40`, extra `19`
  - mixed_hard: exact `13`, matched `315`, missing `53`, extra `7`
- Main pattern:
  - best observed run so far
  - strongest overall benchmark alignment
  - especially strong compared with all later prompt variants

### `V1.1`

- Files:
  - `scripts/prompt_flat_v1_1.py`
  - `scripts/analyze_llm_flat_v1_1_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_1_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_1_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_1_120_plot.png`
- Setup:
  - review only
  - metadata removed
  - stricter label guidance and more explicit restrictions
- Result:
  - exact matches: `20`
  - matched labels: `458`
  - missing labels: `221`
  - extra labels: `108`
- Bucket breakdown:
  - positive: exact `9`, matched `98`, missing `39`, extra `17`
  - negative: exact `9`, matched `111`, missing `63`, extra `33`
  - mixed_hard: exact `2`, matched `249`, missing `119`, extra `58`
- Main pattern:
  - much worse than `V1`
  - strong drop in recall
  - mixed bucket deteriorated sharply

### `V1.2`

- Files:
  - `scripts/prompt_flat_v1_2.py`
  - `scripts/analyze_llm_flat_v1_2_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_2_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_2_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_2_120_plot.png`
- Setup:
  - same guidance as `V1`
  - review only
  - metadata removed
- Result:
  - exact matches: `23`
  - matched labels: `467`
  - missing labels: `212`
  - extra labels: `117`
- Bucket breakdown:
  - positive: exact `13`, matched `108`, missing `29`, extra `21`
  - negative: exact `7`, matched `113`, missing `61`, extra `38`
  - mixed_hard: exact `3`, matched `246`, missing `122`, extra `58`
- Main pattern:
  - slightly better than `V1.1`
  - still clearly worse than `V1`
  - indicates that removing metadata alone already hurts benchmark performance

### `V1.3`

- Files:
  - `scripts/prompt_flat_v1_3.py`
  - `scripts/analyze_llm_flat_v1_3_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_3_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_3_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_3_120_plot.png`
- Setup:
  - same guidance as `V1`
  - reduced metadata only:
    - `star_rating`
    - `like_count`
    - `has_owner_response`
- Result:
  - exact matches: `18`
  - matched labels: `477`
  - missing labels: `202`
  - extra labels: `156`
- Bucket breakdown:
  - positive: exact `10`, matched `109`, missing `28`, extra `36`
  - negative: exact `7`, matched `123`, missing `51`, extra `40`
  - mixed_hard: exact `1`, matched `245`, missing `123`, extra `80`
- Main pattern:
  - no recovery from metadata reduction
  - strongest overlabeling among the metadata ablation tests
  - especially unstable in `mixed_hard`

### `V1.4`

- Files:
  - `scripts/prompt_flat_v1_4.py`
  - `scripts/analyze_llm_flat_v1_4_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_4_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_4_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_4_120_plot.png`
- Setup:
  - full metadata retained
  - targeted prompt clarifications for known weak labels
  - explicit strengthening and braking rules for selected categories
- Result:
  - exact matches: `24`
  - matched labels: `429`
  - missing labels: `250`
  - extra labels: `133`
- Bucket breakdown:
  - positive: exact `12`, matched `106`, missing `31`, extra `27`
  - negative: exact `8`, matched `104`, missing `70`, extra `34`
  - mixed_hard: exact `4`, matched `219`, missing `149`, extra `72`
- Main pattern:
  - targeted verbal corrections did not help
  - prompt appears oversteered
  - both underdetection and overlabeling increased

### `V1.5`

- Files:
  - `scripts/analyze_llm_flat_v1_5_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_5_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_5_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_5_120_plot.png`
- Setup:
  - exact `V1` prompt logic
  - full metadata retained
  - pinned model snapshot: `gpt-4.1-mini-2025-04-14`
  - `temperature=0`
- Result:
  - exact matches: `26`
  - matched labels: `498`
  - missing labels: `181`
  - extra labels: `120`
- Bucket breakdown:
  - positive: exact `14`, matched `117`, missing `20`, extra `23`
  - negative: exact `9`, matched `120`, missing `54`, extra `30`
  - mixed_hard: exact `3`, matched `261`, missing `107`, extra `67`
- Main pattern:
  - did not reproduce the original `V1` result
  - substantially worse than `V1`
  - suggests that either model alias behavior, temperature, or both influenced the earlier result

### `V1.6`

- Files:
  - `scripts/prompt_flat_v1_6.py`
  - `scripts/analyze_llm_flat_v1_6_gpt.py`
  - `analysis/llm/benchmark_comparison/reviews_v1_6_120_labeled.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_6_120_compare.json`
  - `analysis/llm/benchmark_comparison/reviews_v1_6_120_plot.png`
- Setup:
  - based on `V1.5`
  - full metadata retained
  - pinned model snapshot: `gpt-4.1-mini-2025-04-14`
  - `temperature=0`
  - 6 few-shot examples embedded directly in the prompt
  - examples copied verbatim from the reviewed benchmark
- Important methodological note:
  - this is an in-sample few-shot steering test
  - the examples come from the same 120-review benchmark that is also used for evaluation
- Result:
  - exact matches: `20`
  - matched labels: `440`
  - missing labels: `239`
  - extra labels: `114`
- Bucket breakdown:
  - positive: exact `7`, matched `98`, missing `39`, extra `33`
  - negative: exact `6`, matched `113`, missing `61`, extra `30`
  - mixed_hard: exact `7`, matched `229`, missing `139`, extra `51`
- Main pattern:
  - few-shot prompting did not improve performance
  - extra labels fell slightly relative to `V1.5`, but recall dropped further
  - even exact benchmark examples did not recover `V1`

## Cross-Version Summary

### Relative position of the variants

- `V1` is the clear best observed configuration.
- `V1.5` is the strongest of the later controlled follow-up runs, but still clearly worse than `V1`.
- `V1.1`, `V1.2`, `V1.3`, `V1.4`, and `V1.6` all underperform relative to `V1`, with different tradeoffs between recall loss and overlabeling.
- The middle group should be interpreted cautiously because some variants have slightly better exact-match counts while being much worse on missing or extra labels.

### Main conclusions so far

- The original `V1` run remains the strongest observed result.
- Removing metadata consistently hurt performance.
- Reducing metadata did not recover the original result.
- Adding more restrictive or more explicit rule text did not improve alignment.
- Re-running `V1` under a pinned snapshot and `temperature=0` did not reproduce the original `V1` quality.
- Exact in-sample few-shot examples also did not improve the benchmark result.

### Current working interpretation

- The extraction behavior is highly sensitive to prompt and model context changes.
- More prompt structure has not translated into better benchmark alignment.
- The strongest known result still comes from the comparatively simple original `V1` setup.
- The next likely leverage point is not additional prompt wording, but a better data strategy:
  - out-of-sample few-shot evaluation
  - train/eval split
  - or fine-tuning preparation

## `V1.7` Fine-Tuning Follow-Up

### Full-120 diagnostic

- fine-tuned model:
  - `ft:gpt-4.1-mini-2025-04-14:personal::DfW1e1JT`
- full 120-review result:
  - exact matches: `53`
  - matched labels: `572`
  - missing labels: `107`
  - extra labels: `68`

Interpretation:

- `V1.7` improved in-sample fit on the 120 reviewed benchmark cases
- this is the strongest exact-match count observed on the full set

### Holdout20 generalization

The 20-review holdout was not included in training and is therefore the more relevant generalization signal.

- `V1` holdout20:
  - exact matches: `8`
  - matched labels: `92`
  - missing labels: `18`
  - extra labels: `5`
- `V1.7` holdout20:
  - exact matches: `1`
  - matched labels: `77`
  - missing labels: `33`
  - extra labels: `25`

Interpretation:

- the fine-tuned model generalizes poorly beyond its training split
- `V1.7` should therefore be understood as an overfit fine-tuning result, not as the best general-purpose model

## Holdout20 Base-Model Sweep

To test whether stronger or more expensive base models solve the task more robustly, a holdout-only sweep was run with the same `V1` prompt structure.

### `gpt-5.4-mini`

- exact matches: `2`
- matched labels: `72`
- missing labels: `38`
- extra labels: `43`
- average request time: `1.45s`

Main pattern:

- very fast
- weak alignment on unseen reviews
- low recall and still many extra labels

### `gpt-5.1` with `reasoning_effort=low`

- exact matches: `1`
- matched labels: `89`
- missing labels: `21`
- extra labels: `65`
- average request time: `2.05s`

Main pattern:

- highest matched-label count among the new base models
- but by far the highest overlabeling
- behaves like a high-recall, low-precision model on this benchmark

### `gemini-2.5-flash`

- exact matches: `1`
- matched labels: `78`
- missing labels: `32`
- extra labels: `42`
- average request time: `5.80s`

Main pattern:

- somewhat more controlled than `gpt-5.1`
- still clearly behind `V1`
- unstable especially on mixed and ambiguous reviews

### `gemini-2.5-pro`

- exact matches: `1`
- matched labels: `72`
- missing labels: `38`
- extra labels: `38`
- average request time: `11.55s`

Main pattern:

- cleaner than `gpt-5.1` on extra labels
- but does not improve exact matches or recall enough
- not competitive with `V1` on generalization

## `V1.8` Paraphrase-Augmented Fine-Tuning

`V1.8` tests whether automated paraphrase augmentation can improve fine-tuning generalization.

Setup:

- source split:
  - original `V1.7` train100 / holdout20
- augmentation:
  - 40 selected hard training reviews
  - 2 accepted paraphrases per source review
  - 80 synthetic paraphrases total
- training set size:
  - 100 original reviewed train examples
  - 80 synthetic paraphrase examples
  - 180 total training examples
- generator and judge:
  - `gpt-5.1` with `reasoning_effort=low`
- fine-tuning base model:
  - `gpt-4.1-mini-2025-04-14`

Fine-tuning job:

- job id:
  - `ftjob-bfXlxBKddowoqAt4QyRmcWft`
- fine-tuned model:
  - `ft:gpt-4.1-mini-2025-04-14:personal::DfmG9LLl`
- status:
  - `succeeded`
- trained tokens:
  - `460,161`
- hyperparameters:
  - `batch_size = 1`
  - `learning_rate_multiplier = 2.0`
  - `n_epochs = 3`

### Holdout20 result

- `V1` holdout20:
  - exact matches: `8`
  - matched labels: `92`
  - missing labels: `18`
  - extra labels: `5`
- `V1.7` holdout20:
  - exact matches: `1`
  - matched labels: `77`
  - missing labels: `33`
  - extra labels: `25`
- `V1.8` holdout20:
  - exact matches: `3`
  - matched labels: `76`
  - missing labels: `34`
  - extra labels: `23`

Interpretation:

- `V1.8` improves slightly over `V1.7`
  - exact matches: `1 -> 3`
  - extra labels: `25 -> 23`
- however, it still remains clearly below `V1`
- the augmentation therefore gives a weak positive signal, but not a strong enough gain to replace the original baseline

### Key methodological observation

The augmentation pipeline accepted all synthetic examples:

- `80/80` paraphrases passed the semantic judge
- no candidate was rejected
- no reserve review had to be used

Interpretation:

- the semantic QA gate was likely too permissive
- this means `V1.8` is informative, but not yet a strict high-confidence augmentation setup
- the main open question is not whether paraphrase augmentation can help at all, but whether it can help under substantially stricter quality control

## New Cross-Test Learnings

### 1. `V1` remains the strongest generalization baseline

This is now the most stable result across all experiments:

- `V1` is still the best known operational setup for unseen reviews
- no later prompt variant beat it
- the fine-tuned model did not beat it on holdout20
- stronger base models also did not beat it on holdout20

### 2. Metadata is useful in the current task setup

The metadata ablation line was consistent:

- removing metadata hurt benchmark quality
- reducing metadata also hurt benchmark quality
- the original full-metadata prompt remains the strongest prompt configuration

### 3. More prompt structure did not improve calibration

The different prompt interventions all failed in related ways:

- stricter rules reduced recall
- targeted clarifications oversteered the model
- exact benchmark few-shot examples did not improve out-of-sample performance

The practical lesson is that adding more instruction text did not solve the main task-calibration problem.

### 4. Fine-tuning currently overfits faster than it generalizes

`V1.7` improved in-sample metrics on the reviewed 120 cases, but degraded sharply on the 20 unseen holdout reviews.

This means:

- the current training set is probably too small or too narrow
- the model learns benchmark-specific patterns faster than robust label behavior

### 5. Better models are not enough by themselves

The base-model sweep suggests that the current bottleneck is not simply “use a more powerful model”.

Instead, the main issue appears to be:

- label calibration
- semantic drift into nearby labels
- insufficiently diverse task-specific training examples

### 6. The dominant failure mode is overlabeling plus label substitution

Across the newer models, the recurring error pattern is:

- predicting semantically nearby but benchmark-inconsistent labels
- adding strong care-related labels too often
- substituting staff/support labels instead of matching the reviewed gold label exactly
- struggling especially on mixed reviews and nuanced positive/negative combinations

### 7. Paraphrase augmentation is promising in principle, but the first automated version was too weakly controlled

`V1.8` suggests:

- synthetic wording variation can improve over an overfit fine-tune
- but the current automated judge did not filter aggressively enough
- stronger synthetic-data QA is required before augmentation can be considered a primary improvement path

### 8. Explicit Structured Outputs are a major regression factor

The `V1.9` control run added an important technical finding:

- the earlier `V1` family already used `instructor`
- `instructor` itself is therefore not the new variable
- the major new factor is explicit:
  - `response_format = json_schema`

`V1.9` was designed as a focused control against `V1.5`:

- same `V1` prompt family
- same full metadata block
- same snapshot model:
  - `gpt-4.1-mini-2025-04-14`
- same `temperature=0`
- but explicit `json_schema` instead of the earlier `instructor` response-model path

Results on the reviewed 120 benchmark:

- `V1.5`:
  - exact `26`
  - matched `498`
  - missing `181`
  - extra `120`
- `V1.9`:
  - exact `19`
  - matched `497`
  - missing `182`
  - extra `174`

Interpretation:

- recall is almost unchanged
- the main regression is a large jump in **extra labels**
- explicit structured outputs therefore appear to worsen label calibration substantially

### 9. Batch API itself is not the main problem

`V1.10` then isolated the Batch API itself by holding everything else fixed relative to `V1.9`:

- same snapshot model
- same `temperature=0`
- same explicit `json_schema`
- same `V1` prompt
- but now through the **Batch API**

Results on the same reviewed 120 benchmark:

- `V1.9`:
  - exact `19`
  - matched `497`
  - missing `182`
  - extra `174`
- `V1.10`:
  - exact `18`
  - matched `494`
  - missing `185`
  - extra `167`

Interpretation:

- `V1.10` is only slightly worse than `V1.9`
- the Batch API therefore adds at most a smaller secondary effect
- the dominant quality drop already exists before batch execution, once the run moves onto explicit `json_schema`

## Full-Run Descriptive Analysis (`30,863` Reviews)

The large-scale batch path was then carried through to complete corpus coverage:

- `10000_ids` fully materialized
- `20863_ids` fully materialized
- merged full run:
  - `30,863` reviews
- parse errors:
  - `0`

Artifacts:

- labeled full run:
  - `analysis/llm/full_run/v1_batch_run/merged/all_scopes_labeled.json`
- merged summary:
  - `analysis/llm/full_run/v1_batch_run/merged/all_scopes_summary.json`
- descriptive analysis summary:
  - `analysis/llm/full_run/descriptive_analysis/summary.json`
- descriptive report:
  - `analysis/llm/full_run/descriptive_analysis/fullrun_descriptive_report.md`

### Batch processing setup

The full-run path was not executed as one giant batch request.

Reason:

- the first large submission attempts exposed an OpenAI Batch queue constraint
- several large jobs submitted in parallel failed with:
  - `token_limit_exceeded`
- the practical limit was the number of **enqueued tokens**, not the overall account credit balance

Operational consequence:

- the corpus was split into:
  - `10000_ids`
  - `20863_ids`
- each scope was further split into medium-sized batch files
- the first scope used:
  - `5 x 2000` reviews
- the second scope used:
  - `10 x 2000`
  - `1 x 863`

Execution strategy:

- upload one batch input file at a time
- submit one batch job at a time
- poll status every `300` seconds
- fetch and materialize completed batches
- only then submit the next batch

This serial autopilot approach was chosen specifically to stay below the observed queue limit while still preserving the cost advantages of the Batch API.

### Batch processing duration

Based on the OpenAI batch job timestamps:

- `10000_ids`
  - first batch created to last batch completed:
    - `2,663s`
    - about `44m 23s`
- `20863_ids`
  - first batch created to last batch completed:
    - `11,382s`
    - about `3h 09m 42s`

Combined batch-processing time across both scopes:

- `14,045s`
- about `3h 54m 05s`

These timings refer to the API-side batch processing windows from job creation to completion. The observed wall-clock runtime can be slightly longer because the local autopilot polls in fixed intervals and materializes outputs between cycles.

### Batch processing cost

Token usage from the batch job artifacts:

- `10000_ids`
  - input tokens:
    - `8,585,445`
  - output tokens:
    - `241,783`
  - total tokens:
    - `8,827,228`
- `20863_ids`
  - input tokens:
    - `17,904,423`
  - output tokens:
    - `499,129`
  - total tokens:
    - `18,403,552`

Combined full-run token volume:

- input tokens:
  - `26,489,868`
- output tokens:
  - `740,912`
- total tokens:
  - `27,230,780`

Observed credit usage:

- `20863_ids`
  - credit balance changed from `7.98 USD` to `4.00 USD`
  - observed run cost:
    - `3.98 USD`
- `10000_ids`
  - earlier user-observed balance change suggested an approximate cost of:
    - about `1.93 USD`

Approximate total full-run cost:

- about `5.91 USD`

Interpretation:

- the batch path was economically efficient enough to process the full `30,863`-review corpus
- but this cost efficiency came with the already documented quality tradeoff relative to the original synchronous `V1` baseline

### Global distribution

- reviews with no labels:
  - `1,005` (`3.26%`)
- reviews with only problem labels:
  - `9,528` (`30.87%`)
- reviews with only strength labels:
  - `13,347` (`43.25%`)
- reviews with both problem and strength labels:
  - `6,983` (`22.63%`)
- mean labels per review:
  - `3.59`
- median labels per review:
  - `3`
- max labels on a single review:
  - `34`

### Dominant problem themes

Top problem labels:

- `care.treatment` (`5,013`)
- `access.waiting` (`4,420`)
- `staff.friendliness` (`4,088`)
- `staff.respect` (`3,966`)
- `staff.seriousness` (`3,020`)

### Dominant strength themes

Top strength labels:

- `staff.friendliness` (`15,723`)
- `staff.empathy` (`9,742`)
- `care.treatment` (`9,014`)
- `care.competence` (`7,411`)
- `staff.respect` (`3,692`)

### Frequent combinations

Most common problem-problem combinations:

- `staff.friendliness` + `staff.respect` (`1,678`)
- `care.treatment` + `staff.respect` (`1,402`)
- `care.competence` + `care.treatment` (`1,359`)

Most common problem-strength combinations:

- `staff.friendliness` + `staff.friendliness` (`1,101`)
- `access.waiting` + `staff.friendliness` (`1,088`)
- `care.treatment` + `staff.friendliness` (`929`)

Interpretation:

- the full-run outputs are now complete enough for a global thematic overview
- the corpus is dominated by staff-related and care-related labels on both problem and strength sides
- a large share of reviews are positive-only or problem-only, while about a fifth are mixed-label reviews
- the full-run should still be interpreted as a **coverage analysis with known quality tradeoffs**, not as benchmark-equivalent output

## Full-Run Metadata Analysis

A second analysis stage was then added on top of the same merged `30,863`-review corpus to focus on the most robust metadata dimensions:

- `star_rating`
- `like_count`
- `has_owner_response`

Artifacts:

- metadata summary:
  - `analysis/llm/full_run/metadata_analysis/summary.json`
- metadata report:
  - `analysis/llm/full_run/metadata_analysis/metadata_analysis_report.md`
- metadata plots:
  - `analysis/llm/full_run/metadata_analysis/plots/`

### Star-rating profiles

The star signal behaves as a strong polarity proxy in the labeled corpus:

- `1★`
  - avg problem labels:
    - `3.18`
  - avg strength labels:
    - `0.27`
  - problem-only reviews:
    - `80.09%`
- `5★`
  - avg problem labels:
    - `0.21`
  - avg strength labels:
    - `3.42`
  - strength-only reviews:
    - `80.01%`
- `3★`
  - mixed reviews:
    - `66.58%`
  - highest mixed share across the star buckets

Interpretation:

- low-star reviews are strongly problem-dominated
- high-star reviews are strongly strength-dominated
- `3★` reviews are especially useful as mixed / ambivalent cases

### Like-salience patterns

The like counts show a clear descriptive association with more conflict-heavy reviews:

- `0` likes
  - avg star rating:
    - `3.86`
  - avg problem labels:
    - `1.03`
- `25+` likes
  - avg star rating:
    - `1.39`
  - avg problem labels:
    - `4.51`

Intermediate buckets follow the same general direction:

- with more likes, average star ratings decrease
- with more likes, average problem-label density increases

Interpretation:

- more visible reviews appear descriptively more negative and more problem-oriented
- this should be framed as a corpus-level association, not as a claim about objective relevance

### Owner-response profile

Reviews with owner responses differ descriptively from those without:

- with owner response
  - avg strength labels:
    - `2.35`
  - no-label reviews:
    - `1.82%`
- without owner response
  - avg strength labels:
    - `1.99`
  - no-label reviews:
    - `3.86%`
  - avg likes:
    - `3.13`

Interpretation:

- owner response is a useful descriptive grouping signal
- but it should be treated as a **selection signal**, not as an intervention effect or causal mechanism

### Metadata limits

The remaining metadata fields are less suitable as primary next-step analyses:

- `review_time`
  - available mainly as relative free-text strings such as:
    - `vor einem Jahr`
    - `vor 3 Monaten`
  - usable only as coarse buckets like:
    - days / weeks / months / years
- `clinic_name`
  - effectively unavailable in the merged full-run metadata

This means the strongest next-step metadata analyses are the ones above, not clinic-level or fine-grained temporal comparisons.

## `V1.9` JSON-Schema Control Run

Purpose:

- isolate the effect of explicit `response_format = json_schema`
- keep the rest of the setup aligned with `V1.5`

Configuration:

- original `V1` prompt
- full metadata
- model:
  - `gpt-4.1-mini-2025-04-14`
- `temperature=0`
- synchronous execution
- explicit local JSON parsing and validation against `FlatExtraction`

Results:

- overall:
  - exact `19`
  - matched `497`
  - missing `182`
  - extra `174`
- positive:
  - exact `10`
  - matched `117`
  - missing `20`
  - extra `40`
- negative:
  - exact `7`
  - matched `124`
  - missing `50`
  - extra `41`
- mixed_hard:
  - exact `2`
  - matched `256`
  - missing `112`
  - extra `93`

Main comparison vs `V1.5`:

- exact dropped from `26` to `19`
- matched stayed essentially flat (`498` to `497`)
- missing stayed essentially flat (`181` to `182`)
- extra labels increased sharply (`120` to `174`)

Takeaway:

- the explicit JSON-schema path is much more overlabel-prone than the earlier synchronous `instructor` path

## `V1.10` Batch-vs-Sync Control Run

Purpose:

- isolate the additional effect of the Batch API, after `V1.9` had already isolated `json_schema`

Configuration:

- original `V1` prompt
- full metadata
- model:
  - `gpt-4.1-mini-2025-04-14`
- `temperature=0`
- explicit `json_schema`
- **Batch API**
- same reviewed 120 benchmark

Results:

- overall:
  - exact `18`
  - matched `494`
  - missing `185`
  - extra `167`
- positive:
  - exact `8`
  - matched `113`
  - missing `24`
  - extra `47`
- negative:
  - exact `8`
  - matched `125`
  - missing `49`
  - extra `45`
- mixed_hard:
  - exact `2`
  - matched `256`
  - missing `112`
  - extra `75`

Main comparison vs `V1.9`:

- exact:
  - `19 -> 18`
- matched:
  - `497 -> 494`
- missing:
  - `182 -> 185`
- extra:
  - `174 -> 167`

Takeaway:

- the Batch API introduces only a relatively small change compared with the much larger step from `V1.5` to `V1.9`
- the dominant regression signal still comes from explicit structured outputs rather than batching itself

## Overlap48 Readout

The 10k production batch run overlapped with `48` reviewed benchmark cases, which made it possible to compare the large-scale batch path against both old `V1` and the new `V1.9` control.

Results:

- `V1` on overlap48:
  - exact `21`
  - matched `228`
  - missing `41`
  - extra `8`
- 10k batch path on overlap48:
  - exact `8`
  - matched `196`
  - missing `73`
  - extra `70`
- `V1.9` on overlap48:
  - exact `10`
  - matched `195`
  - missing `74`
  - extra `61`

Interpretation:

- the 10k batch path is clearly much weaker than old `V1`
- but it is already quite close to the synchronous `V1.9` JSON-schema control on the same subset
- this reinforces the conclusion that the current batch regression is explained largely by the structured-output path itself, not primarily by the existence of batching

## Current conclusion

At this point the evidence suggests:

- stop treating prompt engineering as the main optimization lever
- stop assuming stronger base models will automatically solve the benchmark
- do not treat `V1.8` as a successful replacement for `V1`
- do not treat the current `json_schema`-based batch path as quality-equivalent to old `V1`
- keep `V1` as the best current operational baseline
- treat the completed full-run as a **descriptive coverage layer**, not as a new best-model result
- focus the next iteration on **better reviewed training data selection**
- if augmentation is revisited, make the QA gate substantially stricter
- if large-scale productive prelabeling is needed again, prefer an explicitly documented tradeoff rather than assuming quality parity with `V1`

The recommended next step is a data-centric one:

- first analyze the now-complete `30,863`-review corpus descriptively
- use the full-run outputs for thematic overview, frequency analysis, and global pattern reporting
- then return to active-learning-style curation of additional reviewed examples
- prioritize disagreement cases, mixed reviews, and the repeated weak labels
- re-run fine-tuning only after the stronger reviewed dataset strategy is defined

## Most Important Error Patterns

### `V1` baseline weaknesses

Most common missing problem labels in `V1`:

- `staff.seriousness`
- `access.waiting`
- `care.competence`
- `communication.information`
- `access.reachability`

Most common extra problem labels in `V1`:

- `access.navigation`
- `care.safety`

Most common extra strength labels in `V1`:

- `staff.empathy`
- `staff.friendliness`

These baseline weaknesses motivated the later prompt variants, but none of the later prompt strategies improved on the original baseline.
