"""
Canada Import Gap Dashboard — Streamlit + Plotly
Interactive visualization of Canada's imports: World vs China

Run: streamlit run dashboard.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import DEFAULT_YEARS, CHINA_CODE, WORLD_CODE
from api import fetch_hs2_all_years, fetch_hs6_chapter
from analysis import records_to_df

# ─────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────
st.set_page_config(
    page_title="Canada Import Gap — Mondoré",
    page_icon="🍁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
  [data-testid="metric-container"] {
      background: #1a2744;
      border-radius: 10px;
      padding: 12px 18px;
      border-left: 4px solid #e63946;
  }
  [data-testid="metric-container"] label { color: #a8b8d8 !important; font-size: 0.78rem; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 1.4rem; }
  [data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 0.75rem; }

  .main-header {
      background: linear-gradient(135deg, #1a2744 0%, #e63946 100%);
      color: white; padding: 20px 28px; border-radius: 12px;
      margin-bottom: 20px;
  }
  .main-header h1 { margin: 0; font-size: 1.7rem; }
  .main-header p  { margin: 4px 0 0; opacity: 0.85; font-size: 0.9rem; }

  footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────
if "drill_chapter" not in st.session_state:
    st.session_state.drill_chapter = "95"


# ─────────────────────────────────────────────────
# Data loading (cached)
# ─────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_hs2_data(years: tuple) -> pd.DataFrame:
    years = list(years)
    world_r = fetch_hs2_all_years(WORLD_CODE, years, use_demo=False)
    china_r = fetch_hs2_all_years(CHINA_CODE, years, use_demo=False)

    world_df = records_to_df(world_r)
    china_df = records_to_df(china_r)

    world_agg = (
        world_df
        .groupby(["year", "hs_code", "description"], as_index=False)["value_usd"]
        .sum().rename(columns={"value_usd": "world_usd"})
    )
    china_agg = (
        china_df
        .groupby(["year", "hs_code"], as_index=False)["value_usd"]
        .sum().rename(columns={"value_usd": "china_usd"})
    )

    db = world_agg.merge(china_agg, on=["year", "hs_code"], how="left")
    db["china_usd"] = db["china_usd"].fillna(0)
    db["gap_usd"] = db["world_usd"] - db["china_usd"]
    db["china_share_pct"] = (db["china_usd"] / db["world_usd"].replace(0, float("nan")) * 100).fillna(0).round(2)
    db["world_usd_m"] = (db["world_usd"] / 1e6).round(1)
    db["china_usd_m"] = (db["china_usd"] / 1e6).round(1)
    db["gap_usd_m"]   = (db["gap_usd"] / 1e6).round(1)
    db["opportunity_score"] = (db["gap_usd"] * (1 - db["china_share_pct"] / 100) / 1e9).round(3)
    db["year"] = db["year"].astype(int)
    return db


@st.cache_data(show_spinner=False)
def load_hs6_data(chapter: str, years: tuple) -> pd.DataFrame:
    years = list(years)
    world_r = fetch_hs6_chapter(WORLD_CODE, chapter, years, use_demo=False)
    china_r = fetch_hs6_chapter(CHINA_CODE, chapter, years, use_demo=False)

    world_df = records_to_df(world_r)
    china_df = records_to_df(china_r)

    world_agg = (
        world_df
        .groupby(["hs_code", "description"], as_index=False)["value_usd"]
        .sum().rename(columns={"value_usd": "world_usd"})
    )
    china_agg = (
        china_df
        .groupby(["hs_code"], as_index=False)["value_usd"]
        .sum().rename(columns={"value_usd": "china_usd"})
    )

    db = world_agg.merge(china_agg, on="hs_code", how="left")
    db["china_usd"] = db["china_usd"].fillna(0)
    db["gap_usd"] = db["world_usd"] - db["china_usd"]
    db["china_share_pct"] = (db["china_usd"] / db["world_usd"].replace(0, float("nan")) * 100).fillna(0).round(2)
    db["world_usd_m"] = (db["world_usd"] / 1e6).round(1)
    db["china_usd_m"] = (db["china_usd"] / 1e6).round(1)
    db["gap_usd_m"]   = (db["gap_usd"] / 1e6).round(1)
    db["opportunity_score"] = (db["gap_usd"] * (1 - db["china_share_pct"] / 100) / 1e9).round(4)
    return db.sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def build_summary(db: pd.DataFrame) -> pd.DataFrame:
    agg = (
        db
        .groupby(["hs_code", "description"], as_index=False)
        .agg(world_usd_m=("world_usd_m", "sum"),
             china_usd_m=("china_usd_m", "sum"),
             gap_usd_m=("gap_usd_m", "sum"))
    )
    agg["china_share_pct"] = (agg["china_usd_m"] / agg["world_usd_m"].replace(0, float("nan")) * 100).fillna(0).round(2)
    agg["opportunity_score"] = (agg["gap_usd_m"] * 1e6 * (1 - agg["china_share_pct"] / 100) / 1e9).round(3)
    agg["short_desc"] = agg["description"].str[:35]
    agg["label"] = agg["hs_code"] + " · " + agg["short_desc"]
    agg = agg.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    agg.index += 1
    agg.index.name = "rank"
    return agg


# ─────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🍁 Filters")
    selected_years = st.multiselect(
        "Years",
        options=[2021, 2022, 2023, 2024],
        default=[2021, 2022, 2023, 2024],
    )
    if not selected_years:
        selected_years = [2024]

    st.markdown("---")
    top_n = st.slider("# categories in ranking", 5, 30, 15)
    min_world = st.slider("Min. market size (USD B)", 0, 50, 0)

    st.markdown("---")
    st.markdown("**Deep Dive — HS2 Chapter**")
    chapter_input = st.text_input(
        "HS Chapter (2 digits)",
        value=st.session_state.drill_chapter,
        key="chapter_input_sidebar",
    )
    if chapter_input.strip() != st.session_state.drill_chapter:
        st.session_state.drill_chapter = chapter_input.strip().zfill(2)

    st.markdown("---")
    st.caption("Source: UN Comtrade | Mondoré Consulting")
    st.caption("Data: demo mode (realistic synthetic)")


# ─────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────

with st.spinner("Loading data..."):
    raw_db = load_hs2_data(tuple(selected_years))
    summary = build_summary(raw_db)
    summary_filtered = summary[summary["world_usd_m"] >= min_world * 1000]

# ─────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
  <h1>🍁 Canada Import Gap Analysis</h1>
  <p>Chinese export opportunities in the Canadian market · Mondoré Consulting</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# KPI Cards
# ─────────────────────────────────────────────────

total_world  = summary["world_usd_m"].sum() / 1000
total_china  = summary["china_usd_m"].sum() / 1000
total_gap    = summary["gap_usd_m"].sum() / 1000
avg_share    = (total_china / total_world * 100) if total_world > 0 else 0
best_score   = summary["opportunity_score"].max()
n_low_share  = (summary["china_share_pct"] < 15).sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🌍 World Total",    f"USD {total_world:,.0f} B",  f"{len(selected_years)} years")
c2.metric("🇨🇳 China Total",    f"USD {total_china:,.0f} B",  f"{avg_share:.1f}% share")
c3.metric("📈 Total Gap",      f"USD {total_gap:,.0f} B",    "available potential")
c4.metric("🏆 Top Opp. Score", f"{best_score:.0f} B USD",   "#1 category")
c5.metric("🎯 CN share < 15%", f"{n_low_share} categories", "low penetration")

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏠 About",
    "📊 Ranking",
    "🎯 Strategic Quadrant",
    "📅 Annual Trends",
    "🔍 Deep Dive HS6",
    "📋 Full Table",
])


# ══════════════════════════════════
# TAB 0 — HOME / ABOUT
# ══════════════════════════════════
with tab0:
    st.markdown("## 🍁 Canada Import Gap Analysis")
    st.markdown(
        "A strategic intelligence tool built by **Mondoré Consulting** to identify "
        "Chinese export opportunities in the Canadian market — powered by UN Comtrade data."
    )

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown("### 🎯 Objective")
        st.markdown("""
