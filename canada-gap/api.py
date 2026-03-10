"""
UN Comtrade API wrapper with local caching and retry logic.

When the live API is unreachable (e.g. restricted network environment),
pass use_demo=True to use realistic synthetic data from demo_data.py.
"""

import json
import os
import time
import hashlib
import requests

from config import API_KEY, BASE_URL, DATA_DIR


def _cache_path(params: dict) -> str:
    """Generate a deterministic cache file path based on request params."""
    key = json.dumps(params, sort_keys=True)
    digest = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(DATA_DIR, f"{digest}.json")


def fetch_comtrade(
    reporter_code: str,
    partner_code: str,
    period: int,
    cmd_code: str,
    max_records: int = 100000,
    max_retries: int = 3,
) -> list[dict]:
    """
    Fetch data from UN Comtrade API with local cache and retry on 429.

    Returns a list of record dicts.
    """
    params = {
        "reporterCode": reporter_code,
        "partnerCode": partner_code,
        "period": str(period),
        "flowCode": "M",
        "cmdCode": cmd_code,
        "maxRecords": max_records,
        "format": "JSON",
        "includeDesc": "true",
    }

    cache_file = _cache_path(params)

    # Return from cache if available
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached = json.load(f)
        print(f"  [cache] {period} partner={partner_code} cmd={cmd_code} — {len(cached)} records")
        return cached

    headers = {"Ocp-Apim-Subscription-Key": API_KEY}

    for attempt in range(1, max_retries + 1):
        try:
            print(f"  [api]   {period} partner={partner_code} cmd={cmd_code} — attempt {attempt}")
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=60)

            if resp.status_code == 429:
                wait = 60 * attempt
                print(f"  [rate-limit] 429 received, waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            payload = resp.json()
            records = payload.get("data") or []

            # Persist to cache
            with open(cache_file, "w") as f:
                json.dump(records, f)

            print(f"  [api]   → {len(records)} records received")
            return records

        except requests.RequestException as exc:
            print(f"  [error] Request failed: {exc}")
            if attempt < max_retries:
                time.sleep(5 * attempt)
            else:
                raise

    return []


def fetch_hs2_all_years(partner_code: str, years: list[int], use_demo: bool = False) -> list[dict]:
    """Fetch HS2-level (AG2) data for all specified years."""
    if use_demo:
        from demo_data import get_hs2_records
        print(f"  [demo] Generating synthetic HS2 records for partner={partner_code}, years={years}")
        return get_hs2_records(partner_code, years)

    all_records = []
    for year in years:
        records = fetch_comtrade(
            reporter_code="124",
            partner_code=partner_code,
            period=year,
            cmd_code="AG2",
        )
        all_records.extend(records)
    return all_records


def fetch_hs6_chapter(partner_code: str, chapter: str, years: list[int], use_demo: bool = False) -> list[dict]:
    """Fetch HS6-level data for a specific chapter and all specified years.

    Uses cmdCode=AG6 (all HS6 subheadings) and filters to the target chapter
    prefix. This is necessary because cmdCode=<2-digit-chapter> returns only
    the HS2 aggregate record, not the HS6 breakdown.

    The full AG6 response is cached per (partner, year), so subsequent chapter
    queries for the same year hit the local cache and filter in memory.
    """
    if use_demo:
        from demo_data import get_hs6_records
        print(f"  [demo] Generating synthetic HS6 records for chapter={chapter}, partner={partner_code}, years={years}")
        return get_hs6_records(partner_code, chapter, years)

    chapter_prefix = str(chapter).zfill(2)
    all_records = []
    for year in years:
        records = fetch_comtrade(
            reporter_code="124",
            partner_code=partner_code,
            period=year,
            cmd_code="AG6",
        )
        # Filter to the target chapter (cmdCode starts with the 2-digit prefix)
        chapter_records = [r for r in records if str(r.get("cmdCode", "")).startswith(chapter_prefix)]
        print(f"  [filter] chapter={chapter_prefix} year={year} → {len(chapter_records)} HS6 records (from {len(records)} AG6 total)")
        all_records.extend(chapter_records)
    return all_records
