# Benchmark Tests Status - 2026-05-14

This file documents the benchmark test status for the reviewed 120-review hospital benchmark.

## Benchmark Setup

- Reviewed reference:
  - `analysis/llm/benchmark_comparison/benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json`
- Full benchmark sample:
  - `analysis/llm/samples/review_labels_benchmark_ids_120.txt`
- Compare:
  - `scripts/compare_benchmark.py`
- Plot:
  - `scripts/plot_benchmark.py`

The benchmark compares model-predicted `problem_labels` and `strength_labels` against the manually reviewed benchmark labels.

## Dashboard Status

### API usage

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

These numbers are recorded as dashboard snapshots from the experiment runs.

## Tested Prompt Variants

### `V1`

- Setup:
  - original flat prompt
  - full metadata in prompt
  - model alias `gpt-4.1-mini`
- Output artifacts:
  - `reviews_v1_120_labled.json`
  - `reviews_v1_120_compare.json`
  - `reviews_v1_120_plot.png`
- Result:
  - exact matches: `46`
  - matched labels: `577`
  - missing labels: `102`
  - extra labels: `44`

### `V1.1`

- Setup:
  - review only
  - metadata removed
  - stricter and more explicit label rules
- Result:
  - exact matches: `20`
  - matched labels: `458`
  - missing labels: `221`
  - extra labels: `108`

### `V1.2`

- Setup:
  - same rules as `V1`
  - review only
  - metadata removed
- Result:
  - exact matches: `23`
  - matched labels: `467`
  - missing labels: `212`
  - extra labels: `117`

### `V1.3`

- Setup:
  - same rules as `V1`
  - reduced metadata only:
    - `star_rating`
    - `like_count`
    - `has_owner_response`
- Result:
  - exact matches: `18`
  - matched labels: `477`
  - missing labels: `202`
  - extra labels: `156`

### `V1.4`

- Setup:
  - full metadata retained
  - targeted clarifications for known weak labels
- Result:
  - exact matches: `24`
  - matched labels: `429`
  - missing labels: `250`
  - extra labels: `133`

### `V1.5`

- Setup:
  - exact `V1` prompt logic
  - full metadata retained
  - pinned snapshot `gpt-4.1-mini-2025-04-14`
  - `temperature=0`
- Result:
  - exact matches: `26`
  - matched labels: `498`
  - missing labels: `181`
  - extra labels: `120`

### `V1.6`

- Setup:
  - based on `V1.5`
  - exact reviewed benchmark examples embedded as few-shot examples
  - in-sample few-shot steering test
- Result:
  - exact matches: `20`
  - matched labels: `440`
  - missing labels: `239`
  - extra labels: `114`

## Current Interpretation

- `V1` remains the strongest observed benchmark result.
- Removing metadata consistently hurt performance.
- Reducing metadata did not recover the original result.
- Additional rule text did not improve alignment.
- Re-running `V1` under a pinned snapshot and `temperature=0` did not reproduce the original `V1` score.
- Exact in-sample few-shot prompting also did not improve the result.

Most important `V1` baseline weaknesses:

- missing problems:
  - `staff.seriousness`
  - `access.waiting`
  - `care.competence`
  - `communication.information`
  - `access.reachability`
- extra problems:
  - `access.navigation`
  - `care.safety`
- extra strengths:
  - `staff.empathy`
  - `staff.friendliness`

## `V1.7` Fine-Tuning Status

The fine-tuning path for `V1.7` has been prepared and the first OpenAI fine-tuning job has succeeded.

Prepared components:

- deterministic `100/20` train-holdout split builder
- OpenAI supervised fine-tuning dataset builder
- OpenAI fine-tuning job wrapper
- fine-tuned inference runner

Fine-tuning job result:

- fine-tuning job id:
  - `ftjob-WaObnRAeOvgiZaFBQ0yvYX8N`
- base model:
  - `gpt-4.1-mini-2025-04-14`
- fine-tuned model:
  - `ft:gpt-4.1-mini-2025-04-14:personal::DfW1e1JT`
- status:
  - `succeeded`
- trained tokens:
  - `222,855`
- training duration:
  - `15 minutes 12 seconds`
- OpenAI-selected hyperparameters:
  - `batch_size = 1`
  - `learning_rate_multiplier = 2.0`
  - `n_epochs = 3`

