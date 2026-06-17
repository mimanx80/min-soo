import glob
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="마케팅 대시보드", layout="wide", initial_sidebar_state="expanded")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CH_DIR   = os.path.join(BASE_DIR, "data", "raw", "channel")
AF_DIR   = os.path.join(BASE_DIR, "data", "raw", "appsflyer")
BZ_DIR   = os.path.join(BASE_DIR, "data", "raw", "braze")

JOIN_KEYS       = ["일", "캠페인", "그룹", "소재"]
COMPARE_METRICS = ["클릭", "회원가입", "구매", "구매매출"]
IS_LOCAL        = os.path.isdir(CH_DIR)

# 퍼널 순서 (지표 계층)
FUNNEL_ORDER = ["노출", "클릭_ch", "클릭_af", "회원가입_ch", "구매_ch", "구매_af", "구매매출_ch", "구매매출_af"]


# ── 유틸 ──────────────────────────────────────────────────────

def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    if "일" in df.columns:
        df["일"] = pd.to_datetime(df["일"])
    return df


def get_col(df: pd.DataFrame, name: str, src: str) -> str:
    c = f"{name}_{src}"
    return c if c in df.columns else name


def safe_sum(df: pd.DataFrame, col: str) -> float:
    return float(df[col].sum()) if col in df.columns else 0.0


def kpi_row(df: pd.DataFrame) -> None:
    """채널·캠페인·그룹 공통 KPI 메트릭 행 — 퍼널 계층 순서로 표시"""
    cost  = safe_sum(df, "비용")
    imp   = safe_sum(df, "노출")
    ck_ch = safe_sum(df, get_col(df, "클릭", "ch"))
    ck_af = safe_sum(df, get_col(df, "클릭", "af"))
    pu_ch = safe_sum(df, get_col(df, "구매", "ch"))
    pu_af = safe_sum(df, get_col(df, "구매", "af"))
    rv_ch = safe_sum(df, get_col(df, "구매매출", "ch"))
    rv_af = safe_sum(df, get_col(df, "구매매출", "af"))

    ctr      = ck_ch / imp   * 100 if imp   else 0
    cvr_ch   = pu_ch / ck_ch * 100 if ck_ch else 0
    roas_ch  = rv_ch / cost  * 100 if cost  else 0
    roas_af  = rv_af / cost  * 100 if cost  else 0
    cpa_ch   = cost  / pu_ch        if pu_ch else 0
    cpa_af   = cost  / pu_af        if pu_af else 0

    k = st.columns(8)
    k[0].metric("비용",         f"₩{cost:,.0f}")
    k[1].metric("노출",         f"{imp:,.0f}")
    k[2].metric("클릭 CH",      f"{ck_ch:,.0f}",  f"CTR {ctr:.2f}%")
    k[3].metric("클릭 AF",      f"{ck_af:,.0f}",  f"vs CH {ck_af/ck_ch*100:.0f}%" if ck_ch else None)
    k[4].metric("구매 CH",      f"{pu_ch:,.0f}",  f"CVR {cvr_ch:.1f}%")
    k[5].metric("구매 AF",      f"{pu_af:,.0f}",  f"vs CH {pu_af/pu_ch*100:.0f}%" if pu_ch else None)
    k[6].metric("ROAS CH / AF", f"{roas_ch:.0f}% / {roas_af:.0f}%")
    k[7].metric("CPA CH / AF",  f"₩{cpa_ch:,.0f} / ₩{cpa_af:,.0f}")


