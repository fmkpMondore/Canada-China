"""
Gap analysis and opportunity scoring.
"""

import pandas as pd


def records_to_df(records: list[dict]) -> pd.DataFrame:
    """Convert raw API records to a cleaned DataFrame."""
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Keep only the columns we need (some may be missing)
    cols_map = {
        "period": "year",
        "cmdCode": "hs_code",
        "cmdDesc": "description",
        "partnerCode": "partner_code",
        "primaryValue": "value_usd",
        "netWgt": "net_weight_kg",
    }
    available = {k: v for k, v in cols_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce").fillna(0)
    df["hs_code"] = df["hs_code"].astype(str).str.strip()

    return df


def compute_gap(
    world_records: list[dict],
    china_records: list[dict],
    group_col: str = "hs_code",
) -> pd.DataFrame:
    """
    Aggregate world and china data, compute gap and opportunity score.

    group_col: 'hs_code' for aggregated view
    Returns a DataFrame sorted by opportunity_score descending.
    """
    world_df = records_to_df(world_records)
    china_df = records_to_df(china_records)

    if world_df.empty:
        raise ValueError("No world data available — check API response.")

    # Aggregate across all years
    world_agg = (
        world_df.groupby([group_col, "description"], as_index=False)["value_usd"]
        .sum()
        .rename(columns={"value_usd": "world_usd", "description": "description"})
    )

    if not china_df.empty:
        china_agg = (
            china_df.groupby([group_col], as_index=False)["value_usd"]
            .sum()
            .rename(columns={"value_usd": "china_usd"})
        )
    else:
        china_agg = pd.DataFrame(columns=[group_col, "china_usd"])

    merged = world_agg.merge(china_agg, on=group_col, how="left")
    merged["china_usd"] = merged["china_usd"].fillna(0)

    merged["gap_usd"] = merged["world_usd"] - merged["china_usd"]
    merged["china_share_pct"] = (merged["china_usd"] / merged["world_usd"].replace(0, pd.NA)) * 100
    merged["china_share_pct"] = merged["china_share_pct"].fillna(0).round(2)

    # Opportunity score: large gap + low china participation
    merged["opportunity_score"] = merged["gap_usd"] * (1 - merged["china_share_pct"] / 100)

    merged = merged[merged["world_usd"] > 0].copy()
    merged = merged.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    merged.index += 1  # 1-based rank
    merged.index.name = "rank"

    return merged


def compute_gap_by_year(
    world_records: list[dict],
    china_records: list[dict],
    group_col: str = "hs_code",
) -> pd.DataFrame:
    """Same as compute_gap but keeps year dimension for trend tab."""
    world_df = records_to_df(world_records)
    china_df = records_to_df(china_records)

    if world_df.empty:
        return pd.DataFrame()

    world_agg = (
        world_df.groupby(["year", group_col, "description"], as_index=False)["value_usd"]
        .sum()
        .rename(columns={"value_usd": "world_usd"})
    )

    if not china_df.empty:
        china_agg = (
            china_df.groupby(["year", group_col], as_index=False)["value_usd"]
            .sum()
            .rename(columns={"value_usd": "china_usd"})
        )
    else:
        china_agg = pd.DataFrame(columns=["year", group_col, "china_usd"])

    merged = world_agg.merge(china_agg, on=["year", group_col], how="left")
    merged["china_usd"] = merged["china_usd"].fillna(0)
    merged["gap_usd"] = merged["world_usd"] - merged["china_usd"]
    merged["china_share_pct"] = (
        (merged["china_usd"] / merged["world_usd"].replace(0, pd.NA)) * 100
    ).fillna(0).round(2)

    return merged.sort_values(["year", "world_usd"], ascending=[True, False])


def print_top_n(df: pd.DataFrame, n: int = 15, highlight_chapter: str = None):
    """Print a formatted ranking table to stdout."""
    top = df.head(n)

    header = (
        f"{'Rank':>4}  {'HS':>6}  {'Description':<45}  "
        f"{'World(USD M)':>12}  {'China(USD M)':>12}  "
        f"{'Gap(USD M)':>10}  {'CN Share%':>9}  {'Opp.Score(B)':>12}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    for rank, row in top.iterrows():
        marker = " ◀" if highlight_chapter and str(row["hs_code"]) == str(highlight_chapter) else ""
        print(
            f"{rank:>4}  {row['hs_code']:>6}  {str(row['description'])[:45]:<45}  "
            f"{row['world_usd']/1e6:>12,.1f}  "
            f"{row['china_usd']/1e6:>12,.1f}  "
            f"{row['gap_usd']/1e6:>10,.1f}  "
            f"{row['china_share_pct']:>9.1f}  "
            f"{row['opportunity_score']/1e9:>12,.2f}"
            f"{marker}"
        )

    print("=" * len(header))
