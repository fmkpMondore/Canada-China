"""
Canada Import Gap Analysis — Entry Point

Usage:
  python main.py --mode holistic
  python main.py --mode holistic --years 2022 2023 2024
  python main.py --mode deepdive --chapter 95
  python main.py --mode deepdive --chapter 95 --csv
  python main.py --mode holistic --demo   # use synthetic data (no API needed)
"""

import argparse
import sys

from config import DEFAULT_YEARS, CHINA_CODE, WORLD_CODE
from api import fetch_hs2_all_years, fetch_hs6_chapter
from analysis import compute_gap, compute_gap_by_year, print_top_n
from export import export_holistic, export_deepdive, export_csv


def mode_holistic(years: list[int], use_csv: bool, use_demo: bool = False):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║        CANADA IMPORT GAP ANALYSIS — HOLISTIC MODE           ║")
    if use_demo:
        print("║                   [DEMO MODE — synthetic data]              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\nYears: {years}")
    print("\n[1/4] Fetching World imports (HS2)...")
    world_records = fetch_hs2_all_years(WORLD_CODE, years, use_demo=use_demo)

    print("\n[2/4] Fetching China imports (HS2)...")
    china_records = fetch_hs2_all_years(CHINA_CODE, years, use_demo=use_demo)

    print("\n[3/4] Computing gap & opportunity scores...")
    summary_df = compute_gap(world_records, china_records)
    yearly_df  = compute_gap_by_year(world_records, china_records)

    print(f"\nTotal HS2 chapters with data: {len(summary_df)}")

    # Print top 15
    print("\n┌─────────────────────────────────────────────────────────┐")
    print("│           TOP 15 OPPORTUNITIES FOR CHINESE EXPORTS      │")
    print("│              (Canada Market — Aggregated years)         │")
    print("└─────────────────────────────────────────────────────────┘")
    print_top_n(summary_df, n=15, highlight_chapter="95")

    # Hypothesis evaluation — Chapter 95 (Toys)
    _evaluate_hypothesis(summary_df, chapter="95")

    print("\n[4/4] Exporting results...")
    if use_csv:
        path1 = export_csv(summary_df, "canada_import_gap_holistic.csv")
        path2 = export_csv(yearly_df,  "canada_import_gap_holistic_yearly.csv")
        print(f"  Saved: {path1}")
        print(f"  Saved: {path2}")
    else:
        path = export_holistic(summary_df, yearly_df)
        print(f"  Saved: {path}")

    print("\nDone.")


def _evaluate_hypothesis(summary_df, chapter: str = "95"):
    """Print a detailed evaluation of the toys hypothesis."""
    match = summary_df[summary_df["hs_code"].astype(str).str.strip() == str(chapter)]

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║     HYPOTHESIS EVALUATION: HS 95 — TOYS & GAMES (Canada)   ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if match.empty:
        print("  ⚠  Chapter 95 not found in results. Check API data.")
        return

    row = match.iloc[0]
    rank = match.index[0]
    total_chapters = len(summary_df)

    print(f"\n  Rank:               #{rank} of {total_chapters} chapters")
    print(f"  World imports:      USD {row['world_usd']/1e6:,.1f} M")
    print(f"  China imports:      USD {row['china_usd']/1e6:,.1f} M")
    print(f"  Gap (World-China):  USD {row['gap_usd']/1e6:,.1f} M")
    print(f"  China market share: {row['china_share_pct']:.1f}%")
    print(f"  Opportunity Score:  {row['opportunity_score']/1e9:.2f} B USD")

    print("\n  Interpretation:")
    if row["china_share_pct"] < 20:
        share_verdict = "LOW — significant room to grow"
    elif row["china_share_pct"] < 40:
        share_verdict = "MODERATE — some opportunity remains"
    else:
        share_verdict = "HIGH — market already well-captured by China"

    if rank <= 10:
        rank_verdict = "STRONG — top-10 opportunity"
    elif rank <= 25:
        rank_verdict = "MODERATE — top-25 opportunity"
    else:
        rank_verdict = "WEAK — not among top opportunities"

    print(f"    • China share: {share_verdict}")
    print(f"    • Rank:        {rank_verdict}")

    if row["china_share_pct"] < 40 and rank <= 25:
        verdict = "✅ HYPOTHESIS SUPPORTED"
        explanation = (
            "HS 95 (Toys & Games) presents a meaningful gap opportunity "
            "for Chinese exporters in the Canadian market."
        )
    elif row["china_share_pct"] >= 40:
        verdict = "⚠  HYPOTHESIS PARTIALLY SUPPORTED"
        explanation = (
            "China already holds a significant share of the Canadian toy market. "
            "Opportunities exist but competition is already high."
        )
    else:
        verdict = "❌ HYPOTHESIS NOT STRONGLY SUPPORTED"
        explanation = (
            "HS 95 does not rank among top opportunities relative to other chapters. "
            "Consider other categories with larger absolute gaps."
        )

    print(f"\n  Verdict: {verdict}")
    print(f"  {explanation}")
    print()


def mode_deepdive(chapter: str, years: list[int], use_csv: bool, use_demo: bool = False):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║     CANADA IMPORT GAP — DEEP DIVE: HS Chapter {chapter:<14}║")
    if use_demo:
        print("║                   [DEMO MODE — synthetic data]              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\nYears: {years}")

    print(f"\n[1/3] Fetching World imports (HS6 within chapter {chapter})...")
    world_records = fetch_hs6_chapter(WORLD_CODE, chapter, years, use_demo=use_demo)

    print(f"\n[2/3] Fetching China imports (HS6 within chapter {chapter})...")
    china_records = fetch_hs6_chapter(CHINA_CODE, chapter, years, use_demo=use_demo)

    print("\n[3/3] Computing gap & opportunity scores...")
    summary_df = compute_gap(world_records, china_records)

    print(f"\nTotal HS6 products in chapter {chapter}: {len(summary_df)}")

    print(f"\n┌──────────────────────────────────────────────────────────────┐")
    print(f"│       TOP 15 PRODUCTS — HS Chapter {chapter:<27}│")
    print(f"└──────────────────────────────────────────────────────────────┘")
    print_top_n(summary_df, n=15)

    print("\n[Exporting results...]")
    if use_csv:
        path = export_csv(summary_df, f"canada_import_gap_hs{chapter}_deepdive.csv")
    else:
        path = export_deepdive(summary_df, chapter)
    print(f"  Saved: {path}")
    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(
        description="Canada Import Gap Analysis using UN Comtrade data"
    )
    parser.add_argument(
        "--mode",
        choices=["holistic", "deepdive"],
        required=True,
        help="Analysis mode: 'holistic' (all HS2 chapters) or 'deepdive' (one chapter, HS6 level)",
    )
    parser.add_argument(
        "--chapter",
        type=str,
        default="95",
        help="HS chapter for deep dive (e.g. 95 for Toys). Default: 95",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years to include. Default: {DEFAULT_YEARS}",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Export to CSV instead of Excel",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Use synthetic data instead of live API calls. "
            "Useful when the API is unreachable or to test the pipeline quickly."
        ),
    )

    args = parser.parse_args()

    if args.mode == "holistic":
        mode_holistic(years=args.years, use_csv=args.csv, use_demo=args.demo)
    elif args.mode == "deepdive":
        mode_deepdive(chapter=args.chapter, years=args.years, use_csv=args.csv, use_demo=args.demo)


if __name__ == "__main__":
    main()
