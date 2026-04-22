# human-ls

## Google review example

The script at [scripts/fetch_mhh_google_reviews.py](/Users/finnborchers/Desktop/HUMAN-LS/human-ls/scripts/fetch_mhh_google_reviews.py) fetches the available public Google Places review data for Hannover Medical School (`Medizinische Hochschule Hannover`) via the official Places API.

Run it with:

```bash
export GOOGLE_MAPS_API_KEY="your-key"
python3 scripts/fetch_mhh_google_reviews.py --output mhh_reviews.json
```

Important limitation: Google Places returns only `up to five reviews` for a place through the API, so this is useful as a compliant prototype but not as a full-corpus collection method.

## Granular LLM review analysis

The script at [scripts/analyze_reviews_llm.py](/Users/finnborchers/Desktop/HUMAN-LS/human-ls/scripts/analyze_reviews_llm.py) runs the granular all-LLM taxonomy pass over the captured `artifacts/*/reviews.json` corpus, uses explicit nested Pydantic models defined in the script, and writes the extracted labels to [review_label_results_v1.json](/Users/finnborchers/Desktop/HUMAN-LS/human-ls/analysis/review_label_results_v1.json).

It uses:

- the official OpenAI Python library
- `instructor` for structured extraction
- `pydantic` for the nested runtime response models
- `python-dotenv` so `OPENAI_API_KEY` can be loaded from a local `.env`

Install the Python dependencies first:

```bash
python3 -m pip install -r requirements.txt
```

The script is intentionally simple and constant-driven. Change the top-level values in [scripts/analyze_reviews_llm.py](/Users/finnborchers/Desktop/HUMAN-LS/human-ls/scripts/analyze_reviews_llm.py) if you want a different model, output path, start index, or review count.

Run it with:

```bash
python3 scripts/analyze_reviews_llm.py
```

By default it:

- loads `OPENAI_API_KEY` from `.env`
- reads `artifacts/*/reviews.json`
- uses explicit static Pydantic model definitions in `scripts/analyze_reviews_llm.py`
- processes the slice defined by `START_INDEX` and `NUM_REVIEWS`
- skips already processed `review_id`s if they are already present in the output JSON
- writes nested model results to `analysis/review_label_results_v1.json`
