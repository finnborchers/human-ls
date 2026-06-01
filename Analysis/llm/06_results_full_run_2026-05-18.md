# Full-Run Results - 2026-05-18

This document summarizes the substantive results of the full HumanLS batch run over the complete Google review corpus after the benchmarking and model-selection phase had been completed.

The purpose of this file is not to revisit model selection. Instead, it documents what can be learned from the now fully labeled corpus under the methodological constraint already established in the benchmark notes:

- `V1` remained the strongest benchmark baseline
- the full run was still executed on the batch path for complete corpus coverage
- the resulting labels should therefore be interpreted as a **descriptive coverage layer with known quality tradeoffs**

## Data Basis and Processing Context

### Corpus and processing scope

The final full-run corpus contains:

- `30,863` reviews in total
- `10,000` reviews in the first scope:
  - `10000_ids`
- `20,863` reviews in the second scope:
  - `20863_ids`
- `0` parse errors after full materialization

Batch processing was intentionally split into sequential sub-batches rather than executed as one giant request.

Reason:

- parallel large-batch submission triggered:
  - `token_limit_exceeded`
- the binding operational limit was the OpenAI Batch queue for **enqueued tokens**
- not the nominal credit balance itself

The resulting strategy was:

- one batch input file at a time
- one batch job at a time
- polling every `300` seconds
- fetch/materialize before submitting the next batch

This produced a complete full run while staying under the observed queue limit.

### Runtime and cost

Observed batch-processing duration:

- `10000_ids`:
  - `44m 23s`
- `20863_ids`:
  - `3h 09m 42s`
- combined API-side batch time:
  - `3h 54m 05s`

Observed or reconstructed token volume:

- `10000_ids`:
  - `8,827,228` total tokens
- `20863_ids`:
  - `18,403,552` total tokens
- combined:
  - `27,230,780` total tokens

Observed cost:

- `20863_ids`:
  - `3.98 USD`
- `10000_ids`:
  - approximately `1.93 USD`
- approximate total full-run cost:
  - `5.91 USD`

Methodological implication:

- the batch path was operationally efficient enough for full-corpus processing
- but the benchmark analyses already showed that this efficiency came with measurable quality loss relative to the original synchronous `V1` baseline

## Global Corpus Structure

### Review-level label composition

The full run yields the following high-level composition:

- no labels:
  - `1,005` reviews
  - `3.26%`
- only problem labels:
  - `9,528` reviews
  - `30.87%`
- only strength labels:
  - `13,347` reviews
  - `43.25%`
- both problem and strength labels:
  - `6,983` reviews
  - `22.63%`

The overall label density is moderate:

- mean labels per review:
  - `3.59`
- median labels per review:
  - `3`
- maximum labels on one review:
  - `34`

Interpretation:

- the corpus is not dominated by a single review type
- a large share is clearly positive-only or negative-only
- but the mixed segment is still substantial enough to matter analytically

Relevant figure references:

- label density distribution:
  - [labels_per_review_histogram.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/descriptive_analysis/plots/labels_per_review_histogram.png)
- problem vs strength volume:
  - [problem_vs_strength_volume.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/descriptive_analysis/plots/problem_vs_strength_volume.png)

### Dominant thematic structure

The most frequent problem labels in the full corpus are:

1. `care.treatment` (`5,013`)
2. `access.waiting` (`4,420`)
3. `staff.friendliness` (`4,088`)
4. `staff.respect` (`3,966`)
5. `staff.seriousness` (`3,020`)

The most frequent strength labels are:

1. `staff.friendliness` (`15,723`)
2. `staff.empathy` (`9,742`)
3. `care.treatment` (`9,014`)
4. `care.competence` (`7,411`)
5. `staff.respect` (`3,692`)

Interpretation:

- staff-related and care-related themes dominate both sides of the corpus
- positive descriptions are especially concentrated around:
  - friendliness
  - empathy
  - treatment
  - competence
- negative descriptions are especially concentrated around:
  - treatment
  - waiting
  - interpersonal conduct

This is already informative for HumanLS:

- patient experience in this corpus is not primarily structured by rare niche topics
- it is structured by recurrent interactional and care-process signals

Relevant figure references:

- top problem labels:
  - [top_problem_labels.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/descriptive_analysis/plots/top_problem_labels.png)
- top strength labels:
  - [top_strength_labels.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/descriptive_analysis/plots/top_strength_labels.png)

### Frequent co-occurrence patterns

The most common problem-problem combinations are:

1. `staff.friendliness` + `staff.respect` (`1,678`)
2. `care.treatment` + `staff.respect` (`1,402`)
3. `care.competence` + `care.treatment` (`1,359`)

The most common problem-strength combinations are:

1. `staff.friendliness` + `staff.friendliness` (`1,101`)
2. `access.waiting` + `staff.friendliness` (`1,088`)
3. `care.treatment` + `staff.friendliness` (`929`)

Interpretation:

- criticism and praise often coexist around the same interactional domain
- reviews do not simply separate into “care” versus “staff”
- instead, the same experiential axes can appear positively and negatively within the same corpus and often within the same review

This is particularly relevant for HumanLS because it supports an interface or analysis logic that treats reviews as **multi-aspect signals**, not as binary sentiment containers.

Relevant figure reference:

