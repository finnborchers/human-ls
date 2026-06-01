# Full-Run Metadata Analysis

## Methodological note

- This analysis remains descriptive and corpus-level.
- The results refer to the labeled full-run corpus and should be interpreted as **associations within a coverage analysis with known model tradeoffs**.
- No causal interpretation is appropriate for owner responses, likes, or star-rating effects.

## Main observations

- `1★` reviews are strongly problem-dominated:
  - average problem labels: `3.18`
  - average strength labels: `0.27`
  - problem-only share: `80.09%`
- `5★` reviews are strongly strength-dominated:
  - average problem labels: `0.21`
  - average strength labels: `3.42`
  - strength-only share: `80.01%`
- `3★` reviews show the strongest mixed pattern:
  - mixed share: `66.58%`

- Reviews with `0` likes have an average star rating of `3.86`.
- Reviews with `25+` likes have an average star rating of `1.39`.
- Across the like buckets, higher visibility is descriptively linked to lower star ratings and higher problem-label density.

- Reviews with owner responses show:
  - average strength labels: `2.35`
  - no-label share: `1.82%`
- Reviews without owner responses show:
  - average likes: `3.13`

## Interpretation boundary

- Star ratings behave as a strong polarity signal in the labeled corpus.
- Likes appear to correlate with more conflict-heavy and problem-oriented reviews.
- Owner response should be treated as a selection signal, not an intervention effect.