def agg_metrics(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """공통 집계 — 비용/노출/클릭/전환/매출 + 파생 KPI"""
    agg_map: dict = {}
    for col in ["비용", "노출"]:
        if col in df.columns:
            agg_map[col] = (col, "sum")
    for m in COMPARE_METRICS:
        for src in ("ch", "af"):
            c = get_col(df, m, src)
            if c in df.columns:
                agg_map[f"{m}_{src}"] = (c, "sum")

    result = df.groupby(by).agg(**agg_map).reset_index()

    cost_s  = result.get("비용",        pd.Series(0, index=result.index))
    imp_s   = result.get("노출",        pd.Series(0, index=result.index))
    ck_ch_s = result.get("클릭_ch",     pd.Series(0, index=result.index))
    pu_ch_s = result.get("구매_ch",     pd.Series(0, index=result.index))
    pu_af_s = result.get("구매_af",     pd.Series(0, index=result.index))
    rv_ch_s = result.get("구매매출_ch", pd.Series(0, index=result.index))
    rv_af_s = result.get("구매매출_af", pd.Series(0, index=result.index))

    result["CTR"]     = ck_ch_s / imp_s.replace(0, pd.NA)   * 100
    result["CVR_ch"]  = pu_ch_s / ck_ch_s.replace(0, pd.NA) * 100
    result["ROAS_ch"] = rv_ch_s / cost_s.replace(0, pd.NA)  * 100
    result["ROAS_af"] = rv_af_s / cost_s.replace(0, pd.NA)  * 100
    result["CPA_ch"]  = cost_s  / pu_ch_s.replace(0, pd.NA)
    result["CPA_af"]  = cost_s  / pu_af_s.replace(0, pd.NA)
    return result


def bar_compare(data: pd.DataFrame, x: str, metric_ch: str, metric_af: str,
                title: str, yformat: str = "") -> go.Figure:
    """CH vs AF 그룹 바차트"""
    fig = go.Figure()
    if metric_ch in data.columns:
        fig.add_trace(go.Bar(name=f"{metric_ch.split('_')[0]} CH",
                             x=data[x], y=data[metric_ch],
                             marker_color="#00CC96"))
    if metric_af in data.columns:
        fig.add_trace(go.Bar(name=f"{metric_af.split('_')[0]} AF",
                             x=data[x], y=data[metric_af],
                             marker_color="#FFA15A", opacity=0.8))
    fig.update_layout(barmode="group", title=title,
                      yaxis_tickformat=yformat, height=360)
    return fig


def funnel_chart(df: pd.DataFrame, label: str) -> go.Figure:
    """퍼널 시각화 (노출→클릭→구매→매출)"""
    steps = [
        ("노출",       safe_sum(df, "노출")),
        ("클릭 CH",    safe_sum(df, get_col(df, "클릭", "ch"))),
        ("클릭 AF",    safe_sum(df, get_col(df, "클릭", "af"))),
        ("구매 CH",    safe_sum(df, get_col(df, "구매", "ch"))),
        ("구매 AF",    safe_sum(df, get_col(df, "구매", "af"))),
    ]
    steps = [(n, v) for n, v in steps if v > 0]
    fig = go.Figure(go.Funnel(
        y=[n for n, _ in steps],
        x=[v for _, v in steps],
        textinfo="value+percent previous",
        marker_color=["#636EFA","#00CC96","#FFA15A","#19D3F3","#FF6692"],
    ))
    fig.update_layout(title=f"퍼널: {label}", height=350)
    return fig


# ── 데이터 로드 ────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_from_folder() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    ch_files = sorted(glob.glob(os.path.join(CH_DIR, "????-??-??.csv")))
    af_files = sorted(glob.glob(os.path.join(AF_DIR, "????-??-??.csv")))
    ch = parse_dates(pd.concat([pd.read_csv(f) for f in ch_files], ignore_index=True)) if ch_files else pd.DataFrame()
    af = parse_dates(pd.concat([pd.read_csv(f) for f in af_files], ignore_index=True)) if af_files else pd.DataFrame()

    pur_files = glob.glob(os.path.join(BZ_DIR, "purchases_*.csv"))
    purchases = pd.concat([pd.read_csv(f) for f in pur_files], ignore_index=True) if pur_files else pd.DataFrame()
    if not purchases.empty and "purchase_at" in purchases.columns:
        purchases["purchase_at"] = pd.to_datetime(purchases["purchase_at"])

    usr_files = sorted(glob.glob(os.path.join(BZ_DIR, "users_*.csv")))
    users = pd.read_csv(usr_files[-1]) if usr_files else pd.DataFrame()

    cmp_files = glob.glob(os.path.join(BZ_DIR, "campaigns", "*.csv"))
    campaigns = pd.concat([pd.read_csv(f) for f in cmp_files], ignore_index=True) if cmp_files else pd.DataFrame()
    if not campaigns.empty and "sent_at" in campaigns.columns:
        campaigns["sent_at"] = pd.to_datetime(campaigns["sent_at"])

    return ch, af, {"purchases": purchases, "users": users, "campaigns": campaigns}


def build_joined(ch: pd.DataFrame, af: pd.DataFrame) -> pd.DataFrame:
    if ch.empty and af.empty:
        return pd.DataFrame()
    if ch.empty:
        return af.copy()
    if af.empty:
        return ch.copy()

    af_keep = list(dict.fromkeys(
        JOIN_KEYS + ["미디어소스"] + [c for c in COMPARE_METRICS if c in af.columns]
    ))
    merged = pd.merge(ch, af[af_keep], on=JOIN_KEYS, how="left", suffixes=("_ch", "_af"))
    for m in COMPARE_METRICS:
        if f"{m}_ch" not in merged.columns and m in merged.columns:
            merged.rename(columns={m: f"{m}_ch"}, inplace=True)
        if f"{m}_af" not in merged.columns:
            merged[f"{m}_af"] = pd.NA
    return merged


# ── 사이드바: 데이터 소스 ─────────────────────────────────────

st.sidebar.header("📂 데이터")

if IS_LOCAL:
    ch_raw, af_raw, braze = load_from_folder()
    n_ch = len(glob.glob(os.path.join(CH_DIR, "????-??-??.csv")))
    n_af = len(glob.glob(os.path.join(AF_DIR, "????-??-??.csv")))
    st.sidebar.success(f"로컬 폴더 연결\n채널 {n_ch}일 | AF {n_af}일")
    if st.sidebar.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
else:
    st.sidebar.caption("CSV 파일을 업로드하세요.")
    up_ch = st.sidebar.file_uploader("채널 CSV", type="csv", accept_multiple_files=True)
    up_af = st.sidebar.file_uploader("AppsFlyer CSV", type="csv", accept_multiple_files=True)
    ch_raw = parse_dates(pd.concat([pd.read_csv(f) for f in up_ch], ignore_index=True)) if up_ch else pd.DataFrame()
    af_raw = parse_dates(pd.concat([pd.read_csv(f) for f in up_af], ignore_index=True)) if up_af else pd.DataFrame()
    with st.sidebar.expander("Braze 데이터 (선택)"):
        up_pur = st.file_uploader("purchases CSV", type="csv", accept_multiple_files=True, key="pur")
        up_usr = st.file_uploader("users CSV", type="csv", key="usr")
        up_cmp = st.file_uploader("campaigns CSV", type="csv", accept_multiple_files=True, key="cmp")
    purchases = parse_dates(pd.concat([pd.read_csv(f) for f in up_pur], ignore_index=True)) if up_pur else pd.DataFrame()
    users     = pd.read_csv(up_usr) if up_usr else pd.DataFrame()
    campaigns = parse_dates(pd.concat([pd.read_csv(f) for f in up_cmp], ignore_index=True)) if up_cmp else pd.DataFrame()
    braze     = {"purchases": purchases, "users": users, "campaigns": campaigns}
    n_ch, n_af = len(up_ch or []), len(up_af or [])

if ch_raw.empty and af_raw.empty:
    st.title("📊 마케팅 퍼포먼스 대시보드")
    if IS_LOCAL:
        st.error("data/raw/channel/ 과 data/raw/appsflyer/ 에 YYYY-MM-DD.csv 파일을 넣어주세요.")
    else:
        st.info("👈 사이드바에서 채널·AppsFlyer CSV 파일을 업로드하세요.")
    st.stop()

df = build_joined(ch_raw, af_raw)

# ── 사이드바: 공통 날짜 필터만 ───────────────────────────────

st.sidebar.divider()
st.sidebar.header("📅 기간 필터")

dates = sorted(df["일"].dt.date.unique())
date_range = st.sidebar.date_input(
    "기간", value=(dates[0], dates[-1]), min_value=dates[0], max_value=dates[-1]
)

date_mask = (df["일"].dt.date >= date_range[0]) & (df["일"].dt.date <= date_range[-1])
base = df[date_mask].copy()   # 날짜만 필터된 베이스 — 각 탭이 자체 필터 추가

st.sidebar.caption(f"선택 기간: {date_range[0]} ~ {date_range[-1]}\n{len(base):,}행")


# ── 헤더 ──────────────────────────────────────────────────────

st.title("📊 마케팅 퍼포먼스 대시보드")
st.caption("노출·비용 = 채널(CH) 기준 | 클릭·전환·매출 = CH(채널 어트리뷰션) vs AF(MMP 어트리뷰션) 비교")

# 전체 KPI
kpi_row(base)
st.divider()


# ── 탭 ────────────────────────────────────────────────────────

tab_ch, tab_cmp, tab_grp, tab_cr, tab_trend, tab_braze, tab_raw = st.tabs([
    "📡 채널",
    "🎯 캠페인",
    "👥 그룹(타겟)",
    "🖼️ 소재",
    "📈 일별 트렌드",
    "💬 Braze CRM",
    "🗂️ 원본",
])


# ══════════════════════════════════════════════════════════════
# 탭 1: 채널 뷰
# ══════════════════════════════════════════════════════════════

with tab_ch:
    st.subheader("채널별 성과 비교")
    st.caption("분석 단위: 채널 | 지표 계층: 비용 → 노출 → 클릭 → 전환 → 매출")

    if "채널" not in base.columns:
        st.info("채널 컬럼 없음")
    else:
        ch_agg = agg_metrics(base, ["채널"])

        # KPI 테이블
        fmt = {
            "비용": "{:,.0f}", "노출": "{:,.0f}",
            "클릭_ch": "{:,.0f}", "클릭_af": "{:,.0f}",
            "구매_ch": "{:,.0f}", "구매_af": "{:,.0f}",
            "구매매출_ch": "{:,.0f}", "구매매출_af": "{:,.0f}",
            "CTR": "{:.2f}%", "CVR_ch": "{:.2f}%",
            "ROAS_ch": "{:.1f}%", "ROAS_af": "{:.1f}%",
            "CPA_ch": "{:,.0f}", "CPA_af": "{:,.0f}",
        }
        show_cols = ["채널", "비용", "노출", "클릭_ch", "클릭_af",
                     "구매_ch", "구매_af", "ROAS_ch", "ROAS_af", "CPA_ch", "CPA_af",
                     "CTR", "CVR_ch"]
        st.dataframe(
            ch_agg[[c for c in show_cols if c in ch_agg.columns]]
                .style.format({k: v for k, v in fmt.items() if k in ch_agg.columns})
                .background_gradient(subset=["ROAS_ch"] if "ROAS_ch" in ch_agg.columns else [], cmap="RdYlGn"),
            use_container_width=True,
        )

        # 차트 3종
        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            fig = px.pie(ch_agg, names="채널", values="비용", title="비용 비중",
                         color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)
        with r1c2:
            fig = bar_compare(ch_agg, "채널", "ROAS_ch", "ROAS_af", "채널별 ROAS CH vs AF")
            fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="100%")
            st.plotly_chart(fig, use_container_width=True)
        with r1c3:
            fig = bar_compare(ch_agg, "채널", "CPA_ch", "CPA_af", "채널별 CPA CH vs AF")
            st.plotly_chart(fig, use_container_width=True)

        # 퍼널 (채널별)
        st.markdown("##### 채널별 퍼널")
        channels = ch_agg["채널"].tolist()
        fcols = st.columns(len(channels))
        for i, ch_name in enumerate(channels):
            with fcols[i]:
                ch_slice = base[base["채널"] == ch_name]
                st.plotly_chart(funnel_chart(ch_slice, ch_name), use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 탭 2: 캠페인 뷰
# ══════════════════════════════════════════════════════════════

with tab_cmp:
    st.subheader("캠페인별 성과")
    st.caption("분석 단위: 채널 > 캠페인 | 필터로 채널을 좁히면 캠페인 간 직접 비교 가능")

    # 이 탭 전용 필터
    cmp_ch_opts = sorted(base["채널"].dropna().unique()) if "채널" in base.columns else []
    sel_cmp_ch  = st.multiselect("채널 선택", cmp_ch_opts, default=cmp_ch_opts, key="cmp_ch")

    cmp_base = base[base["채널"].isin(sel_cmp_ch)] if sel_cmp_ch and "채널" in base.columns else base

    grp_by = [c for c in ["채널", "캠페인목적", "캠페인"] if c in cmp_base.columns]
    cmp_agg = agg_metrics(cmp_base, grp_by)

    # 버블차트: 비용 vs ROAS, 버블=구매수
    color_col = "채널" if "채널" in cmp_agg.columns else "캠페인"
    size_col  = "구매_ch" if "구매_ch" in cmp_agg.columns else None
    fig = px.scatter(
        cmp_agg, x="비용", y="ROAS_ch",
        size=size_col, color=color_col,
        hover_data=[c for c in ["캠페인", "캠페인목적", "ROAS_af", "CPA_ch", "CPA_af"] if c in cmp_agg.columns],
        title="캠페인: 비용 vs ROAS CH  (버블 크기 = 구매수 CH, hover = AF 지표)",
        height=420,
    )
    fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="ROAS 100%")
    st.plotly_chart(fig, use_container_width=True)

    # 목적별 ROAS 바차트
    if "캠페인목적" in cmp_agg.columns:
        goal_agg = agg_metrics(cmp_base, ["캠페인목적"])
        gc1, gc2 = st.columns(2)
        with gc1:
            fig2 = bar_compare(goal_agg, "캠페인목적", "ROAS_ch", "ROAS_af", "캠페인 목적별 ROAS")
            fig2.add_hline(y=100, line_dash="dot", line_color="gray")
            st.plotly_chart(fig2, use_container_width=True)
        with gc2:
            fig3 = bar_compare(goal_agg, "캠페인목적", "CPA_ch", "CPA_af", "캠페인 목적별 CPA")
            st.plotly_chart(fig3, use_container_width=True)

    # 상세 테이블
    fmt2 = {
        "비용": "{:,.0f}", "노출": "{:,.0f}",
        "클릭_ch": "{:,.0f}", "클릭_af": "{:,.0f}",
        "구매_ch": "{:,.0f}", "구매_af": "{:,.0f}",
        "구매매출_ch": "{:,.0f}", "구매매출_af": "{:,.0f}",
        "CTR": "{:.2f}%", "CVR_ch": "{:.2f}%",
        "ROAS_ch": "{:.1f}%", "ROAS_af": "{:.1f}%",
        "CPA_ch": "{:,.0f}", "CPA_af": "{:,.0f}",
    }
    st.dataframe(
        cmp_agg.sort_values("ROAS_ch", ascending=False)
               .style.format({k: v for k, v in fmt2.items() if k in cmp_agg.columns})
               .background_gradient(subset=["ROAS_ch"] if "ROAS_ch" in cmp_agg.columns else [], cmap="RdYlGn"),
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════
# 탭 3: 그룹(타겟) 뷰
# ══════════════════════════════════════════════════════════════

with tab_grp:
    st.subheader("그룹(타겟)별 성과")
    st.caption("분석 단위: 채널 > 캠페인 > 그룹 | 동일 캠페인 내 타겟 전략 비교")

    # 이 탭 전용 필터
    g_fc1, g_fc2 = st.columns(2)
    with g_fc1:
        grp_ch_opts = sorted(base["채널"].dropna().unique()) if "채널" in base.columns else []
        sel_grp_ch  = st.multiselect("채널", grp_ch_opts, default=grp_ch_opts, key="grp_ch")
    with g_fc2:
        grp_filtered = base[base["채널"].isin(sel_grp_ch)] if sel_grp_ch and "채널" in base.columns else base
        cmp_opts_g   = sorted(grp_filtered["캠페인"].dropna().unique()) if "캠페인" in grp_filtered.columns else []
        sel_grp_cmp  = st.multiselect("캠페인", cmp_opts_g, default=cmp_opts_g, key="grp_cmp")

    grp_base = grp_filtered[grp_filtered["캠페인"].isin(sel_grp_cmp)] if sel_grp_cmp and "캠페인" in grp_filtered.columns else grp_filtered

    grp_by2  = [c for c in ["채널", "캠페인", "그룹"] if c in grp_base.columns]
    grp_agg  = agg_metrics(grp_base, grp_by2)

    # 그룹별 ROAS + CPA
    gc1, gc2 = st.columns(2)
    with gc1:
        grp_only = agg_metrics(grp_base, ["그룹"]) if "그룹" in grp_base.columns else pd.DataFrame()
        if not grp_only.empty:
            fig = bar_compare(grp_only, "그룹", "ROAS_ch", "ROAS_af", "타겟 그룹별 ROAS CH vs AF")
            fig.add_hline(y=100, line_dash="dot", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
    with gc2:
        if not grp_only.empty:
            fig2 = bar_compare(grp_only, "그룹", "CPA_ch", "CPA_af", "타겟 그룹별 CPA CH vs AF")
            st.plotly_chart(fig2, use_container_width=True)

    # 채널 × 그룹 히트맵: ROAS_ch
    if "채널" in grp_agg.columns and "그룹" in grp_agg.columns and "ROAS_ch" in grp_agg.columns:
        st.markdown("##### 채널 × 그룹 ROAS 히트맵")
        pivot = grp_agg.pivot_table(index="그룹", columns="채널", values="ROAS_ch", aggfunc="mean")
        fig3 = px.imshow(
            pivot, text_auto=".0f", aspect="auto",
            color_continuous_scale="RdYlGn",
            title="채널 × 그룹 ROAS CH (%) — 녹색일수록 고효율",
        )
        st.plotly_chart(fig3, use_container_width=True)

    # 논타겟 vs 유사타겟 직접 비교 (동일 캠페인 내)
    if "그룹" in grp_agg.columns:
        ab_groups = grp_agg[grp_agg["그룹"].isin(["논타겟", "유사타겟"])]
        if not ab_groups.empty and "캠페인" in ab_groups.columns:
            st.markdown("##### 논타겟 vs 유사타겟 — 동일 캠페인 내 비교")
            fig4 = px.bar(
                ab_groups, x="캠페인", y="ROAS_ch", color="그룹",
                barmode="group", title="캠페인별 논타겟 vs 유사타겟 ROAS CH",
                color_discrete_map={"논타겟": "#636EFA", "유사타겟": "#EF553B"},
            )
            fig4.add_hline(y=100, line_dash="dot", line_color="gray")
            st.plotly_chart(fig4, use_container_width=True)

    st.dataframe(
        grp_agg.sort_values("ROAS_ch", ascending=False)
               .style.format({k: v for k, v in {
                   "비용": "{:,.0f}", "노출": "{:,.0f}",
                   "클릭_ch": "{:,.0f}", "구매_ch": "{:,.0f}", "구매_af": "{:,.0f}",
                   "CTR": "{:.2f}%", "CVR_ch": "{:.2f}%",
                   "ROAS_ch": "{:.1f}%", "ROAS_af": "{:.1f}%",
                   "CPA_ch": "{:,.0f}", "CPA_af": "{:,.0f}",
               }.items() if k in grp_agg.columns})
               .background_gradient(subset=["ROAS_ch"] if "ROAS_ch" in grp_agg.columns else [], cmap="RdYlGn"),
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════
# 탭 4: 소재 뷰
# ══════════════════════════════════════════════════════════════

with tab_cr:
    st.subheader("소재별 성과")
    st.caption("분석 단위: 채널 > 캠페인 > 그룹 > 소재 | 소재타입·AB 자동 파싱")

    cr_fc1, cr_fc2, cr_fc3 = st.columns(3)
    with cr_fc1:
        cr_ch_opts = sorted(base["채널"].dropna().unique()) if "채널" in base.columns else []
        sel_cr_ch  = st.multiselect("채널", cr_ch_opts, default=cr_ch_opts, key="cr_ch")
    with cr_fc2:
        cr_base0   = base[base["채널"].isin(sel_cr_ch)] if sel_cr_ch and "채널" in base.columns else base
        cr_cmp_opts = sorted(cr_base0["캠페인"].dropna().unique()) if "캠페인" in cr_base0.columns else []
        sel_cr_cmp  = st.multiselect("캠페인", cr_cmp_opts, default=cr_cmp_opts, key="cr_cmp")
    with cr_fc3:
        cr_base1   = cr_base0[cr_base0["캠페인"].isin(sel_cr_cmp)] if sel_cr_cmp and "캠페인" in cr_base0.columns else cr_base0
        cr_grp_opts = sorted(cr_base1["그룹"].dropna().unique()) if "그룹" in cr_base1.columns else []
        sel_cr_grp  = st.multiselect("그룹", cr_grp_opts, default=cr_grp_opts, key="cr_grp")

    cr_base = cr_base1[cr_base1["그룹"].isin(sel_cr_grp)] if sel_cr_grp and "그룹" in cr_base1.columns else cr_base1

    # 소재명 파싱
    cr_df = cr_base.copy()
    cr_df["소재타입"] = cr_df["소재"].str.split("_").str[0]
    cr_df["AB"]      = cr_df["소재"].apply(
        lambda x: next((p for p in str(x).split("_") if p in ("A", "B")), "단일")
    )

    cr_agg = agg_metrics(cr_df, ["소재", "소재타입", "AB"])

    top_n   = st.slider("TOP N", 5, 30, 15, key="cr_topn")
    rank_by = "ROAS_ch" if "ROAS_ch" in cr_agg.columns else "비용"
    top     = cr_agg.nlargest(top_n, rank_by)

    tc1, tc2 = st.columns([3, 1])
    with tc1:
        fig = go.Figure()
        fig.add_trace(go.Bar(y=top["소재"], x=top.get("구매매출_ch"), name="매출 CH",
                             orientation="h", marker_color="#00CC96"))
        if "구매매출_af" in top.columns:
            fig.add_trace(go.Bar(y=top["소재"], x=top["구매매출_af"], name="매출 AF",
                                 orientation="h", marker_color="#FFA15A", opacity=0.7))
        fig.update_layout(barmode="group", title=f"소재 TOP {top_n} (ROAS CH 기준)",
                          height=max(400, top_n * 30), xaxis_title="구매매출 (₩)")
        st.plotly_chart(fig, use_container_width=True)
    with tc2:
        type_agg = cr_agg.groupby("소재타입")["비용"].sum().reset_index()
        fig2 = px.pie(type_agg, names="소재타입", values="비용", title="소재타입별 비용",
                      color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig2, use_container_width=True)

    # AB 비교
    if st.checkbox("AB 테스트 상세 비교"):
        ab_agg = agg_metrics(cr_df[cr_df["AB"] != "단일"], ["소재타입", "AB"])
        if not ab_agg.empty:
            abc1, abc2 = st.columns(2)
            with abc1:
                fig3 = px.bar(ab_agg, x="소재타입", y="ROAS_ch", color="AB", barmode="group",
                               title="소재타입 × AB — ROAS CH")
                st.plotly_chart(fig3, use_container_width=True)
            with abc2:
                fig4 = px.bar(ab_agg, x="소재타입", y="CPA_ch", color="AB", barmode="group",
                               title="소재타입 × AB — CPA CH")
                st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 탭 5: 일별 트렌드
# ══════════════════════════════════════════════════════════════

with tab_trend:
    st.subheader("일별 트렌드")

    tr_ch_opts = sorted(base["채널"].dropna().unique()) if "채널" in base.columns else []
    sel_tr_ch  = st.multiselect("채널", tr_ch_opts, default=tr_ch_opts, key="tr_ch")
    tr_base    = base[base["채널"].isin(sel_tr_ch)] if sel_tr_ch and "채널" in base.columns else base

    daily = agg_metrics(tr_base, ["일"])

    t1, t2, t3, t4 = st.tabs(["비용 & 매출", "클릭 CH vs AF", "구매 CH vs AF", "ROAS CH vs AF"])

    with t1:
        plot_cols = [c for c in ["비용", "구매매출_ch", "구매매출_af"] if c in daily.columns]
        fig = px.bar(daily, x="일", y=plot_cols, barmode="group",
                     color_discrete_map={"비용": "#636EFA", "구매매출_ch": "#00CC96", "구매매출_af": "#FFA15A"},
                     labels={"value": "금액 (₩)", "variable": ""})
        st.plotly_chart(fig, use_container_width=True)
    with t2:
        fig = go.Figure()
        if "클릭_ch" in daily.columns:
            fig.add_trace(go.Scatter(x=daily["일"], y=daily["클릭_ch"], name="클릭 CH", mode="lines+markers"))
        if "클릭_af" in daily.columns:
            fig.add_trace(go.Scatter(x=daily["일"], y=daily["클릭_af"], name="클릭 AF", mode="lines+markers", line=dict(dash="dash")))
        st.plotly_chart(fig, use_container_width=True)
    with t3:
        fig = go.Figure()
        if "구매_ch" in daily.columns:
            fig.add_trace(go.Bar(x=daily["일"], y=daily["구매_ch"], name="구매 CH"))
        if "구매_af" in daily.columns:
            fig.add_trace(go.Bar(x=daily["일"], y=daily["구매_af"], name="구매 AF"))
        fig.update_layout(barmode="group")
        st.plotly_chart(fig, use_container_width=True)
    with t4:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily["일"], y=daily["ROAS_ch"], name="ROAS CH", mode="lines+markers"))
        fig.add_trace(go.Scatter(x=daily["일"], y=daily["ROAS_af"], name="ROAS AF", mode="lines+markers", line=dict(dash="dash")))
        fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="100%")
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 탭 6: Braze CRM
# ══════════════════════════════════════════════════════════════