- problem co-occurrence heatmap:
  - [problem_label_cooccurrence_heatmap.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/descriptive_analysis/plots/problem_label_cooccurrence_heatmap.png)

## Metadata-Linked Patterns

### Star ratings as polarity structure

The strongest and cleanest metadata signal is the star rating.

For `1★` reviews:

- average problem labels:
  - `3.18`
- average strength labels:
  - `0.27`
- problem-only share:
  - `80.09%`

For `5★` reviews:

- average problem labels:
  - `0.21`
- average strength labels:
  - `3.42`
- strength-only share:
  - `80.01%`

For `3★` reviews:

- mixed-review share:
  - `66.58%`
- highest mixed proportion among all star buckets

Interpretation:

- the star scale maps very strongly onto the label polarity structure
- `1★` and `5★` behave as near-pure extremes
- `3★` reviews appear to be the most analytically valuable ambivalence cases

This is a strong argument for using `3★` reviews as a high-yield subset in future HumanLS curation or qualitative inspection workflows.

Relevant figure references:

- star distribution:
  - [star_distribution.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/metadata_analysis/plots/star_distribution.png)
- review composition by star:
  - [review_mix_by_star.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/metadata_analysis/plots/review_mix_by_star.png)
- average labels by star:
  - [avg_labels_by_star.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/metadata_analysis/plots/avg_labels_by_star.png)

### Likes as salience signal

The like-count signal is also analytically useful.

At the low end:

- reviews with `0` likes have an average star rating of:
  - `3.86`
- and an average problem-label density of:
  - `1.03`

At the high end:

- reviews with `25+` likes have an average star rating of:
  - `1.39`
- and an average problem-label density of:
  - `4.51`

The intermediate buckets follow the same directional trend:

- more likes are associated with lower average star ratings
- more likes are associated with higher problem-label density
- more likes are also associated with a reduced share of pure strength-only reviews

Interpretation:

- highly liked reviews appear to function as a salience marker for conflict-heavy, experience-relevant criticism
- this does **not** mean that likes measure objective truth or objective relevance
- but within this corpus they clearly behave as a useful prioritization signal for prominent negative experience narratives

For HumanLS, this suggests a practical downstream use:

- likes can serve as a triage signal when prioritizing reviews for qualitative follow-up or UI prominence

Relevant figure reference:

- like-bucket salience:
  - [like_bucket_salience.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/metadata_analysis/plots/like_bucket_salience.png)

### Owner responses as descriptive grouping, not causal mechanism

Owner-response status also shows visible differences, but it must be interpreted much more cautiously.

Reviews with owner responses:

- average strength labels:
  - `2.35`
- no-label share:
  - `1.82%`
- total share of corpus:
  - `29.63%`

Reviews without owner responses:

- average strength labels:
  - `1.99`
- no-label share:
  - `3.86%`
- average likes:
  - `3.13`

Interpretation:

- owner response is descriptively associated with a somewhat different review profile
- but the direction of explanation is open
- for example, reviewed institutions may selectively respond to particular kinds of reviews, or response behavior may correlate with other institutional traits

Therefore:

- this variable should be treated as a **selection signal**
- not as evidence that owner responses improve or worsen review content

Relevant figure reference:

- owner response profile:
  - [owner_response_profile.png](/Users/finnborchers/human-ls/human-ls/analysis/llm/full_run/metadata_analysis/plots/owner_response_profile.png)

## Limits and Interpretation Boundaries

Several constraints remain important.

### Model-path constraint

The benchmark work showed clearly that:

- the original `V1` setup remained the strongest quality baseline
- the batch path was chosen for complete coverage, not because it outperformed `V1`

Therefore the full-run outputs should be read as:

- broad, structured, corpus-level evidence
- but not as benchmark-equivalent gold labels

### Metadata constraint

Not all metadata dimensions are equally usable:

- `star_rating`:
  - strong and interpretable
- `like_count`:
  - strong enough for descriptive salience analysis
- `has_owner_response`:
  - usable with caution
- `review_time`:
  - only available as relative free-text strings such as:
    - `vor einem Jahr`
    - `vor 3 Monaten`
  - therefore only suitable for coarse bucketization
- `clinic_name`:
  - effectively unavailable in the merged corpus metadata

There is also a small missing-star bucket:

- `56` reviews have `star_rating = None`
- these are retained as an `Unknown` category in the metadata analysis
- they were not dropped, to preserve total-count consistency

### Substantive caution

These findings are strong enough for:

- descriptive thematic mapping
- corpus characterization
- prioritization logic for future HumanLS exploration

They are **not** yet strong enough for:

- clinic ranking
- causal claims
- institutional performance inference

## Implications for HumanLS

Taken together, the full-run results support a few concrete conclusions for the HumanLS project.

1. The corpus contains a stable, repetitive experiential structure centered on:
   - care quality
   - waiting/access
   - staff interaction

2. Mixed reviews are not marginal noise.
   - especially `3★` reviews encode ambivalence that is analytically valuable

3. Likes appear to be a promising prioritization feature.
   - highly liked reviews are much more problem-dense and much more negative on average

4. The current pipeline is already good enough to support:
   - descriptive overview
   - hypothesis generation
   - structured qualitative follow-up

5. The project should still keep the distinction clear between:
   - a coverage-oriented labeling layer
   - and a quality-optimized benchmark path

That distinction is methodologically important and, at this point, one of the central lessons of the whole experiment sequence.