Canada imports over **USD 600 billion** in goods annually. China currently supplies
roughly **15–20%** of that total — but the share varies enormously across product categories.

This dashboard maps the **import gap**: categories where Canada buys heavily from the world
but China's penetration remains low. These gaps represent actionable export opportunities
for Chinese manufacturers and trading companies.
        """)

        st.markdown("### 📐 Methodology")
        st.markdown("""
| Metric | Definition |
|---|---|
| **World Imports** | Total Canadian imports from all countries |
| **China Imports** | Canadian imports specifically from China |
| **Gap** | World − China = volume not yet captured by China |
| **China Share %** | China / World × 100 |
| **Opportunity Score** | Gap × (1 − Share%) — rewards both large gap AND low penetration |
        """)

        st.markdown("### 🗂️ Data Source")
        st.markdown("""
- **UN Comtrade API** — official bilateral trade statistics
- Coverage: HS2 chapters (97 product categories) × years 2021–2024
- Current mode: **Realistic synthetic data** (demo) based on published Statistics Canada figures
- Live API mode: available with a valid UN Comtrade subscription key
        """)

    with col_r:
        st.markdown("### 🧭 Feature Guide")

        features = [
            ("📊 Ranking", "Top opportunities ranked by Opportunity Score. Click any row to instantly load its HS6 Deep Dive."),
            ("🎯 Strategic Quadrant", "Bubble chart plotting all categories by gap size vs China's share. Reveals PRIORITY, GROWTH, NICHE, and SATURATED zones."),
            ("📅 Annual Trends", "Track how world imports and China's share evolved year-over-year for selected categories."),
            ("🔍 Deep Dive HS6", "Zoom into any HS2 chapter to see 6-digit product breakdown — bar chart, scatter, and full table."),
            ("📋 Full Table", "Searchable, sortable table of all 97 HS2 categories with download to CSV and JSON."),
        ]

        for icon_title, desc in features:
            with st.expander(icon_title):
                st.markdown(desc)

        st.markdown("### ⚡ Quick Start")
        st.markdown("""
