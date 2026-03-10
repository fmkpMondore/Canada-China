"""
Canada Import Gap Dashboard — Streamlit + Plotly
Visualização interativa das importações do Canadá: Mundo vs China

Rodar: streamlit run dashboard.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import DEFAULT_YEARS, CHINA_CODE, WORLD_CODE
from api import fetch_hs2_all_years, fetch_hs6_chapter
from analysis import records_to_df

# ─────────────────────────────────────────────────
# Config da página
# ─────────────────────────────────────────────────
st.set_page_config(
    page_title="Canada Import Gap — Mondoré",
    page_icon="🍁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema / CSS custom
st.markdown("""
<style>
  /* Fundo escuro nos cards de métrica */
  [data-testid="metric-container"] {
      background: #1a2744;
      border-radius: 10px;
      padding: 12px 18px;
      border-left: 4px solid #e63946;
  }
  [data-testid="metric-container"] label { color: #a8b8d8 !important; font-size: 0.78rem; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 1.4rem; }
  [data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 0.75rem; }

  /* Header */
  .main-header {
      background: linear-gradient(135deg, #1a2744 0%, #e63946 100%);
      color: white; padding: 20px 28px; border-radius: 12px;
      margin-bottom: 20px;
  }
  .main-header h1 { margin: 0; font-size: 1.7rem; }
  .main-header p  { margin: 4px 0 0; opacity: 0.85; font-size: 0.9rem; }

  /* Ocultar rodapé Streamlit */
  footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────
# Carregamento de dados (com cache)
# ─────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_hs2_data(years: tuple) -> pd.DataFrame:
    years = list(years)
    world_r = fetch_hs2_all_years(WORLD_CODE, years, use_demo=True)
    china_r = fetch_hs2_all_years(CHINA_CODE, years, use_demo=True)

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
    world_r = fetch_hs6_chapter(WORLD_CODE, chapter, years, use_demo=True)
    china_r = fetch_hs6_chapter(CHINA_CODE, chapter, years, use_demo=True)

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
    st.markdown("## 🍁 Filtros")
    selected_years = st.multiselect(
        "Anos",
        options=[2021, 2022, 2023, 2024],
        default=[2021, 2022, 2023, 2024],
    )
    if not selected_years:
        selected_years = [2024]

    st.markdown("---")
    top_n = st.slider("Nº de categorias no ranking", 5, 30, 15)
    min_world = st.slider("Mercado mínimo (USD B)", 0, 50, 0)

    st.markdown("---")
    st.markdown("**Deep Dive — HS2 Chapter**")
    chapter_input = st.text_input("Capítulo HS (2 dígitos)", value="95")

    st.markdown("---")
    st.caption("Fonte: UN Comtrade | Mondoré Consulting")
    st.caption("Dados: demo mode (sintéticos realistas)")


# ─────────────────────────────────────────────────
# Carrega dados
# ─────────────────────────────────────────────────

with st.spinner("Carregando dados..."):
    raw_db = load_hs2_data(tuple(selected_years))
    summary = build_summary(raw_db)
    summary_filtered = summary[summary["world_usd_m"] >= min_world * 1000]

# ─────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
  <h1>🍁 Canada Import Gap Analysis</h1>
  <p>Oportunidades de exportação chinesa no mercado canadense · Mondoré Consulting</p>
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
c1.metric("🌍 Total Mundo",      f"USD {total_world:,.0f} B",  f"{len(selected_years)} anos")
c2.metric("🇨🇳 Total China",      f"USD {total_china:,.0f} B",  f"{avg_share:.1f}% share")
c3.metric("📈 Gap Total",        f"USD {total_gap:,.0f} B",    "potencial disponível")
c4.metric("🏆 Maior Opp. Score", f"{best_score:.0f} B USD",   "categoria top 1")
c5.metric("🎯 CN share < 15%",   f"{n_low_share} categorias", "baixa penetração")

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Ranking", "🎯 Quadrante Estratégico", "📅 Tendência Anual",
    "🔍 Deep Dive HS6", "📋 Tabela Completa"
])


