"""
Streamlit Interactive Analytical Dashboard for SportsPulse Lakehouse.
Provides executive summaries, cross-sport comparisons, athlete deep-dives, and 250Hz ECG visualizations.
"""

from pathlib import Path

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="SportsPulse Lakehouse | Athlete Analytics",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "data/04_gold/sportspulse.duckdb"
GOLD_DIR = Path("data/04_gold")
BRONZE_DIR = Path("data/02_bronze")


@st.cache_resource
def get_duckdb_connection():
    return duckdb.connect(DB_PATH, read_only=True)


def run_query(query: str) -> pl.DataFrame:
    conn = get_duckdb_connection()
    return pl.from_arrow(conn.execute(query).arrow())


# Sidebar Navigation
st.sidebar.image("https://img.icons8.com/color/96/heart-with-pulse.png", width=64)
st.sidebar.title("🏃 SportsPulse")
st.sidebar.markdown("**Plataforma Lakehouse de Telemetria Cardiorrespiratória**")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Navegação:",
    [
        "📊 Visão Executiva & Modalidades",
        "🫀 Análise de Sessão & Atleta",
        "⚡ ECG de Alta Resolução (250Hz)",
        "🦆 Explorador SQL (DuckDB)",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Base de Dados**: SportDB (10 Esportes, 81 Atletas, 126 Sessões, 449k+ segundos de telemetria contínua)."
)

