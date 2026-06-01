# Full-Run Descriptive Analysis

## Run summary

- Total reviews analyzed: `30,863`
- Fully materialized reviews: `30,863`
- Parse errors in full run: `0`
- Reviews without any labels: `1,005` (`3.26%`)

## Methodological note

- `V1` remained the strongest benchmark baseline in the controlled tests.
- The full 30,863-review run was still executed on the batch path to obtain complete corpus coverage.
- The resulting descriptive analysis should therefore be read as a **coverage analysis with a known quality tradeoff**, not as a new gold-standard label set.

## Main observations

- Reviews with only problem labels: `9,528` (`30.87%`)
- Reviews with only strength labels: `13,347` (`43.25%`)
- Reviews with both problem and strength labels: `6,983` (`22.63%`)
- Mean labels per review: `3.59`
- Median labels per review: `3`

- Dominant problem themes: care.treatment (5013), access.waiting (4420), staff.friendliness (4088), staff.respect (3966), staff.seriousness (3020)
- Dominant strength themes: staff.friendliness (15723), staff.empathy (9742), care.treatment (9014), care.competence (7411), staff.respect (3692)
- Most common problem-problem combinations: staff.friendliness + staff.respect (1678), care.treatment + staff.respect (1402), care.competence + care.treatment (1359)
- Most common problem-strength combinations: staff.friendliness + staff.friendliness (1101), access.waiting + staff.friendliness (1088), care.treatment + staff.friendliness (929)

## Interpretation boundary

- This first pass is intentionally global and descriptive.
- It supports high-level thematic interpretation of the corpus.
- It should not yet be used as a clinic-ranking or causal comparison layer without additional filtering and methodological safeguards.
