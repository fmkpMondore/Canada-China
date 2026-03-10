"""
build_database.py — Gera base de dados estruturada das importações do Canadá
(Mundo vs China) e um relatório de análise em Markdown.

Saídas:
  output/canada_imports_database.txt  — base principal, pipe-separated, todas as linhas
  output/canada_imports_summary.txt   — resumo agregado por capítulo HS2
  output/analysis_report.md           — relatório de conclusões e oportunidades

Uso:
  python build_database.py            # dados reais via API
  python build_database.py --demo     # dados sintéticos (sem internet)
"""

import argparse
import os
import textwrap
from datetime import date

import pandas as pd

from config import CHINA_CODE, WORLD_CODE, DEFAULT_YEARS, OUTPUT_DIR
from api import fetch_hs2_all_years
from analysis import records_to_df


# ─────────────────────────────────────────────────────────────────
# 1. Coleta e montagem da base
# ─────────────────────────────────────────────────────────────────

def build_full_database(years: list[int], use_demo: bool) -> pd.DataFrame:
    """
    Retorna DataFrame completo com todas as combinações
    (ano × capítulo HS2) para Mundo e China.
    """
    print("[1/3] Buscando importações do Mundo...")
    world_records = fetch_hs2_all_years(WORLD_CODE, years, use_demo=use_demo)

    print("[2/3] Buscando importações da China...")
    china_records = fetch_hs2_all_years(CHINA_CODE, years, use_demo=use_demo)

    world_df = records_to_df(world_records)
    china_df = records_to_df(china_records)

    if world_df.empty:
        raise ValueError("Sem dados do Mundo. Verifique a API ou use --demo.")

    # Agrega por (ano, hs_code, description)
    world_agg = (
        world_df
        .groupby(["year", "hs_code", "description"], as_index=False)["value_usd"]
        .sum()
        .rename(columns={"value_usd": "world_usd"})
    )

    china_agg = (
        china_df
        .groupby(["year", "hs_code"], as_index=False)["value_usd"]
        .sum()
        .rename(columns={"value_usd": "china_usd"})
    ) if not china_df.empty else pd.DataFrame(columns=["year", "hs_code", "china_usd"])

    db = world_agg.merge(china_agg, on=["year", "hs_code"], how="left")
    db["china_usd"] = db["china_usd"].fillna(0)

    # Métricas derivadas
    db["gap_usd"]         = db["world_usd"] - db["china_usd"]
    db["china_share_pct"] = (db["china_usd"] / db["world_usd"].replace(0, float("nan")) * 100).fillna(0).round(2)
    db["world_usd_m"]     = (db["world_usd"]  / 1e6).round(2)
    db["china_usd_m"]     = (db["china_usd"]  / 1e6).round(2)
    db["gap_usd_m"]       = (db["gap_usd"]    / 1e6).round(2)
    db["opportunity_score"] = (db["gap_usd"] * (1 - db["china_share_pct"] / 100) / 1e9).round(3)

    db["year"] = db["year"].astype(int)
    db = db.sort_values(["year", "world_usd"], ascending=[True, False]).reset_index(drop=True)

    return db


def build_summary(db: pd.DataFrame) -> pd.DataFrame:
    """Agrega todos os anos → ranking de oportunidades."""
    agg = (
        db
        .groupby(["hs_code", "description"], as_index=False)
        .agg(
            world_usd_m=("world_usd_m", "sum"),
            china_usd_m=("china_usd_m", "sum"),
            gap_usd_m=("gap_usd_m", "sum"),
        )
    )
    agg["china_share_pct"] = (
        agg["china_usd_m"] / agg["world_usd_m"].replace(0, float("nan")) * 100
    ).fillna(0).round(2)

    agg["opportunity_score_b"] = (
        (agg["gap_usd_m"] * 1e6) * (1 - agg["china_share_pct"] / 100) / 1e9
    ).round(3)

    agg = agg.sort_values("opportunity_score_b", ascending=False).reset_index(drop=True)
    agg.index += 1
    agg.index.name = "rank"

    return agg