# ══════════════════════════════════
# TAB 1 — RANKING
# ══════════════════════════════════
with tab1:
    st.markdown(f"### Top {top_n} Oportunidades por Opportunity Score")
    st.caption("Score = Gap × (1 − Share China%). Quanto maior o gap E menor a participação da China, maior o score.")

    top = summary_filtered.head(top_n).sort_values("opportunity_score", ascending=True)

    fig_rank = go.Figure()

    # Barras do gap (não capturado pela China)
    fig_rank.add_trace(go.Bar(
        y=top["label"],
        x=top["gap_usd_m"] / 1000,
        name="Gap (não-China)",
        orientation="h",
        marker_color="#e63946",
        hovertemplate="<b>%{y}</b><br>Gap: USD %{x:,.1f} B<extra></extra>",
    ))

    # Barras da China
    fig_rank.add_trace(go.Bar(
        y=top["label"],
        x=top["china_usd_m"] / 1000,
        name="China",
        orientation="h",
        marker_color="#f4a261",
        hovertemplate="<b>%{y}</b><br>China: USD %{x:,.1f} B<extra></extra>",
    ))

    fig_rank.update_layout(
        barmode="stack",
        height=max(400, top_n * 28),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis_title="USD Bilhões",
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#ffffff",
        xaxis=dict(gridcolor="#2a2a2a"),
        yaxis=dict(gridcolor="#2a2a2a"),
    )
    st.plotly_chart(fig_rank, use_container_width=True)

    # Opportunity Score separado
    st.markdown("#### Opportunity Score por Categoria")
    top_score = summary_filtered.head(top_n).sort_values("opportunity_score", ascending=True)

    fig_score = px.bar(
        top_score,
        x="opportunity_score",
        y="label",
        orientation="h",
        color="china_share_pct",
        color_continuous_scale=["#2ec4b6", "#f4a261", "#e63946"],
        labels={"opportunity_score": "Score (B USD)", "china_share_pct": "Share China %"},
        hover_data={"world_usd_m": True, "china_usd_m": True, "gap_usd_m": True},
    )
    fig_score.update_layout(
        height=max(400, top_n * 28),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#ffffff",
        coloraxis_colorbar=dict(title="Share CN%"),
    )
    st.plotly_chart(fig_score, use_container_width=True)