1. Use the **sidebar** to set years and minimum market size
2. Go to **📊 Ranking** — click a row to drill into products
3. Explore 6-digit breakdowns in **🔍 Deep Dive HS6**
4. Export results from **📋 Full Table**
        """)

    st.markdown("---")
    st.success(
        "**Live Mode** — Data is fetched directly from the UN Comtrade API "
        "(real bilateral trade statistics, Canada reporter, 2021–2024).",
        icon="✅",
    )


# ══════════════════════════════════
# TAB 1 — RANKING
# ══════════════════════════════════
with tab1:
    st.markdown(f"### Top {top_n} Opportunities by Opportunity Score")
    st.caption("Score = Gap × (1 − China Share%). Higher score = larger gap AND lower Chinese penetration.")

    top = summary_filtered.head(top_n).sort_values("opportunity_score", ascending=True)

    fig_rank = go.Figure()
    fig_rank.add_trace(go.Bar(
        y=top["label"], x=top["gap_usd_m"] / 1000,
        name="Gap (non-China)", orientation="h", marker_color="#e63946",
        hovertemplate="<b>%{y}</b><br>Gap: USD %{x:,.1f} B<extra></extra>",
    ))
    fig_rank.add_trace(go.Bar(
        y=top["label"], x=top["china_usd_m"] / 1000,
        name="China", orientation="h", marker_color="#f4a261",
        hovertemplate="<b>%{y}</b><br>China: USD %{x:,.1f} B<extra></extra>",
    ))
    fig_rank.update_layout(
        barmode="stack", height=max(400, top_n * 28),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis_title="USD Billions",
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#ffffff",
        xaxis=dict(gridcolor="#2a2a2a"), yaxis=dict(gridcolor="#2a2a2a"),
    )
    st.plotly_chart(fig_rank, use_container_width=True)

    st.markdown("#### Opportunity Score by Category")
    top_score = summary_filtered.head(top_n).sort_values("opportunity_score", ascending=True)
    fig_score = px.bar(
        top_score, x="opportunity_score", y="label", orientation="h",
        color="china_share_pct",
        color_continuous_scale=["#2ec4b6", "#f4a261", "#e63946"],
        labels={"opportunity_score": "Score (B USD)", "china_share_pct": "China Share %"},
        hover_data={"world_usd_m": True, "china_usd_m": True, "gap_usd_m": True},
    )
    fig_score.update_layout(
        height=max(400, top_n * 28), margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#ffffff",
        coloraxis_colorbar=dict(title="Share CN%"),
    )
    st.plotly_chart(fig_score, use_container_width=True)

    # ── Drill-down: clickable table ──────────────────────────
    st.markdown("#### ⚡ Click a Row → Deep Dive HS6")
    st.caption("Select any row below to load its 6-digit product breakdown in the **🔍 Deep Dive HS6** tab.")

    rank_display = (
        summary_filtered.head(top_n)
        .reset_index()[["rank", "hs_code", "description", "world_usd_m",
                         "china_usd_m", "gap_usd_m", "china_share_pct", "opportunity_score"]]
        .copy()
    )
    rank_display.columns = ["Rank", "HS2", "Category", "World(USD M)",
                             "China(USD M)", "Gap(USD M)", "Share CN%", "Score(B)"]

    sel = st.dataframe(
        rank_display,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Score(B)": st.column_config.ProgressColumn(
                "Score(B)", min_value=0,
                max_value=float(rank_display["Score(B)"].max()),
                format="%.2f",
            ),
            "Share CN%": st.column_config.ProgressColumn(
                "Share CN%", min_value=0, max_value=100, format="%.1f%%",
            ),
        },
    )

    if sel and sel.selection and sel.selection.get("rows"):
        chosen = rank_display.iloc[sel.selection["rows"][0]]
        st.session_state.drill_chapter = str(chosen["HS2"]).zfill(2)
        st.success(
            f"✅ Chapter **{chosen['HS2']} — {chosen['Category'][:50]}** loaded. "
            "Open the **🔍 Deep Dive HS6** tab to see the breakdown.",
        )

    st.markdown("##### Or jump directly to a top category:")
    quick_cols = st.columns(min(top_n, 8))
    for i, row in enumerate(summary_filtered.head(min(top_n, 8)).itertuples()):
        if quick_cols[i].button(f"🔍 {row.hs_code}", help=row.description, key=f"quick_{row.hs_code}"):
            st.session_state.drill_chapter = str(row.hs_code).zfill(2)
            st.rerun()


# ══════════════════════════════════
# TAB 2 — STRATEGIC QUADRANT
# ══════════════════════════════════
with tab2:
    st.markdown("### Strategic Quadrant — Gap Size vs China's Share")
    st.caption(
        "X = China's share (lower = more opportunity). "
        "Y = absolute gap. Bubble size = total market."
    )

    scatter_df = summary_filtered.copy()
    scatter_df["world_b"] = scatter_df["world_usd_m"] / 1000
    scatter_df["gap_b"]   = scatter_df["gap_usd_m"] / 1000

    med_share = 25
    med_gap   = scatter_df["gap_b"].median()

    fig_quad = px.scatter(
        scatter_df,
        x="china_share_pct", y="gap_b", size="world_b",
        color="opportunity_score",
        color_continuous_scale=["#264653", "#2ec4b6", "#f4a261", "#e63946"],
        hover_name="label",
        hover_data={"world_b": ":.1f", "gap_b": ":.1f",
                    "china_share_pct": ":.1f", "opportunity_score": ":.1f"},
        labels={"china_share_pct": "China Share (%)", "gap_b": "Gap (USD B)",
                "world_b": "Total Market (B)", "opportunity_score": "Opp. Score"},
        size_max=60,
    )
    fig_quad.add_vline(x=med_share, line_dash="dash", line_color="#555555", opacity=0.7)
    fig_quad.add_hline(y=med_gap,   line_dash="dash", line_color="#555555", opacity=0.7)

    y_max = scatter_df["gap_b"].max() * 1.05
    fig_quad.add_annotation(x=5,  y=y_max*0.92,  text="🎯 PRIORITY",   showarrow=False,
                            font=dict(color="#2ec4b6", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=55, y=y_max*0.92,  text="⚡ GROWTH",     showarrow=False,
                            font=dict(color="#f4a261", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=5,  y=med_gap*0.15, text="🔍 NICHE",     showarrow=False,
                            font=dict(color="#a8b8d8", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=55, y=med_gap*0.15, text="🔒 SATURATED", showarrow=False,
                            font=dict(color="#888888", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.update_layout(
        height=580, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#ffffff",
        xaxis=dict(gridcolor="#2a2a2a", range=[-2, 75]),
        yaxis=dict(gridcolor="#2a2a2a"),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_quad, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🎯 PRIORITY** — High gap, low China share")
        prio = summary_filtered[
            (summary_filtered["gap_usd_m"] / 1000 >= med_gap) &
            (summary_filtered["china_share_pct"] < med_share)
        ][["hs_code", "short_desc", "gap_usd_m", "china_share_pct"]].head(8)
        prio.columns = ["HS", "Category", "Gap(USD M)", "CN%"]
        st.dataframe(prio, hide_index=True, use_container_width=True)
    with col_b:
        st.markdown("**⚡ GROWTH** — High gap, China already present")
        grow = summary_filtered[
            (summary_filtered["gap_usd_m"] / 1000 >= med_gap) &
            (summary_filtered["china_share_pct"] >= med_share)
        ][["hs_code", "short_desc", "gap_usd_m", "china_share_pct"]].head(8)
        grow.columns = ["HS", "Category", "Gap(USD M)", "CN%"]
        st.dataframe(grow, hide_index=True, use_container_width=True)


# ══════════════════════════════════
# TAB 3 — ANNUAL TRENDS
# ══════════════════════════════════
with tab3:
    st.markdown("### Annual Trends — Import Evolution")

    all_labels = summary["label"].tolist()
    default_cats = all_labels[:5]
    selected_cats = st.multiselect("Select categories to track", all_labels, default=default_cats)

    if selected_cats:
        hs_selected = [lb.split(" · ")[0] for lb in selected_cats]
        trend_df = raw_db[raw_db["hs_code"].isin(hs_selected)].copy()
        trend_df["label"] = trend_df["hs_code"] + " · " + trend_df["description"].str[:30]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 🌍 World Imports (USD M)")
            fig_w = px.line(trend_df, x="year", y="world_usd_m", color="label", markers=True,
                            labels={"world_usd_m": "USD M", "year": "Year", "label": "Category"})
            fig_w.update_layout(height=350, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                                yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
                                legend=dict(font=dict(size=9)))
            st.plotly_chart(fig_w, use_container_width=True)

        with col2:
            st.markdown("#### 🇨🇳 China's Share (%) by Year")
            fig_s = px.line(trend_df, x="year", y="china_share_pct", color="label", markers=True,
                            labels={"china_share_pct": "Share %", "year": "Year", "label": "Category"})
            fig_s.update_layout(height=350, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                                yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
                                legend=dict(font=dict(size=9)))
            st.plotly_chart(fig_s, use_container_width=True)

        st.markdown("#### 📈 Absolute Gap (USD M) — Evolution")
        fig_gap = px.area(trend_df, x="year", y="gap_usd_m", color="label",
                          labels={"gap_usd_m": "Gap (USD M)", "year": "Year", "label": "Category"})
        fig_gap.update_layout(height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                              font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                              yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
                              legend=dict(font=dict(size=9)))
        st.plotly_chart(fig_gap, use_container_width=True)
    else:
        st.info("Select at least one category above.")


# ══════════════════════════════════
# TAB 4 — DEEP DIVE HS6
# ══════════════════════════════════
with tab4:
    ch = st.session_state.drill_chapter.zfill(2) if st.session_state.drill_chapter else "95"
    st.markdown(f"### Deep Dive — HS Chapter {ch}")

    ch_row = summary[summary["hs_code"] == ch]
    if not ch_row.empty:
        ch_name  = ch_row.iloc[0]["description"]
        ch_rank  = ch_row.index[0]
        ch_score = ch_row.iloc[0]["opportunity_score"]
        ch_share = ch_row.iloc[0]["china_share_pct"]
        st.markdown(f"**{ch_name}** — Rank #{ch_rank} | Score: {ch_score:.1f} B | China share: {ch_share:.1f}%")

    with st.spinner(f"Loading HS6 products for chapter {ch}..."):
        hs6 = load_hs6_data(ch, tuple(selected_years))

    if hs6.empty:
        st.warning("No data found for this chapter.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("HS6 Products", len(hs6))
        c2.metric("Largest gap", f"USD {hs6['gap_usd_m'].max():,.0f} M", hs6.loc[0, 'description'][:30])
        c3.metric("Lowest CN share", f"{hs6['china_share_pct'].min():.1f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        top12 = hs6.head(12)
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Bar(x=top12["description"].str[:40], y=top12["world_usd_m"],
                                name="World", marker_color="#264653"))
        fig_dd.add_trace(go.Bar(x=top12["description"].str[:40], y=top12["china_usd_m"],
                                name="China", marker_color="#f4a261"))
        fig_dd.update_layout(
            barmode="group", height=420, title=f"Top 12 Products — HS {ch}",
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#ffffff",
            xaxis=dict(tickangle=-30, gridcolor="#2a2a2a"),
            yaxis=dict(title="USD M", gridcolor="#2a2a2a"),
            legend=dict(orientation="h"), margin=dict(t=40, b=80),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        st.markdown("#### HS6 Quadrant — Opportunity by Product")
        fig_s6 = px.scatter(
            hs6, x="china_share_pct", y="gap_usd_m", size="world_usd_m",
            color="opportunity_score", hover_name="description",
            color_continuous_scale=["#264653", "#2ec4b6", "#e63946"], size_max=40,
            labels={"china_share_pct": "China Share (%)", "gap_usd_m": "Gap (USD M)",
                    "world_usd_m": "Total Market"},
        )
        fig_s6.update_layout(height=400, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                             font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                             yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10))
        st.plotly_chart(fig_s6, use_container_width=True)

        display_hs6 = hs6[["hs_code", "description", "world_usd_m", "china_usd_m",
                            "gap_usd_m", "china_share_pct", "opportunity_score"]].copy()
        display_hs6.columns = ["HS6", "Product", "World(M)", "China(M)", "Gap(M)", "Share%", "Score(B)"]
        st.dataframe(display_hs6, hide_index=True, use_container_width=True)


# ══════════════════════════════════
# TAB 5 — FULL TABLE
# ══════════════════════════════════
with tab5:
    st.markdown("### Full Table — All HS2 Chapters")

    search = st.text_input("🔍 Search by HS code or description", "")

    disp = summary_filtered.reset_index()[
        ["rank", "hs_code", "description", "world_usd_m", "china_usd_m",
         "gap_usd_m", "china_share_pct", "opportunity_score"]
    ].copy()
    disp.columns = ["Rank", "HS2", "Category", "World(USD M)", "China(USD M)",
                    "Gap(USD M)", "Share CN%", "Score(B)"]

    if search:
        mask = (
            disp["HS2"].str.contains(search, case=False, na=False) |
            disp["Category"].str.contains(search, case=False, na=False)
        )
        disp = disp[mask]

    st.dataframe(
        disp,
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "Score(B)": st.column_config.ProgressColumn(
                "Score(B)", min_value=0,
                max_value=float(disp["Score(B)"].max()) if len(disp) > 0 else 1,
                format="%.2f",
            ),
            "Share CN%": st.column_config.ProgressColumn(
                "Share CN%", min_value=0, max_value=100, format="%.1f%%",
            ),
            "Gap(USD M)":   st.column_config.NumberColumn("Gap(USD M)",   format="%,.0f"),
            "World(USD M)": st.column_config.NumberColumn("World(USD M)", format="%,.0f"),
            "China(USD M)": st.column_config.NumberColumn("China(USD M)", format="%,.0f"),
        },
    )

    col_dl1, col_dl2 = st.columns(2)
    col_dl1.download_button(
        "⬇️ Download CSV",
        disp.to_csv(index=False).encode("utf-8"),
        "canada_import_gap.csv",
        "text/csv",
    )
    col_dl2.download_button(
        "⬇️ Download JSON",
        disp.to_json(orient="records", indent=2).encode("utf-8"),
        "canada_import_gap.json",
        "application/json",
    )


# ─────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<center><small>Mondoré Consulting · Canada Import Gap Analysis · "
    "Source: UN Comtrade API · Live production data</small></center>",
    unsafe_allow_html=True,
)