Prepared split artifacts:

- `analysis/llm/finetune/reviews_v1_7_train_ids_100.txt`
- `analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt`
- `analysis/llm/finetune/reviews_v1_7_holdout_reference.json`

### `V1.7` Full-120 Diagnostic

- Output artifacts:
  - `reviews_v1_7_120_labeled.json`
  - `reviews_v1_7_120_compare.json`
  - `reviews_v1_7_120_plot.png`
- Result:
  - exact matches: `53`
  - matched labels: `572`
  - missing labels: `107`
  - extra labels: `68`

Interpretation:

- `V1.7` improved in-sample benchmark fit on the full 120-review set.
- It slightly reduced total predicted labels relative to benchmark volume, but still stayed close enough to produce the best exact-match count observed on the full set.

### `V1.7` Holdout20 Generalization

- Evaluation split:
  - train100 / holdout20
- Holdout reference:
  - `analysis/llm/finetune/reviews_v1_7_holdout_reference.json`
- Result on the 20 reviews not included in training:
  - exact matches: `1`
  - matched labels: `77`
  - missing labels: `33`
  - extra labels: `25`

Interpretation:

- `V1.7` degraded sharply on unseen reviews.
- The fine-tuned model appears overfit to the training 100:
  - train100: `52/100` exact matches, `74` missing, `43` extra
  - holdout20: `1/20` exact matches, `33` missing, `25` extra
- Therefore `V1.7` is not the current best general-purpose model despite its strong 120-set score.

### `V1.7` Latency Note

- Fine-tuning did not make the existing long `V1` prompt faster by itself.
- The 120-review `V1.7` run took:
  - total wall-clock: `1387.00s`
  - average request time: `11.55s/review`
  - throughput: `~5.2 reviews/min`
- The longest outliers appear to be driven by a mix of:
  - long review text
  - and backend/service-side variance

## Post-`V1.7` Model Sweep

The next benchmark phase shifts from prompt-tuning and fine-tuning to a clean base-model sweep focused on generalization.

Primary benchmark:

- `analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt`
- reference:
  - `analysis/llm/finetune/reviews_v1_7_holdout_reference.json`

Secondary benchmark:

- full 120-review diagnostic pass only for shortlisted winners

Implemented sweep runners:

- OpenAI:
  - `scripts/analyze_llm_flat_v1_sweep_openai.py`
- Gemini:
  - `scripts/analyze_llm_flat_v1_sweep_gemini.py`

Key sweep design:

- same `V1` prompt
- same metadata block
- same flat label schema
- same compare and plot scripts
- per-review request durations are stored for latency inspection

Stage A candidates:

- `gpt-5.4-mini`
- `gpt-5.1` with `reasoning_effort=low`
- `gemini-2.5-flash`
- `gemini-2.5-pro`

Promotion rule:

- only promote a model to a 120-review diagnostic run if it is near or better than `V1` on holdout20
- and if its extra-label count stays meaningfully below the `V1.7` holdout level

Qualitative holdout reviews to inspect in every sweep:

- `bundeswehrkrankenhaus:223`
- `euregio-klinik-albert-schweitzer-strasse-gmbh:191`
- `herzogin-elisabeth-hospital:259`
- `asklepios-fachklinikum-goettingen:77`
- `sana-klinikum-hameln-pyrmont:139`

## Holdout20 Results Across Model Sweep

The current generalization benchmark is the 20-review holdout that was not used in `V1.7` fine-tuning.

Reference comparisons:

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

Stage A model sweep results:

### `gpt-5.4-mini`

- exact matches: `2`
- matched labels: `72`
- missing labels: `38`
- extra labels: `43`
- average request time: `1.45s`

Pattern:

- very fast
- weak holdout alignment
- substantial recall loss
- also adds many extra labels

### `gpt-5.1` with `reasoning_effort=low`

- exact matches: `1`
- matched labels: `89`
- missing labels: `21`
- extra labels: `65`
- average request time: `2.05s`

Pattern:

- strongest matched-label count among the new base models
- but clearly the strongest overlabeling
- behaves as a high-recall, low-precision model on this task

### `gemini-2.5-flash`