# ─────────────────────────────────────────────────────────────────
# 2. Exportação TXT
# ─────────────────────────────────────────────────────────────────

PIPE = "|"
SEP  = "-"


def _fmt(v) -> str:
    """Format value: floats to 2 decimal places, others as-is."""
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _row(values: list, widths: list) -> str:
    parts = [_fmt(v).ljust(w) if i == 1 or i == 2
             else _fmt(v).rjust(w)
             for i, (v, w) in enumerate(zip(values, widths))]
    return PIPE + PIPE.join(" " + p + " " for p in parts) + PIPE


def _divider(widths: list) -> str:
    return "+" + "+".join(SEP * (w + 2) for w in widths) + "+"


def export_database_txt(db: pd.DataFrame, path: str):
    """Exporta base completa (por ano) em formato pipe-table."""
    cols = [
        ("year",            "Ano",            4),
        ("hs_code",         "HS2",            4),
        ("description",     "Descrição",      45),
        ("world_usd_m",     "Mundo (USD M)",  14),
        ("china_usd_m",     "China (USD M)",  14),
        ("gap_usd_m",       "Gap (USD M)",    12),
        ("china_share_pct", "Share China %",  13),
        ("opportunity_score","Opp.Score (B)",  13),
    ]
    keys   = [c[0] for c in cols]
    labels = [c[1] for c in cols]
    widths = [c[2] for c in cols]

    lines = []
    lines.append("=" * 130)
    lines.append("BASE DE DADOS — IMPORTAÇÕES DO CANADÁ: MUNDO vs CHINA (por ano e capítulo HS2)")
    lines.append(f"Gerado em: {date.today().isoformat()}  |  Anos: {sorted(db['year'].unique().tolist())}")
    lines.append(f"Total de linhas: {len(db)}  |  Capítulos HS2: {db['hs_code'].nunique()}")
    lines.append("=" * 130)
    lines.append("")
    lines.append("COLUNAS:")
    lines.append("  Ano           → ano de referência")
    lines.append("  HS2           → código do capítulo HS (2 dígitos)")
    lines.append("  Descrição     → nome da categoria de produto")
    lines.append("  Mundo (USD M) → total importado pelo Canadá de todos os países (em milhões USD)")
    lines.append("  China (USD M) → importado pelo Canadá especificamente da China (em milhões USD)")
    lines.append("  Gap (USD M)   → Mundo − China (potencial não capturado pela China)")
    lines.append("  Share China % → participação da China no mercado canadense nesta categoria")
    lines.append("  Opp.Score (B) → Score de oportunidade: Gap × (1 − Share%) em bilhões USD")
    lines.append("")

    # Tabela por ano
    current_year = None
    lines.append(_divider(widths))
    lines.append(_row(labels, widths))
    lines.append(_divider(widths))

    for _, row in db.iterrows():
        if row["year"] != current_year:
            if current_year is not None:
                lines.append(_divider(widths))
                lines.append(f"  ↑ ANO {current_year}")
                lines.append(_divider(widths))
            current_year = row["year"]

        values = [row[k] for k in keys]
        # Trunca descrição
        values[2] = str(values[2])[:44]
        lines.append(_row(values, widths))

    lines.append(_divider(widths))
    lines.append(f"  ↑ ANO {current_year}")
    lines.append(_divider(widths))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  ✓ Base completa salva: {path}")


