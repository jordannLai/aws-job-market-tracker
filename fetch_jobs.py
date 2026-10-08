"""
Fetch job postings from the Adzuna API and save the raw results as JSON.

Phase 1 of the AWS Job Market Tracker. Runs locally today; later the
fetch logic moves into an AWS Lambda function and the save step writes
to S3 instead of the local data/ folder.

Usage:
    python fetch_jobs.py
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

# --- Settings -------------------------------------------------------------

# Job titles to track. Each one costs PAGES_PER_QUERY API calls per run.
SEARCH_TERMS = [
    "cloud engineer",
    "data engineer",
    "software engineer",
]

COUNTRY = "us"            # Adzuna country code
RESULTS_PER_PAGE = 50     # Adzuna's maximum per call
PAGES_PER_QUERY = 2       # 3 terms x 2 pages = 6 calls per run
MAX_DAYS_OLD = 7          # only postings from the last N days

BASE_URL = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search"
DATA_DIR = Path("data/raw")


# --- Core logic -----------------------------------------------------------

def get_credentials():
    """Load Adzuna keys from the .env file and stop with a clear message if missing."""
    load_dotenv()
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key or "your_" in app_id or "your_" in app_key:
        sys.exit("Missing Adzuna keys. Add ADZUNA_APP_ID and ADZUNA_APP_KEY to your .env file.")
    return app_id, app_key


def fetch_page(app_id, app_key, search_term, page):
    """Call the Adzuna search endpoint for one page of results."""
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": search_term,
        "results_per_page": RESULTS_PER_PAGE,
        "max_days_old": MAX_DAYS_OLD,
        "content-type": "application/json",
    }
    response = requests.get(f"{BASE_URL}/{page}", params=params, timeout=30)

    if response.status_code == 401:
        sys.exit("Adzuna rejected your keys (401). Double-check the values in .env.")
    response.raise_for_status()
    return response.json()


def fetch_term(app_id, app_key, search_term):
    """Fetch all configured pages for one search term and combine the results."""
    all_results = []
    total_available = 0

    for page in range(1, PAGES_PER_QUERY + 1):
        data = fetch_page(app_id, app_key, search_term, page)
        results = data.get("results", [])
        total_available = data.get("count", total_available)
        all_results.extend(results)

        if len(results) < RESULTS_PER_PAGE:
            break  # no more pages
        time.sleep(1)  # be polite to the API

    return {
        "search_term": search_term,
        "fetched_on": date.today().isoformat(),
        "total_available": total_available,
        "results": all_results,
    }


def save_raw(payload):
    """Save results to data/raw/YYYY-MM-DD/<search_term>.json (S3 later)."""
    folder = DATA_DIR / payload["fetched_on"]
    folder.mkdir(parents=True, exist_ok=True)
    filename = payload["search_term"].replace(" ", "_") + ".json"
    path = folder / filename
    path.write_text(json.dumps(payload, indent=2))
    return path


def main():
    app_id, app_key = get_credentials()

    for term in SEARCH_TERMS:
        print(f"Fetching '{term}'...")
        payload = fetch_term(app_id, app_key, term)
        path = save_raw(payload)
        print(
            f"  saved {len(payload['results'])} postings "
            f"(of {payload['total_available']:,} available) -> {path}"
        )

    print("Done.")


if __name__ == "__main__":
    main()