- exact matches: `1`
- matched labels: `78`
- missing labels: `32`
- extra labels: `42`
- average request time: `5.80s`

Pattern:

- more conservative than `gpt-5.1`
- still clearly behind `V1`
- remains unstable on mixed reviews

### `gemini-2.5-pro`

- exact matches: `1`
- matched labels: `72`
- missing labels: `38`
- extra labels: `38`
- average request time: `11.55s`

Pattern:

- more controlled than `gpt-5.1` and slightly cleaner than `gemini-2.5-flash` on extra labels
- but no meaningful improvement in exact matches or recall
- currently not competitive with `V1` on holdout generalization

## `V1.8` Paraphrase-Augmented Fine-Tuning

`V1.8` tests whether fully automated paraphrase augmentation improves generalization over `V1.7`.

Setup:

- source split:
  - original `V1.7` train100 / holdout20
- augmentation strategy:
  - 40 selected hard training reviews
  - 2 accepted paraphrases per source review
  - 80 synthetic paraphrases total
- resulting training set:
  - 100 original reviewed train examples
  - 80 synthetic paraphrase examples
  - 180 total training examples
- generator model:
  - `gpt-5.1` with `reasoning_effort=low`
- judge model:
  - `gpt-5.1` with `reasoning_effort=low`
- fine-tuning base model:
  - `gpt-4.1-mini-2025-04-14`

Prepared artifacts:

- `analysis/llm/augmentation/reviews_v1_8_source_ids_40.txt`
- `analysis/llm/augmentation/reviews_v1_8_augmented_80.json`
- `analysis/llm/augmentation/reviews_v1_8_judgments.json`
- `analysis/llm/augmentation/reviews_v1_8_manifest.json`
- `analysis/llm/finetune/reviews_v1_8_train_180.jsonl`
- `analysis/llm/finetune/reviews_v1_8_valid_20.jsonl`
- `analysis/llm/finetune/reviews_v1_8_dataset_manifest.json`

Fine-tuning job result:

- fine-tuning job id:
  - `ftjob-bfXlxBKddowoqAt4QyRmcWft`
- fine-tuned model:
  - `ft:gpt-4.1-mini-2025-04-14:personal::DfmG9LLl`
- status:
  - `succeeded`
- trained tokens:
  - `460,161`
- OpenAI-selected hyperparameters:
  - `batch_size = 1`
  - `learning_rate_multiplier = 2.0`
  - `n_epochs = 3`

### `V1.8` Holdout20 Result

- Output artifacts:
  - `reviews_v1_8_holdout20_labeled.json`
  - `reviews_v1_8_holdout20_compare.json`
  - `reviews_v1_8_holdout20_plot.png`
- Result:
  - exact matches: `3`
  - matched labels: `76`
  - missing labels: `34`
  - extra labels: `23`
- Bucket breakdown:
  - positive: exact `1`, matched `16`, missing `5`, extra `4`
  - negative: exact `1`, matched `26`, missing `9`, extra `6`
  - mixed_hard: exact `1`, matched `34`, missing `20`, extra `13`

Comparison to earlier holdout baselines:

- `V1`:
  - exact `8`, matched `92`, missing `18`, extra `5`
- `V1.7`:
  - exact `1`, matched `77`, missing `33`, extra `25`
- `V1.8`:
  - exact `3`, matched `76`, missing `34`, extra `23`

Interpretation:

- `V1.8` is a small improvement over `V1.7`, especially in:
  - exact matches: `1 -> 3`
  - extra labels: `25 -> 23`
- however, it does not recover the original `V1` quality:
  - matched labels remain well below `V1`
  - missing labels remain much higher than `V1`
- the paraphrase augmentation therefore helped a little, but not enough to solve the generalization problem

### `V1.8` Qualitative Holdout Findings

Important examples:

- `bundeswehrkrankenhaus:223`
  - `V1.7` lost the positive `care.treatment` label
  - `V1.8` recovers the benchmark-correct label set
- `asklepios-fachklinikum-goettingen:77`
  - `V1.7` drifted into `environment.support`
  - `V1.8` returns to the correct `staff.friendliness` + `staff.empathy` strengths
- `euregio-klinik-albert-schweitzer-strasse-gmbh:191`
  - `V1.8` still misses `staff.empathy`