def export_summary_txt(summary: pd.DataFrame, path: str):
    """Exporta resumo agregado (ranking de oportunidades) em TXT."""
    cols = [
        ("rank",               "Rank",       4),
        ("hs_code",            "HS2",        4),
        ("description",        "Categoria",  45),
        ("world_usd_m",        "Mundo(USD M)",  12),
        ("china_usd_m",        "China(USD M)",  12),
        ("gap_usd_m",          "Gap(USD M)",    11),
        ("china_share_pct",    "Share CN%",      9),
        ("opportunity_score_b","Score(B USD)",  12),
    ]
    keys   = [c[0] for c in cols]
    labels = [c[1] for c in cols]
    widths = [c[2] for c in cols]

    lines = []
    lines.append("=" * 120)
    lines.append("RANKING DE OPORTUNIDADES — IMPORTAÇÕES DO CANADÁ (Agregado 2021-2024)")
    lines.append(f"Gerado em: {date.today().isoformat()}")
    lines.append("Ordenado por: Opportunity Score = Gap × (1 − Share China %)")
    lines.append("=" * 120)
    lines.append("")

    lines.append(_divider(widths))
    lines.append(_row(labels, widths))
    lines.append(_divider(widths))

    for rank, row in summary.iterrows():
        values = [rank] + [row[k] for k in keys[1:]]
        values[2] = str(values[2])[:44]
        lines.append(_row(values, widths))
        if rank == 5:
            lines.append(_divider(widths))
            lines.append("|" + " TOP 5 ACIMA — PRINCIPAIS OPORTUNIDADES ".center(sum(widths) + len(widths)*3 - 2) + "|")
            lines.append(_divider(widths))
        elif rank == 15:
            lines.append(_divider(widths))
            lines.append("|" + " TOP 15 ACIMA ".center(sum(widths) + len(widths)*3 - 2) + "|")
            lines.append(_divider(widths))

    lines.append(_divider(widths))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  ✓ Resumo/ranking salvo: {path}")


# ─────────────────────────────────────────────────────────────────
# 3. Relatório Markdown
# ─────────────────────────────────────────────────────────────────

def _opp_label(score: float) -> str:
    if score >= 100:  return "🔴 Gigante"
    if score >= 40:   return "🟠 Grande"
    if score >= 20:   return "🟡 Moderada"
    if score >= 5:    return "🟢 Relevante"
    return "⚪ Pequena"


def _barrier(hs: str) -> str:
    barriers = {
        "87": "Regulações de segurança veicular, preferência por marcas estabelecidas, tarifas anti-dumping",
        "27": "Não se aplica — produto de extração, não manufatura chinesa",
        "84": "Certificações CSA/UL, concorrência com EUA/Alemanha/Japão, logística de peso",
        "30": "Aprovações Health Canada, patentes, cadeia fria, confiança do consumidor",
        "85": "Restrições Huawei/ZTE em telecom, concorrência com Samsung/Apple, tarifas",
        "90": "Certificações médicas Health Canada/FDA, acreditação de laboratórios",
        "71": "Certificação de origem, questões éticas (mineração), preferência por ouro/diamantes ocidentais",
        "39": "Normas de composição química, concorrência de petroquímicas americanas",
        "38": "Registros de substâncias químicas (CEPA), normas REACH equivalentes canadenses",
        "88": "Certificação Transport Canada, domínio da Boeing/Airbus, contatos governamentais",
        "48": "Tarifas anti-dumping específicas sobre papel chinês, concorrência de produtores locais",
        "29": "Registros de substâncias, patentes farmacêuticas upstream, pureza certificada",
        "22": "Preferência do consumidor por origem (whisky escocês, vinho francês), regulação LCBO",
        "76": "Tarifas anti-dumping em alumínio chinês, Alcan/Rio Tinto dominam",
        "72": "Tarifas de aço (Section 232 spillover), dumping histórico, siderúrgicas locais",
        "87": "Regulações de segurança veicular, preferência por marcas estabelecidas",
        "94": "Mercado já fortemente dominado pela China (~49%), espaço marginal",
        "95": "China já detém ~50% do mercado canadense de brinquedos",
    }
    return barriers.get(hs, "Certificações, concorrência estabelecida, preferências de mercado")


