# human-ls

## Google review example

The script at [scripts/fetch_mhh_google_reviews.py](/Users/finnborchers/Desktop/HUMAN-LS/human-ls/scripts/fetch_mhh_google_reviews.py) fetches the available public Google Places review data for Hannover Medical School (`Medizinische Hochschule Hannover`) via the official Places API.

Run it with:

```bash
export GOOGLE_MAPS_API_KEY="your-key"
python3 scripts/fetch_mhh_google_reviews.py --output mhh_reviews.json
```

Important limitation: Google Places returns only `up to five reviews` for a place through the API, so this is useful as a compliant prototype but not as a full-corpus collection method.