- `herzogin-elisabeth-hospital:259`
  - `V1.8` still adds extra `care.competence`
- `sana-klinikum-hameln-pyrmont:139`
  - `V1.8` remains drift-prone and adds extra nearby labels such as:
    - `access.navigation`
    - `communication.communication`
    - `staff.respect`

### `V1.8` Augmentation QA Observation

The most important methodological observation from the augmentation pipeline is:

- all `80` accepted synthetic paraphrases passed the semantic judge
- there were no rejected candidates
- no reserve source reviews were needed

Interpretation:

- the semantic judge appears too permissive
- `V1.8` should therefore be interpreted as:
  - a useful first augmentation test
  - but not yet a strict quality-controlled augmentation pipeline
- the small gain over `V1.7` suggests paraphrase augmentation is not useless
- but the current judge did not filter hard enough to produce a strong generalization gain

## `V1.9` JSON-Schema Control Run

`V1.9` isolates the most plausible new technical factor from the weak batch path:

- explicit `response_format = json_schema`

Setup:

- original `V1` prompt
- full metadata retained
- snapshot model:
  - `gpt-4.1-mini-2025-04-14`
- `temperature=0`
- synchronous execution
- explicit JSON-schema structured output
- local parsing into `FlatExtraction`

Output artifacts:

- `reviews_v1_9_120_labeled.json`
- `reviews_v1_9_120_compare.json`
- `reviews_v1_9_120_plot.png`

Result:

- exact matches: `19`
- matched labels: `497`
- missing labels: `182`
- extra labels: `174`

Bucket breakdown:

- positive: exact `10`, matched `117`, missing `20`, extra `40`
- negative: exact `7`, matched `124`, missing `50`, extra `41`
- mixed_hard: exact `2`, matched `256`, missing `112`, extra `93`

Interpretation:

- `V1.9` is clearly worse than `V1.5`
- matched labels remain almost unchanged relative to `V1.5`
- the main regression comes from a large increase in extra labels:
  - `V1.5`: `120`
  - `V1.9`: `174`
- this strongly suggests that explicit structured output via `json_schema` is already a substantial regression factor

## `V1.10` Batch-vs-Sync Control Run

`V1.10` isolates the additional effect of the Batch API while keeping the `V1.9` setup otherwise fixed.

Setup:

- original `V1` prompt
- full metadata retained
- snapshot model:
  - `gpt-4.1-mini-2025-04-14`
- `temperature=0`
- explicit JSON-schema structured output
- **Batch API**
- exactly the reviewed 120 benchmark reviews

Output artifacts:

- `reviews_v1_10_120_labeled.json`
- `reviews_v1_10_120_compare.json`
- `reviews_v1_10_120_plot.png`

Result:

- exact matches: `18`
- matched labels: `494`
- missing labels: `185`
- extra labels: `167`

Bucket breakdown:

- positive: exact `8`, matched `113`, missing `24`, extra `47`
- negative: exact `8`, matched `125`, missing `49`, extra `45`
- mixed_hard: exact `2`, matched `256`, missing `112`, extra `75`

Interpretation:

- `V1.10` is very close to `V1.9`
- the difference between synchronous `json_schema` and batch `json_schema` is comparatively small
- this means the main regression is **not primarily caused by the Batch API**
- the dominant quality loss already appears in the explicit structured-output / `json_schema` path

## Overlap48 Readout

The first 10,000-review batch run contains `48` reviews from the reviewed 120 benchmark.

Overlap48 comparison:

- `V1`:
  - exact `21`
  - matched `228`
  - missing `41`
  - extra `8`
- batch10k path:
  - exact `8`
  - matched `196`
  - missing `73`
  - extra `70`
- `V1.9`:
  - exact `10`
  - matched `195`
  - missing `74`
  - extra `61`

Interpretation:

- the 10k batch path is weak
- but `V1.9` on the same overlap is already similarly weak
- therefore the large quality drop in the batch path is largely consistent with the `json_schema` effect itself
- Batch API may still contribute a small additional degradation, but it is not the dominant factor

## Cross-Run Learnings

### 1. `V1` remains the best generalization baseline

The central result is now stable:

- the original `V1` run is still the strongest known general-purpose configuration
- later prompt variants did not beat it
- the fine-tuned model did not beat it on unseen reviews
- stronger and more expensive base models also did not beat it on unseen reviews