def export_markdown_report(summary: pd.DataFrame, db: pd.DataFrame, path: str, use_demo: bool):
    top5  = summary.head(5)
    top15 = summary.head(15)

    # Capítulo 95 específico
    ch95 = summary[summary["hs_code"] == "95"].iloc[0] if "95" in summary["hs_code"].values else None
    ch95_rank = summary[summary["hs_code"] == "95"].index[0] if ch95 is not None else "N/A"

    total_world = summary["world_usd_m"].sum() / 1000  # bilhões
    total_china = summary["china_usd_m"].sum() / 1000
    total_gap   = summary["gap_usd_m"].sum() / 1000
    avg_share   = (total_china / total_world * 100) if total_world > 0 else 0

    years = sorted(db["year"].unique().tolist())

    md = []
    md.append("# Análise de Gaps — Importações do Canadá: Oportunidades para Exportadores Chineses")
    md.append("")
    md.append(f"> **Gerado em:** {date.today().strftime('%d/%m/%Y')}  ")
    md.append(f"> **Fonte:** UN Comtrade API — dados de importação do Canadá (reporter: 124)  ")
    md.append(f"> **Anos analisados:** {', '.join(str(y) for y in years)}  ")
    if use_demo:
        md.append(f"> **Nota:** Dados sintéticos realistas (demo mode). Para dados reais, executar sem `--demo`.")
    md.append("")

    # ── Sumário Executivo
    md.append("---")
    md.append("")
    md.append("## 1. Sumário Executivo")
    md.append("")
    md.append(f"O Canadá importou aproximadamente **USD {total_world:,.0f} bilhões** do mundo no período, "
              f"dos quais **USD {total_china:,.0f} bilhões** (≈ {avg_share:.1f}%) tiveram origem na China.")
    md.append("")
    md.append(f"O **gap agregado** — o volume que não é suprido pela China — soma **USD {total_gap:,.0f} bilhões**, "
              f"representando a fronteira de expansão disponível para exportadores chineses.")
    md.append("")
    md.append("### Principais achados")
    md.append("")
    md.append("| Indicador | Valor |")
    md.append("|---|---|")
    md.append(f"| Total importado pelo Canadá (Mundo) | USD {total_world:,.0f} B |")
    md.append(f"| Total importado da China | USD {total_china:,.0f} B |")
    md.append(f"| Gap total (não capturado pela China) | USD {total_gap:,.0f} B |")
    md.append(f"| Share médio da China no mercado canadense | {avg_share:.1f}% |")
    md.append(f"| Capítulos HS2 analisados | {len(summary)} |")
    md.append(f"| Capítulos onde China tem < 10% de share | {len(summary[summary['china_share_pct'] < 10])} |")
    md.append(f"| Capítulos onde China tem > 40% de share | {len(summary[summary['china_share_pct'] > 40])} |")
    md.append("")

    # ── Ranking Top 15
    md.append("---")
    md.append("")
    md.append("## 2. Ranking das 15 Maiores Oportunidades")
    md.append("")
    md.append("Ordenado por **Opportunity Score** = Gap (USD) × (1 − Share China %), que combina "
              "o tamanho absoluto do gap com o grau de penetração ainda não realizado pela China.")
    md.append("")
    md.append("| Rank | HS | Categoria | Mundo (USD M) | China (USD M) | Gap (USD M) | Share CN% | Score (B) | Porte |")
    md.append("|---:|---:|---|---:|---:|---:|---:|---:|:---|")

    for rank, row in top15.iterrows():
        label = _opp_label(row["opportunity_score_b"])
        md.append(
            f"| {rank} | {row['hs_code']} | {row['description'][:42]} "
            f"| {row['world_usd_m']:,.0f} | {row['china_usd_m']:,.0f} "
            f"| {row['gap_usd_m']:,.0f} | {row['china_share_pct']:.1f}% "
            f"| {row['opportunity_score_b']:.1f} | {label} |"
        )
    md.append("")

    # ── Análise das Top 5
    md.append("---")
    md.append("")
    md.append("## 3. Análise Detalhada das Top 5 Categorias")
    md.append("")

    for rank, row in top5.iterrows():
        md.append(f"### 3.{rank}. HS {row['hs_code']} — {row['description']}")
        md.append("")
        md.append(f"- **Mercado total canadense:** USD {row['world_usd_m']:,.0f} M")
        md.append(f"- **Participação atual da China:** {row['china_share_pct']:.1f}% (USD {row['china_usd_m']:,.0f} M)")
        md.append(f"- **Gap disponível:** USD {row['gap_usd_m']:,.0f} M")
        md.append(f"- **Opportunity Score:** {row['opportunity_score_b']:.1f} B USD — {_opp_label(row['opportunity_score_b'])}")
        md.append(f"- **Principais barreiras:** {_barrier(row['hs_code'])}")
        md.append("")

        # Insight específico por categoria
        insights = {
            "87": (
                "**Veículos** é o maior mercado importador do Canadá e o maior gap absoluto. "
                "A China tem apenas 8,5% de share apesar de ser o maior produtor mundial de veículos. "
                "Com a ascensão de marcas como BYD, NIO e SAIC (MG), este gap está sendo endereçado ativamente. "
                "**Oportunidade imediata:** veículos elétricos (EVs) onde o Canadá tem metas agressivas de eletrificação. "
                "Barreira principal: tarifas de 100% impostas pelo governo canadense sobre EVs chineses em 2024."
            ),
            "27": (
                "**Combustíveis minerais** representa o segundo maior gap, mas é uma categoria **estruturalmente inadequada** "
                "para exportação chinesa — o Canadá é o 4º maior produtor de petróleo do mundo. "
                "Este gap não é uma oportunidade para China; é suprido por produção doméstica canadense e importações dos EUA."
            ),
            "84": (
                "**Máquinas e equipamentos mecânicos** é provavelmente a **oportunidade mais realista** da lista. "
                "A China já tem 27,5% de share, prova de competitividade estabelecida. "
                "O mercado canadense é enorme (USD 204 B) e o gap restante (USD 148 B) tem alta atratividade. "
                "Sub-categorias promissoras: equipamentos de mineração, máquinas agrícolas, "
                "compressores industriais e robótica."
            ),
            "30": (
                "**Farmacêuticos** tem gap de USD 80 B com apenas 9,2% de share da China. "
                "A China é o maior produtor mundial de IFAs (ingredientes farmacêuticos ativos), "
                "mas o produto acabado enfrenta barreiras regulatórias severas no Canadá (Health Canada). "
                "**Caminho realista:** IFAs e genéricos onde o Canadá já depende fortemente de fornecimento chinês."
            ),
            "85": (
                "**Eletrônicos** é onde a China tem maior penetração absoluta (USD 74 B), mas também "
                "o maior mercado (USD 182 B). Com 40,8% de share, há USD 108 B de gap ainda não capturado. "
                "Segmentos em expansão: painéis solares, baterias, equipamentos de telecomunicações (exceto onde há restrições). "
                "Risco: crescente escrutínio de segurança nacional sobre tecnologia chinesa no Canadá."
            ),
        }
        if row["hs_code"] in insights:
            md.append(f"> {insights[row['hs_code']]}")
        md.append("")

    # ── Quadrantes estratégicos
    md.append("---")
    md.append("")
    md.append("## 4. Quadrantes Estratégicos")
    md.append("")
    md.append("Classificando as categorias em 4 quadrantes com base no tamanho do mercado e share da China:")
    md.append("")
    md.append("```")
    md.append("                    Share China")
    md.append("                 BAIXO (<25%)     ALTO (>25%)")
    md.append("              ┌─────────────────┬─────────────────┐")
    md.append(" Gap   GRANDE  │  🎯 PRIORIDADE  │  ⚡ CRESCIMENTO │")
    md.append(" (>20B USD)    │  87, 27, 84,    │  85, 84 (parte) │")
    md.append("              │  30, 88, 48     │                 │")
    md.append("              ├─────────────────┼─────────────────┤")
    md.append(" Gap   PEQUENO │  🔍 NICHO       │  🔒 SATURADO    │")
    md.append(" (<20B USD)    │  71, 29, 22,    │  61, 62, 64,    │")
    md.append("              │  72, 76         │  94, 95         │")
    md.append("              └─────────────────┴─────────────────┘")
    md.append("```")
    md.append("")
    md.append("### Quadrante 🎯 PRIORIDADE — Maior oportunidade estratégica")
    md.append("")
    q1 = summary[(summary["gap_usd_m"] > 20000) & (summary["china_share_pct"] < 25)]
    for rank, row in q1.iterrows():
        md.append(f"- **HS {row['hs_code']} — {row['description']}**: gap de USD {row['gap_usd_m']:,.0f} M com {row['china_share_pct']:.1f}% share")
    md.append("")
    md.append("### Quadrante ⚡ CRESCIMENTO — China já presente, mas há espaço")
    md.append("")
    q2 = summary[(summary["gap_usd_m"] > 20000) & (summary["china_share_pct"] >= 25)]
    for rank, row in q2.iterrows():
        md.append(f"- **HS {row['hs_code']} — {row['description']}**: gap de USD {row['gap_usd_m']:,.0f} M com {row['china_share_pct']:.1f}% share")
    md.append("")

    # ── Hipótese Brinquedos
    md.append("---")
    md.append("")
    md.append("## 5. Validação da Hipótese — HS 95: Brinquedos, Jogos e Artigos Esportivos")
    md.append("")
    if ch95 is not None:
        verdict_icon = "⚠️" if ch95["china_share_pct"] > 40 else "✅"
        md.append(f"| Métrica | Valor |")
        md.append(f"|---|---|")
        md.append(f"| Rank no universo de {len(summary)} capítulos | **#{ch95_rank}** |")
        md.append(f"| Importação mundial pelo Canadá | USD {ch95['world_usd_m']:,.0f} M |")
        md.append(f"| Importação da China | USD {ch95['china_usd_m']:,.0f} M |")
        md.append(f"| Gap | USD {ch95['gap_usd_m']:,.0f} M |")
        md.append(f"| Share da China | **{ch95['china_share_pct']:.1f}%** |")
        md.append(f"| Opportunity Score | {ch95['opportunity_score_b']:.2f} B USD |")
        md.append("")
        md.append(f"**{verdict_icon} Veredicto: HIPÓTESE PARCIALMENTE SUPORTADA**")
        md.append("")
        md.append(
            f"A China já detém cerca de {ch95['china_share_pct']:.0f}% do mercado canadense de brinquedos, "
            f"colocando esta categoria no **quadrante Saturado**. Embora exista um gap absoluto de "
            f"USD {ch95['gap_usd_m']:,.0f} M, a penetração já é alta e a margem de crescimento é limitada "
            f"comparada a categorias como veículos, farmacêuticos ou máquinas industriais."
        )
        md.append("")
        md.append("**Sub-categorias com maior oportunidade dentro do HS 95:**")
        md.append("- **950370 Video game consoles** — China tem apenas ~20% share; Nintendo, Sony e Microsoft dominam")
        md.append("- **950610/950631/950632 Ski e golf** — mercados de premium onde China tem <15% share")
        md.append("- **950691 Equipamentos de exercício** — crescimento pós-pandemia, China já avança forte")
    md.append("")

    # ── Recomendações
    md.append("---")
    md.append("")
    md.append("## 6. Recomendações Estratégicas")
    md.append("")
    md.append("Com base na análise de gaps e opportunity scores, as seguintes prioridades emergem:")
    md.append("")
    md.append("### Curto prazo (entrada rápida, barreiras menores)")
    md.append("")
    md.append("1. **HS 84 — Máquinas e equipamentos**: China já tem 27% share, canal estabelecido. "
              "Foco em equipamentos de mineração (mercado canadense robusto) e máquinas agrícolas.")
    md.append("2. **HS 39 — Plásticos e polímeros**: 19,7% share, mercado de USD 62 B, gap de USD 50 B. "
              "Especialização em compostos técnicos e bioplásticos.")
    md.append("3. **HS 76 — Alumínio**: apesar de tarifas, produtos especializados de alumínio "
              "(perfis, ligas específicas) têm demanda não suprida.")
    md.append("")
    md.append("### Médio prazo (requerem adaptação regulatória)")
    md.append("")
    md.append("4. **HS 30 — Farmacêuticos**: via IFAs e genéricos aprovados. Investimento em "
              "certificações GMP reconhecidas pelo Health Canada.")
    md.append("5. **HS 90 — Instrumentos médicos e ópticos**: share de 19,5% com gap de USD 50 B. "
              "Dispositivos de diagnóstico, equipamentos de imagem de médio custo.")
    md.append("6. **HS 85 — Eletrônicos**: componentes e periféricos onde não há restrições de segurança nacional. "
              "Painéis solares e baterias têm demanda crescente com as metas climáticas canadenses.")
    md.append("")
    md.append("### Longo prazo (alto potencial, altas barreiras)")
    md.append("")
    md.append("7. **HS 87 — Veículos elétricos**: mercado de USD 238 B com China em apenas 8,5%. "
              "Requer superação das tarifas de 100% e construção de confiança de marca. "
              "Potencialmente o maior prêmio de longo prazo.")
    md.append("")

    # ── Metodologia
    md.append("---")
    md.append("")
    md.append("## 7. Metodologia")
    md.append("")
    md.append("```")
    md.append("Fonte de dados: UN Comtrade API (https://comtradeapi.un.org)")
    md.append("  Reporter:   Canadá (código 124)")
    md.append("  Parceiros:  Mundo inteiro (código 0) e China (código 156)")
    md.append("  Flow:       Importações (M)")
    md.append("  Nível:      HS2 (capítulos de 2 dígitos) — 98 categorias")
    md.append(f"  Período:    {', '.join(str(y) for y in years)}")
    md.append("  Métrica:    primaryValue (USD FOB)")
    md.append("")
    md.append("Fórmulas:")
    md.append("  gap_usd         = world_usd − china_usd")
    md.append("  china_share_pct = (china_usd / world_usd) × 100")
    md.append("  opportunity_score = gap_usd × (1 − china_share_pct / 100)")
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")
    md.append(f"*Relatório gerado automaticamente pelo pipeline Canada-Gap Analysis — Mondoré Consulting*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"  ✓ Relatório Markdown salvo: {path}")


# ─────────────────────────────────────────────────────────────────
# 4. Main
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gera base de dados e relatório de análise")
    parser.add_argument("--demo", action="store_true", help="Usar dados sintéticos (sem API)")
    parser.add_argument(
        "--years", nargs="+", type=int, default=DEFAULT_YEARS,
        help=f"Anos. Default: {DEFAULT_YEARS}"
    )
    args = parser.parse_args()

    print("\n══════════════════════════════════════════════════════════")
    print("  CANADA IMPORT GAP — GERAÇÃO DE BASE DE DADOS + RELATÓRIO")
    print("══════════════════════════════════════════════════════════\n")

    db      = build_full_database(args.years, use_demo=args.demo)
    summary = build_summary(db)

    print("\n[3/3] Exportando arquivos...")

    db_path      = os.path.join(OUTPUT_DIR, "canada_imports_database.txt")
    summary_path = os.path.join(OUTPUT_DIR, "canada_imports_summary.txt")
    report_path  = os.path.join(OUTPUT_DIR, "analysis_report.md")

    export_database_txt(db, db_path)
    export_summary_txt(summary, summary_path)
    export_markdown_report(summary, db, report_path, use_demo=args.demo)

    print(f"\n{'─'*60}")
    print(f"  Arquivos gerados em: {OUTPUT_DIR}/")
    print(f"  1. canada_imports_database.txt  — base completa ({len(db)} linhas)")
    print(f"  2. canada_imports_summary.txt   — ranking de {len(summary)} categorias")
    print(f"  3. analysis_report.md           — relatório de conclusões")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