with tab_braze:
    purchases = braze["purchases"]
    users     = braze["users"]
    campaigns = braze["campaigns"]

    if purchases.empty and users.empty and campaigns.empty:
        st.info("data/raw/braze/ 에 파일이 없거나 업로드되지 않았습니다.")
    else:
        bz1, bz2, bz3 = st.tabs(["구매 트랜잭션", "유저 세그먼트", "CRM 캠페인 AB"])

        with bz1:
            if not purchases.empty and "purchase_at" in purchases.columns:
                pur = purchases[(purchases["purchase_at"].dt.date >= date_range[0]) &
                                (purchases["purchase_at"].dt.date <= date_range[-1])]
                k1, k2, k3 = st.columns(3)
                k1.metric("구매건", f"{len(pur):,}")
                k2.metric("총 매출", f"₩{pur['amount'].sum():,.0f}")
                k3.metric("객단가", f"₩{pur['amount'].mean():,.0f}")
                daily_pur = pur.groupby(pur["purchase_at"].dt.date).agg(
                    건수=("order_id","count"), 매출=("amount","sum")
                ).reset_index()
                st.plotly_chart(px.bar(daily_pur, x="purchase_at", y="매출", title="Braze 일별 매출"), use_container_width=True)

        with bz2:
            if not users.empty and "_segment_truth" in users.columns:
                seg = users["_segment_truth"].value_counts().reset_index()
                seg.columns = ["세그먼트", "유저수"]
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.plotly_chart(px.pie(seg, names="세그먼트", values="유저수", title="유저 세그먼트"), use_container_width=True)
                with sc2:
                    if "attribution_source" in users.columns:
                        attr = users.groupby(["attribution_source","_segment_truth"]).size().reset_index(name="유저수")
                        st.plotly_chart(px.bar(attr, x="attribution_source", y="유저수",
                                               color="_segment_truth", barmode="stack",
                                               title="유입채널 × 세그먼트"), use_container_width=True)

        with bz3:
            if not campaigns.empty:
                cmp_mask = ((campaigns["sent_at"].dt.date >= date_range[0]) &
                            (campaigns["sent_at"].dt.date <= date_range[-1]))
                cmp = campaigns[cmp_mask]
                grp_bz = [c for c in ["canvas_name","variant","target_segment"] if c in cmp.columns]
                bz_agg = cmp.groupby(grp_bz).agg(
                    발송=("delivered","sum"), 오픈=("opened","sum"),
                    클릭=("clicked","sum"), 전환=("converted","sum"),
                    전환매출=("conversion_value","sum"),
                ).reset_index()
                bz_agg["전환율"] = bz_agg["전환"] / bz_agg["발송"].replace(0, pd.NA) * 100
                if "variant" in bz_agg.columns:
                    st.plotly_chart(px.bar(bz_agg, x="canvas_name", y="전환율", color="variant",
                                           barmode="group", title="CRM 캠페인 AB 전환율"), use_container_width=True)
                st.dataframe(bz_agg, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 탭 7: 원본 데이터
# ══════════════════════════════════════════════════════════════

with tab_raw:
    src = st.radio("소스", ["조인 데이터", "Channel 원본", "AppsFlyer 원본"], horizontal=True)
    if src == "조인 데이터":
        st.dataframe(base, use_container_width=True)
        st.caption(f"{len(base):,}행 (날짜 필터 적용)")
    elif src == "Channel 원본":
        st.dataframe(ch_raw, use_container_width=True)
        st.caption(f"{len(ch_raw):,}행")
    else:
        st.dataframe(af_raw, use_container_width=True)
        st.caption(f"{len(af_raw):,}행")