# -------------------------------------------------------------
# PAGE 1: Visão Executiva & Modalidades
# -------------------------------------------------------------
if menu == "📊 Visão Executiva & Modalidades":
    st.title("📊 Visão Executiva & Comparativo de Modalidades Esportivas")
    st.markdown(
        "Análise comparativa de esforço fisiológico, carga de treinamento (**TRIMP**) e variabilidade cardíaca (**HRV**) entre diferentes esportes."
    )

    # Top KPIs
    df_sessions = run_query("SELECT * FROM fact_training_session")
    df_athletes = run_query("SELECT * FROM dim_athlete")

    total_sessions = len(df_sessions)
    total_athletes = len(df_athletes)
    total_hours = round(df_sessions["duration_minutes"].sum() / 60.0, 1)
    avg_hr = round(df_sessions["hr_avg_bpm"].mean(), 1)
    peak_hr = df_sessions["hr_max_bpm"].max()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Modalidades", "10 Esportes")
    col2.metric("Total de Atletas", f"{total_athletes}")
    col3.metric("Sessões Gravadas", f"{total_sessions}")
    col4.metric("Horas de Telemetria", f"{total_hours} h")
    col5.metric("FC Média Global", f"{avg_hr} bpm")

    st.markdown("---")

    # Sports Summary Table and Charts
    df_summary = run_query("SELECT * FROM vw_sport_intensity_comparison")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("🔥 Carga Cardíaca Média (TRIMP Banister)")
        fig_trimp = px.bar(
            df_summary.to_pandas(),
            x="sport_name",
            y="avg_banister_trimp",
            color="avg_hr_bpm",
            color_continuous_scale="Reds",
            labels={
                "avg_banister_trimp": "TRIMP Médio (Pontos)",
                "sport_name": "Modalidade",
                "avg_hr_bpm": "FC Média (bpm)",
            },
            title="Intensidade Fisiológica Relativa por Modalidade",
        )
        fig_trimp.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_trimp, use_container_width=True)

    with c2:
        st.subheader("⏱️ Duração vs Frequência Cardíaca Média")
        fig_scatter = px.scatter(
            df_sessions.join(run_query("SELECT sport_code, sport_name FROM dim_sport"), on="sport_code").to_pandas(),
            x="duration_minutes",
            y="hr_avg_bpm",
            color="sport_name",
            size="banister_trimp",
            hover_data=["subject_id", "session_id", "hr_max_bpm"],
            labels={"duration_minutes": "Duração (min)", "hr_avg_bpm": "FC Média (bpm)", "sport_name": "Esporte"},
            title="Dispersão de Sessões: Duração vs Intensidade Cardíaca",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.subheader("📋 Tabela Comparativa de Biomarcadores")
    st.dataframe(df_summary.to_pandas(), use_container_width=True)

# -------------------------------------------------------------
# PAGE 2: Análise de Sessão & Atleta
# -------------------------------------------------------------
elif menu == "🫀 Análise de Sessão & Atleta":
    st.title("🫀 Análise Individual de Atleta & Telemetria por Fase")

    df_sports = run_query("SELECT sport_code, sport_name FROM dim_sport ORDER BY sport_name")
    sports_map = {row["sport_name"]: row["sport_code"] for row in df_sports.iter_rows(named=True)}

    c_sel1, c_sel2, c_sel3 = st.columns(3)
    with c_sel1:
        sel_sport_name = st.selectbox("Escolha a Modalidade:", list(sports_map.keys()))
        sel_sport_code = sports_map[sel_sport_name]

    with c_sel2:
        df_subjs = run_query(
            f"SELECT DISTINCT subject_id FROM fact_training_session WHERE sport_code = '{sel_sport_code}' ORDER BY subject_id"
        )
        subjs_list = df_subjs["subject_id"].to_list()
        sel_subject = st.selectbox("Escolha o Atleta (ID):", subjs_list)

    with c_sel3:
        df_sess = run_query(
            f"SELECT session_id, duration_minutes, banister_trimp FROM fact_training_session WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}' ORDER BY session_id"
        )
        sess_map = {
            f"{r['session_id']} ({r['duration_minutes']} min | TRIMP: {r['banister_trimp']})": r["session_id"]
            for r in df_sess.iter_rows(named=True)
        }
        sel_sess_label = st.selectbox("Escolha a Sessão (CRD):", list(sess_map.keys()))
        sel_session = sess_map[sel_sess_label]

    # Athlete Info Box
    ath_info = run_query(
        f"SELECT * FROM dim_athlete WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}'"
    )
    sess_info = run_query(
        f"SELECT * FROM fact_training_session WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}' AND session_id = '{sel_session}'"
    )

    if len(ath_info) > 0 and len(sess_info) > 0:
        a_row = ath_info.row(0, named=True)
        s_row = sess_info.row(0, named=True)

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Gênero", str(a_row["gender"]))
        k2.metric("Idade", f"{a_row['age_years']} anos" if a_row["age_years"] else "N/A")
        k3.metric("IMC", f"{a_row['bmi']}" if a_row["bmi"] else "N/A")
        k4.metric("FC Média / Pico", f"{s_row['hr_avg_bpm']} / {s_row['hr_max_bpm']} bpm")
        k5.metric("TRIMP Banister", f"{s_row['banister_trimp']}")
        k6.metric("HRV RMSSD", f"{s_row['rmssd_ms']} ms" if s_row["rmssd_ms"] else "N/A")

    st.markdown("---")

    # Time Series of Session (1Hz)
    st.subheader(f"📈 Série Temporal da Sessão: {sel_sport_code} - {sel_subject} - {sel_session}")

    df_telemetry_sess = run_query(f"""
        SELECT time_sec, phase_name, phase_category, hr_bpm, hr_bpm_smoothed_5s, br_rpm, rr_ms, hr_reserve_pct
        FROM fact_telemetry_1s
        WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}' AND session_id = '{sel_session}'
        ORDER BY time_sec
    """)

    if len(df_telemetry_sess) > 0:
        pdf_tel = df_telemetry_sess.to_pandas()

        # Dual-axis chart: HR & BR
        fig_dual = go.Figure()
        fig_dual.add_trace(
            go.Scatter(
                x=pdf_tel["time_sec"],
                y=pdf_tel["hr_bpm_smoothed_5s"],
                mode="lines",
                name="Frequência Cardíaca (bpm)",
                line=dict(color="#FF4B4B", width=2),
            )
        )
        fig_dual.add_trace(
            go.Scatter(
                x=pdf_tel["time_sec"],
                y=pdf_tel["br_rpm"],
                mode="lines",
                name="Taxa Respiratória (rpm)",
                yaxis="y2",
                line=dict(color="#00D4B2", width=1.5, dash="dot"),
            )
        )

        fig_dual.update_layout(
            title="Comportamento Cardiorrespiratório Contínuo (1 Hz)",
            xaxis=dict(title="Tempo (segundos)"),
            yaxis=dict(
                title="Frequência Cardíaca (bpm)", titlefont=dict(color="#FF4B4B"), tickfont=dict(color="#FF4B4B")
            ),
            yaxis2=dict(
                title="Taxa Respiratória (rpm)",
                titlefont=dict(color="#00D4B2"),
                tickfont=dict(color="#00D4B2"),
                overlaying="y",
                side="right",
            ),
            hovermode="x unified",
            legend=dict(x=0.01, y=0.99),
        )
        st.plotly_chart(fig_dual, use_container_width=True)

        # Phases breakdown
        df_phases_sess = run_query(f"""
            SELECT phase_name, phase_category, duration_minutes, hr_avg_bpm, hr_max_bpm, br_avg_rpm, phase_banister_trimp
            FROM fact_session_phases
            WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}' AND session_id = '{sel_session}'
        """)
        st.subheader("⏱️ Detalhamento das Fases do Protocolo de Treino")
        st.dataframe(df_phases_sess.to_pandas(), use_container_width=True)

# -------------------------------------------------------------
# PAGE 3: ECG de Alta Resolução (250Hz)
# -------------------------------------------------------------
elif menu == "⚡ ECG de Alta Resolução (250Hz)":
    st.title("⚡ Eletrocardiograma de Alta Resolução (250 Hz)")
    st.markdown("Visualizador de sinal bioelétrico bruto do ECG registrado a 250 amostras por segundo.")

    df_sports = run_query("SELECT sport_code, sport_name FROM dim_sport ORDER BY sport_name")
    sports_map = {row["sport_name"]: row["sport_code"] for row in df_sports.iter_rows(named=True)}

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_sport_name = st.selectbox("Modalidade:", list(sports_map.keys()), key="ecg_sport")
        sel_sport_code = sports_map[sel_sport_name]
    with c2:
        df_subjs = run_query(
            f"SELECT DISTINCT subject_id FROM fact_training_session WHERE sport_code = '{sel_sport_code}' ORDER BY subject_id"
        )
        sel_subject = st.selectbox("Atleta (ID):", df_subjs["subject_id"].to_list(), key="ecg_subj")
    with c3:
        df_sess = run_query(
            f"SELECT session_id FROM fact_training_session WHERE sport_code = '{sel_sport_code}' AND subject_id = '{sel_subject}' ORDER BY session_id"
        )
        sel_session = st.selectbox("Sessão (CRD):", df_sess["session_id"].to_list(), key="ecg_sess")

    ecg_file = BRONZE_DIR / "ecg_250hz" / f"sport={sel_sport_code}" / f"{sel_subject}_{sel_session}_ecg.parquet"

    if ecg_file.exists():
        st.success(f"Arquivo de ECG encontrado: `{ecg_file}`")
        df_ecg_full = pl.read_parquet(ecg_file)
        max_sec = int(df_ecg_full["time_sec"].max())

        c_time1, c_time2 = st.columns(2)
        with c_time1:
            start_window = st.slider("Janela de Início (segundos):", 0, max(0, max_sec - 10), 60)
        with c_time2:
            window_duration = st.slider("Duração da Janela (segundos):", 2, 20, 5)

        end_window = start_window + window_duration
        df_window = df_ecg_full.filter((pl.col("time_sec") >= start_window) & (pl.col("time_sec") <= end_window))

        fig_ecg = px.line(
            df_window.to_pandas(),
            x="time_sec",
            y="ecg_mv",
            labels={"time_sec": "Tempo (segundos)", "ecg_mv": "Sinal Bioelétrico ECG (mV)"},
            title=f"Traçado de ECG ({window_duration}s @ 250 Hz) - {sel_sport_code} {sel_subject} {sel_session}",
        )
        fig_ecg.update_traces(line=dict(color="#FF1744", width=1.5))
        st.plotly_chart(fig_ecg, use_container_width=True)
    else:
        st.warning("Arquivo de ECG individual não localizado nesta partição.")

# -------------------------------------------------------------
# PAGE 4: Explorador SQL DuckDB
# -------------------------------------------------------------
elif menu == "🦆 Explorador SQL (DuckDB)":
    st.title("🦆 Explorador SQL Lakehouse (DuckDB)")
    st.markdown("Execute consultas analíticas diretamente nas tabelas e views Gold do Lakehouse.")

    preset_queries = {
        "Ranking de Maiores Cargas de Treino (Top 10 TRIMP)": "SELECT * FROM vw_high_intensity_sessions LIMIT 10;",
        "Resumo de Intensidade por Modalidade": "SELECT * FROM vw_sport_intensity_comparison;",
        "Perfil Completo de Atletas": "SELECT * FROM vw_athlete_summary LIMIT 15;",
        "Amostra da Fato de Telemetria (1Hz)": "SELECT * FROM fact_telemetry_1s LIMIT 10;",
    }

    selected_preset = st.selectbox("Consultas Predefinidas:", list(preset_queries.keys()))
    sql_input = st.text_area("Editor SQL:", value=preset_queries[selected_preset], height=120)

    if st.button("Executar Consulta SQL 🚀"):
        try:
            df_res = run_query(sql_input)
            st.success(f"Consulta executada com sucesso! Retornou {len(df_res)} linhas.")
            st.dataframe(df_res.to_pandas(), use_container_width=True)
        except Exception as e:
            st.error(f"Erro na execução da consulta: {e}")