# ══════════════════════════════════
# TAB 2 — QUADRANTE ESTRATÉGICO
# ══════════════════════════════════
with tab2:
    st.markdown("### Quadrante Estratégico — Tamanho do Gap vs Share da China")
    st.caption(
        "X = share da China (menor = mais oportunidade). "
        "Y = gap absoluto. Tamanho da bolha = mercado total."
    )

    scatter_df = summary_filtered.copy()
    scatter_df["world_b"] = scatter_df["world_usd_m"] / 1000
    scatter_df["gap_b"] = scatter_df["gap_usd_m"] / 1000

    # Linha de corte dos quadrantes
    med_share = 25
    med_gap   = scatter_df["gap_b"].median()

    fig_quad = px.scatter(
        scatter_df,
        x="china_share_pct",
        y="gap_b",
        size="world_b",
        color="opportunity_score",
        color_continuous_scale=["#264653", "#2ec4b6", "#f4a261", "#e63946"],
        hover_name="label",
        hover_data={
            "world_b": ":.1f",
            "gap_b": ":.1f",
            "china_share_pct": ":.1f",
            "opportunity_score": ":.1f",
        },
        labels={
            "china_share_pct": "Share China (%)",
            "gap_b": "Gap (USD B)",
            "world_b": "Mercado Total (B)",
            "opportunity_score": "Opp. Score",
        },
        size_max=60,
    )

    # Linhas de quadrante
    fig_quad.add_vline(x=med_share, line_dash="dash", line_color="#555555", opacity=0.7)
    fig_quad.add_hline(y=med_gap,   line_dash="dash", line_color="#555555", opacity=0.7)

    # Anotações nos quadrantes
    y_max = scatter_df["gap_b"].max() * 1.05
    fig_quad.add_annotation(x=5,  y=y_max*0.92, text="🎯 PRIORIDADE", showarrow=False,
                            font=dict(color="#2ec4b6", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=55, y=y_max*0.92, text="⚡ CRESCIMENTO", showarrow=False,
                            font=dict(color="#f4a261", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=5,  y=med_gap*0.15, text="🔍 NICHO", showarrow=False,
                            font=dict(color="#a8b8d8", size=13), bgcolor="rgba(0,0,0,0.5)")
    fig_quad.add_annotation(x=55, y=med_gap*0.15, text="🔒 SATURADO", showarrow=False,
                            font=dict(color="#888888", size=13), bgcolor="rgba(0,0,0,0.5)")

    fig_quad.update_layout(
        height=580,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#ffffff",
        xaxis=dict(gridcolor="#2a2a2a", range=[-2, 75]),
        yaxis=dict(gridcolor="#2a2a2a"),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_quad, use_container_width=True)

    # Tabela dos quadrantes
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🎯 PRIORIDADE** — Gap alto, share baixo")
        prio = summary_filtered[
            (summary_filtered["gap_usd_m"] / 1000 >= med_gap) &
            (summary_filtered["china_share_pct"] < med_share)
        ][["hs_code", "short_desc", "gap_usd_m", "china_share_pct"]].head(8)
        prio.columns = ["HS", "Categoria", "Gap(USD M)", "CN%"]
        st.dataframe(prio, hide_index=True, use_container_width=True)
    with col_b:
        st.markdown("**⚡ CRESCIMENTO** — Gap alto, China já presente")
        grow = summary_filtered[
            (summary_filtered["gap_usd_m"] / 1000 >= med_gap) &
            (summary_filtered["china_share_pct"] >= med_share)
        ][["hs_code", "short_desc", "gap_usd_m", "china_share_pct"]].head(8)
        grow.columns = ["HS", "Categoria", "Gap(USD M)", "CN%"]
        st.dataframe(grow, hide_index=True, use_container_width=True)


# ══════════════════════════════════
# TAB 3 — TENDÊNCIA ANUAL
# ══════════════════════════════════
with tab3:
    st.markdown("### Tendência Anual — Evolução das Importações")

    # Seletor de categorias para acompanhar
    all_labels = summary["label"].tolist()
    default_cats = all_labels[:5]
    selected_cats = st.multiselect("Selecione categorias para acompanhar", all_labels, default=default_cats)

    if selected_cats:
        hs_selected = [lb.split(" · ")[0] for lb in selected_cats]
        trend_df = raw_db[raw_db["hs_code"].isin(hs_selected)].copy()
        trend_df["label"] = trend_df["hs_code"] + " · " + trend_df["description"].str[:30]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🌍 Importação do Mundo (USD M)")
            fig_w = px.line(
                trend_df,
                x="year", y="world_usd_m", color="label",
                markers=True,
                labels={"world_usd_m": "USD M", "year": "Ano", "label": "Categoria"},
            )
            fig_w.update_layout(
                height=350, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
                legend=dict(font=dict(size=9)),
            )
            st.plotly_chart(fig_w, use_container_width=True)

        with col2:
            st.markdown("#### 🇨🇳 Share da China (%) por Ano")
            fig_s = px.line(
                trend_df,
                x="year", y="china_share_pct", color="label",
                markers=True,
                labels={"china_share_pct": "Share %", "year": "Ano", "label": "Categoria"},
            )
            fig_s.update_layout(
                height=350, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
                yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
                legend=dict(font=dict(size=9)),
            )
            st.plotly_chart(fig_s, use_container_width=True)

        # Gap ao longo do tempo
        st.markdown("#### 📈 Gap Absoluto (USD M) — Evolução")
        fig_gap = px.area(
            trend_df,
            x="year", y="gap_usd_m", color="label",
            labels={"gap_usd_m": "Gap (USD M)", "year": "Ano", "label": "Categoria"},
        )
        fig_gap.update_layout(
            height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#ffffff", xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a"), margin=dict(t=10, b=10),
            legend=dict(font=dict(size=9)),
        )
        st.plotly_chart(fig_gap, use_container_width=True)
    else:
        st.info("Selecione ao menos uma categoria acima.")


# ══════════════════════════════════
# TAB 4 — DEEP DIVE HS6
# ══════════════════════════════════
with tab4:
    ch = chapter_input.strip().zfill(2) if chapter_input.strip() else "95"
    st.markdown(f"### Deep Dive — HS Chapter {ch}")

    # Busca no summary o nome do capítulo
    ch_row = summary[summary["hs_code"] == ch]
    if not ch_row.empty:
        ch_name = ch_row.iloc[0]["description"]
        ch_rank = ch_row.index[0]
        ch_score = ch_row.iloc[0]["opportunity_score"]
        ch_share = ch_row.iloc[0]["china_share_pct"]
        st.markdown(f"**{ch_name}** — Rank #{ch_rank} | Score: {ch_score:.1f} B | China share: {ch_share:.1f}%")

    with st.spinner(f"Carregando produtos HS6 do capítulo {ch}..."):
        hs6 = load_hs6_data(ch, tuple(selected_years))

    if hs6.empty:
        st.warning("Nenhum dado encontrado para este capítulo.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Produtos HS6", len(hs6))
        c2.metric("Maior gap", f"USD {hs6['gap_usd_m'].max():,.0f} M", hs6.loc[0, 'description'][:30])
        c3.metric("Menor share CN", f"{hs6['china_share_pct'].min():.1f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        # Waterfall — top 12 produtos
        top12 = hs6.head(12)

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Bar(
            x=top12["description"].str[:40],
            y=top12["world_usd_m"],
            name="Mundo",
            marker_color="#264653",
        ))
        fig_dd.add_trace(go.Bar(
            x=top12["description"].str[:40],
            y=top12["china_usd_m"],
            name="China",
            marker_color="#f4a261",
        ))
        fig_dd.update_layout(
            barmode="group",
            height=420,
            title=f"Top 12 Produtos — HS {ch}",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font_color="#ffffff",
            xaxis=dict(tickangle=-30, gridcolor="#2a2a2a"),
            yaxis=dict(title="USD M", gridcolor="#2a2a2a"),
            legend=dict(orientation="h"),
            margin=dict(t=40, b=80),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        # Scatter HS6
        st.markdown("#### Quadrante HS6 — Oportunidade por produto")
        fig_s6 = px.scatter(
            hs6,
            x="china_share_pct",
            y="gap_usd_m",
            size="world_usd_m",
            color="opportunity_score",
            hover_name="description",
            color_continuous_scale=["#264653", "#2ec4b6", "#e63946"],
            size_max=40,
            labels={
                "china_share_pct": "Share China (%)",
                "gap_usd_m": "Gap (USD M)",
                "world_usd_m": "Mercado Total",
            },
        )
        fig_s6.update_layout(
            height=400,
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font_color="#ffffff",
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a"),
            margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig_s6, use_container_width=True)

        # Tabela HS6
        display_hs6 = hs6[["hs_code", "description", "world_usd_m", "china_usd_m",
                            "gap_usd_m", "china_share_pct", "opportunity_score"]].copy()
        display_hs6.columns = ["HS6", "Produto", "Mundo(M)", "China(M)", "Gap(M)", "Share%", "Score(B)"]
        st.dataframe(display_hs6, hide_index=True, use_container_width=True)


# ══════════════════════════════════
# TAB 5 — TABELA COMPLETA
# ══════════════════════════════════
with tab5:
    st.markdown("### Tabela Completa — Todos os Capítulos HS2")

    # Filtro de busca
    search = st.text_input("🔍 Buscar por HS code ou descrição", "")

    disp = summary_filtered.reset_index()[
        ["rank", "hs_code", "description", "world_usd_m", "china_usd_m",
         "gap_usd_m", "china_share_pct", "opportunity_score"]
    ].copy()
    disp.columns = ["Rank", "HS2", "Categoria", "Mundo(USD M)", "China(USD M)",
                    "Gap(USD M)", "Share CN%", "Score(B)"]

    if search:
        mask = (
            disp["HS2"].str.contains(search, case=False, na=False) |
            disp["Categoria"].str.contains(search, case=False, na=False)
        )
        disp = disp[mask]

    st.dataframe(
        disp.style
            .background_gradient(subset=["Score(B)"], cmap="RdYlGn")
            .background_gradient(subset=["Share CN%"], cmap="RdYlGn_r")
            .format({
                "Mundo(USD M)": "{:,.0f}",
                "China(USD M)": "{:,.0f}",
                "Gap(USD M)":   "{:,.0f}",
                "Share CN%":    "{:.1f}",
                "Score(B)":     "{:.2f}",
            }),
        use_container_width=True,
        height=600,
    )

    st.download_button(
        "⬇️ Download CSV",
        disp.to_csv(index=False).encode("utf-8"),
        "canada_import_gap.csv",
        "text/csv",
    )


# ─────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<center><small>Mondoré Consulting · Canada Import Gap Analysis · "
    "Fonte: UN Comtrade API · Dados: demo sintético</small></center>",
    unsafe_allow_html=True,
)