### 2. Metadata helps in the current extraction setup

The metadata ablation line was consistent:

- removing metadata hurt performance
- reducing metadata also hurt performance
- the original full-metadata setup remains the strongest prompt configuration

This suggests that the current task benefits from contextual grounding in metadata, even if the exact mechanism is not yet isolated further.

### 3. More prompt control did not translate into better calibration

The prompt interventions all failed in different ways:

- stricter rules reduced recall
- targeted clarifications oversteered the model
- in-sample few-shot examples did not improve the benchmark result

The main lesson is that more instruction text did not solve the labeling problem.

### 4. Fine-tuning improved in-sample fit but overfit on unseen reviews

`V1.7` is the clearest signal here:

- full 120-review score improved
- holdout20 score deteriorated sharply

This means the fine-tuned model learned the benchmark training set more closely, but not the underlying task robustly enough.

### 5. Better models are not enough on their own

The new base-model sweep suggests that the bottleneck is not just raw model capability:

- `gpt-5.4-mini` was fast but underperformed badly
- `gpt-5.1 low` had high recall but severe overlabeling
- both Gemini models remained behind `V1`

The failure pattern is therefore better described as a **task-calibration and data problem** than a model-quality problem.

### 6. The dominant error mode is semantic drift plus overlabeling

Across the newer models, the recurring issues were:

- extra care-related labels such as:
  - `care.competence`
  - `care.treatment`
  - `care.symptoms`
- extra staff or support labels such as:
  - `staff.respect`
  - `environment.support`
- substitutions of nearby labels instead of exact matches
- degraded performance especially on `mixed_hard` reviews

This means many models are semantically close, but not label-calibrated enough for the benchmark.

### 7. Synthetic paraphrase augmentation shows a weak positive signal, not a breakthrough

`V1.8` adds an important nuance to the fine-tuning story:

- synthetic paraphrase augmentation improved on `V1.7`
- but only slightly
- and it still remained clearly behind `V1`

The main lesson is:

- augmentation may help with wording-specific overfitting
- but only if the synthetic data quality control is much stricter than in the first `V1.8` pipeline

### 8. Explicit Structured Outputs are a major regression factor

The `V1.9` / `V1.10` control runs add a new technical conclusion:

- the original synchronous `instructor` path is not the new variable, because the earlier `V1` family already used it
- the major new factor is explicit:
  - `response_format = json_schema`
- this path causes a large jump in extra labels relative to `V1.5`

The practical implication is:

- the current structured-output batch path should not be treated as quality-equivalent to old `V1`

### 9. Batch API itself is not the main problem

`V1.10` is only slightly worse than `V1.9`:

- `V1.9`: exact `19`, matched `497`, missing `182`, extra `174`
- `V1.10`: exact `18`, matched `494`, missing `185`, extra `167`

This suggests:

- the Batch API adds at most a smaller secondary effect
- the dominant quality drop already exists before batch execution, once the run uses explicit `json_schema`

## Full-Run Descriptive Analysis (`30,863` Reviews)

The large-scale batch path was then carried through to full corpus coverage:

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

## Current Decision

Based on the current evidence:

- do **not** continue the expensive base-model sweep as the primary path
- do **not** treat `V1.7` as the new default model
- do **not** treat `V1.8` as a successful replacement for `V1`
- do **not** treat the current `json_schema`-based batch path as operationally equivalent to `V1`
- keep `V1` as the current best operational baseline
- treat the completed full-run as a **descriptive coverage layer**, not as a new best-model result
- shift the next improvement cycle toward **better training data selection and dataset curation**
- if augmentation is revisited, harden the acceptance logic rather than simply generating more paraphrases
- if large-scale productive prelabeling is needed again, prefer an explicitly documented tradeoff rather than assuming quality parity with `V1`

Recommended next direction:

- first analyze the now-complete `30,863`-review corpus descriptively
- use the full-run outputs for thematic overview, frequency analysis, and global pattern reporting
- for future model improvement, return to active-learning-style curation of reviewed examples
- prioritize disagreement cases, mixed reviews, and the recurring error labels
- then re-run fine-tuning with a stronger data strategy instead of more prompt tinkering
