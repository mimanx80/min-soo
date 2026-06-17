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


# ── 데이터 로드 ────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_from_folder() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """로컬 폴더에서 전체 데이터 로드"""
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
    if not users.empty and "signup_date" in users.columns:
        users["signup_date"] = pd.to_datetime(users["signup_date"])

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


# ── 사이드바: 파일 소스 + 필터 ───────────────────────────────

st.sidebar.header("📂 데이터")

if IS_LOCAL:
    # 로컬: 폴더 자동 읽기
    ch_raw, af_raw, braze = load_from_folder()
    n_ch = len(glob.glob(os.path.join(CH_DIR, "????-??-??.csv")))
    n_af = len(glob.glob(os.path.join(AF_DIR, "????-??-??.csv")))
    st.sidebar.success(f"로컬 폴더 연결됨\n채널 {n_ch}일 | AF {n_af}일")
    if st.sidebar.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
else:
    # 클라우드: 파일 업로드
    st.sidebar.caption("CSV 파일을 업로드하세요.")
    up_ch  = st.sidebar.file_uploader("채널 CSV (여러 날짜 동시 선택 가능)", type="csv", accept_multiple_files=True)
    up_af  = st.sidebar.file_uploader("AppsFlyer CSV", type="csv", accept_multiple_files=True)

    ch_raw = parse_dates(pd.concat([pd.read_csv(f) for f in up_ch], ignore_index=True)) if up_ch else pd.DataFrame()
    af_raw = parse_dates(pd.concat([pd.read_csv(f) for f in up_af], ignore_index=True)) if up_af else pd.DataFrame()

    with st.sidebar.expander("Braze 데이터 (선택)"):
        up_pur = st.file_uploader("purchases CSV", type="csv", accept_multiple_files=True, key="pur")
        up_usr = st.file_uploader("users CSV (최신 스냅샷)", type="csv", key="usr")
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
        st.info("👈 사이드바에서 채널·AppsFlyer CSV 파일을 업로드하세요.\n\n파일명 형식: `YYYY-MM-DD.csv`")
    st.stop()

df = build_joined(ch_raw, af_raw)

st.sidebar.divider()
st.sidebar.header("필터")

dates = sorted(df["일"].dt.date.unique())
date_range = st.sidebar.date_input("기간", value=(dates[0], dates[-1]), min_value=dates[0], max_value=dates[-1])

ch_opts  = sorted(df["채널"].dropna().unique()) if "채널" in df.columns else []
sel_ch   = st.sidebar.multiselect("채널", ch_opts, default=ch_opts)

cmp_opts = sorted(df["캠페인"].dropna().unique()) if "캠페인" in df.columns else []
sel_cmp  = st.sidebar.multiselect("캠페인", cmp_opts, default=cmp_opts)

grp_opts = sorted(df["그룹"].dropna().unique()) if "그룹" in df.columns else []
sel_grp  = st.sidebar.multiselect("그룹(타겟)", grp_opts, default=grp_opts)

st.sidebar.caption(f"채널 {n_ch}일 | AF {n_af}일 | Braze 유저 {len(braze['users']):,}명")

# ── 필터 적용 ──────────────────────────────────────────────────

mask = (df["일"].dt.date >= date_range[0]) & (df["일"].dt.date <= date_range[-1])
if sel_ch  and "채널"  in df.columns: mask &= df["채널"].isin(sel_ch)
if sel_cmp and "캠페인" in df.columns: mask &= df["캠페인"].isin(sel_cmp)
if sel_grp and "그룹"  in df.columns: mask &= df["그룹"].isin(sel_grp)
fdf = df[mask].copy()


# ── KPI 계산 ──────────────────────────────────────────────────

cost  = safe_sum(fdf, "비용")
imp   = safe_sum(fdf, "노출")
ck_ch = safe_sum(fdf, get_col(fdf, "클릭", "ch"))
ck_af = safe_sum(fdf, get_col(fdf, "클릭", "af"))
sg_ch = safe_sum(fdf, get_col(fdf, "회원가입", "ch"))
pu_ch = safe_sum(fdf, get_col(fdf, "구매", "ch"))
pu_af = safe_sum(fdf, get_col(fdf, "구매", "af"))
rv_ch = safe_sum(fdf, get_col(fdf, "구매매출", "ch"))
rv_af = safe_sum(fdf, get_col(fdf, "구매매출", "af"))

roas_ch = rv_ch / cost * 100 if cost else 0
roas_af = rv_af / cost * 100 if cost else 0
cpa_ch  = cost / pu_ch if pu_ch else 0
cpa_af  = cost / pu_af if pu_af else 0
ctr     = ck_ch / imp * 100 if imp else 0
cvr_ch  = pu_ch / ck_ch * 100 if ck_ch else 0


# ── 헤더 + KPI ────────────────────────────────────────────────

st.title("📊 마케팅 퍼포먼스 대시보드")
st.caption("노출·비용 = 채널(CH) 기준 | 클릭·전환·매출 = CH vs AppsFlyer(AF) 비교")

k = st.columns(6)
k[0].metric("총 비용",      f"₩{cost:,.0f}")
k[1].metric("노출",         f"{imp:,.0f}",        f"CTR {ctr:.2f}%")
k[2].metric("클릭 CH / AF", f"{ck_ch:,.0f} / {ck_af:,.0f}")
k[3].metric("구매 CH / AF", f"{pu_ch:,.0f} / {pu_af:,.0f}", f"CVR {cvr_ch:.1f}%")
k[4].metric("ROAS CH",      f"{roas_ch:.0f}%",    f"AF {roas_af:.0f}%")
k[5].metric("CPA CH",       f"₩{cpa_ch:,.0f}",   f"AF ₩{cpa_af:,.0f}")

st.divider()


# ── 탭 ────────────────────────────────────────────────────────

tab_trend, tab_channel, tab_campaign, tab_creative, tab_braze, tab_raw = st.tabs([
    "📈 일별 트렌드", "📡 채널 비교", "🎯 캠페인", "🖼️ 소재", "💬 Braze CRM", "🗂️ 원본 데이터"
])


# ── 탭1: 일별 트렌드 ──────────────────────────────────────────

with tab_trend:
    agg_map: dict = {"비용": ("비용", "sum"), "노출": ("노출", "sum")}
    for m in COMPARE_METRICS:
        for src in ("ch", "af"):
            c = get_col(fdf, m, src)
            if c in fdf.columns:
                agg_map[f"{m}_{src}"] = (c, "sum")

    daily = fdf.groupby("일").agg(**agg_map).reset_index()
    daily["ROAS_ch"] = daily.get("구매매출_ch", pd.Series(0, index=daily.index)) / daily["비용"].replace(0, pd.NA) * 100
    daily["ROAS_af"] = daily.get("구매매출_af", pd.Series(0, index=daily.index)) / daily["비용"].replace(0, pd.NA) * 100

    t1, t2, t3, t4 = st.tabs(["비용 & 매출", "클릭 CH vs AF", "구매 CH vs AF", "ROAS CH vs AF"])

    with t1:
        cols_plot = [c for c in ["비용", "구매매출_ch", "구매매출_af"] if c in daily.columns]
        fig = px.bar(daily, x="일", y=cols_plot, barmode="group",
                     color_discrete_map={"비용": "#636EFA", "구매매출_ch": "#00CC96", "구매매출_af": "#FFA15A"},
                     labels={"value": "금액 (₩)", "variable": ""})
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        fig = go.Figure()
        if "클릭_ch" in daily.columns:
            fig.add_trace(go.Scatter(x=daily["일"], y=daily["클릭_ch"], name="클릭 CH", mode="lines+markers"))
        if "클릭_af" in daily.columns:
            fig.add_trace(go.Scatter(x=daily["일"], y=daily["클릭_af"], name="클릭 AF", mode="lines+markers", line=dict(dash="dash")))
        fig.update_layout(yaxis_title="클릭수")
        st.plotly_chart(fig, use_container_width=True)

    with t3:
        fig = go.Figure()
        if "구매_ch" in daily.columns:
            fig.add_trace(go.Bar(x=daily["일"], y=daily["구매_ch"], name="구매 CH"))
        if "구매_af" in daily.columns:
            fig.add_trace(go.Bar(x=daily["일"], y=daily["구매_af"], name="구매 AF"))
        fig.update_layout(barmode="group", yaxis_title="구매수")
        st.plotly_chart(fig, use_container_width=True)

    with t4:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily["일"], y=daily["ROAS_ch"], name="ROAS CH", mode="lines+markers"))
        fig.add_trace(go.Scatter(x=daily["일"], y=daily["ROAS_af"], name="ROAS AF", mode="lines+markers", line=dict(dash="dash")))
        fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="ROAS 100%")
        fig.update_layout(yaxis_title="ROAS (%)")
        st.plotly_chart(fig, use_container_width=True)


# ── 탭2: 채널 비교 ────────────────────────────────────────────

with tab_channel:
    if "채널" not in fdf.columns:
        st.info("채널 컬럼 없음")
    else:
        agg_map2: dict = {"비용": ("비용", "sum"), "노출": ("노출", "sum")}
        for m in COMPARE_METRICS:
            for src in ("ch", "af"):
                c = get_col(fdf, m, src)
                if c in fdf.columns:
                    agg_map2[f"{m}_{src}"] = (c, "sum")

        ch_agg = fdf.groupby("채널").agg(**agg_map2).reset_index()
        ch_agg["ROAS_ch"] = ch_agg.get("구매매출_ch", 0) / ch_agg["비용"].replace(0, pd.NA) * 100
        ch_agg["ROAS_af"] = ch_agg.get("구매매출_af", 0) / ch_agg["비용"].replace(0, pd.NA) * 100
        ch_agg["CPA_ch"]  = ch_agg["비용"] / ch_agg.get("구매_ch", pd.Series(dtype=float)).replace(0, pd.NA)
        ch_agg["CPA_af"]  = ch_agg["비용"] / ch_agg.get("구매_af", pd.Series(dtype=float)).replace(0, pd.NA)

        c1, c2, c3 = st.columns(3)
        with c1:
            fig = px.pie(ch_agg, names="채널", values="비용", title="채널별 비용 비중",
                         color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(ch_agg, x="채널", y=["ROAS_ch", "ROAS_af"], barmode="group",
                         title="채널별 ROAS CH vs AF",
                         color_discrete_map={"ROAS_ch": "#00CC96", "ROAS_af": "#FFA15A"})
            fig.add_hline(y=100, line_dash="dot", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
        with c3:
            fig = px.bar(ch_agg, x="채널", y=["CPA_ch", "CPA_af"], barmode="group",
                         title="채널별 CPA CH vs AF",
                         color_discrete_map={"CPA_ch": "#636EFA", "CPA_af": "#EF553B"})
            st.plotly_chart(fig, use_container_width=True)

        fmt = {
            "비용": "{:,.0f}", "노출": "{:,.0f}",
            "클릭_ch": "{:,.0f}", "클릭_af": "{:,.0f}",
            "회원가입_ch": "{:,.0f}", "회원가입_af": "{:,.0f}",
            "구매_ch": "{:,.0f}", "구매_af": "{:,.0f}",
            "구매매출_ch": "{:,.0f}", "구매매출_af": "{:,.0f}",
            "ROAS_ch": "{:.1f}%", "ROAS_af": "{:.1f}%",
            "CPA_ch": "{:,.0f}", "CPA_af": "{:,.0f}",
        }
        st.dataframe(
            ch_agg.style.format({k: v for k, v in fmt.items() if k in ch_agg.columns}),
            use_container_width=True,
        )


# ── 탭3: 캠페인 ───────────────────────────────────────────────

with tab_campaign:
    if "캠페인" not in fdf.columns:
        st.info("캠페인 컬럼 없음")
    else:
        grp_keys = [k for k in ["채널", "캠페인목적", "캠페인"] if k in fdf.columns]
        agg_map3: dict = {"비용": ("비용", "sum"), "노출": ("노출", "sum")}
        for m in COMPARE_METRICS:
            for src in ("ch", "af"):
                c = get_col(fdf, m, src)
                if c in fdf.columns:
                    agg_map3[f"{m}_{src}"] = (c, "sum")

        cmp_agg = fdf.groupby(grp_keys).agg(**agg_map3).reset_index()
        cmp_agg["ROAS_ch"] = cmp_agg.get("구매매출_ch", 0) / cmp_agg["비용"].replace(0, pd.NA) * 100
        cmp_agg["ROAS_af"] = cmp_agg.get("구매매출_af", 0) / cmp_agg["비용"].replace(0, pd.NA) * 100
        cmp_agg["CPA_af"]  = cmp_agg["비용"] / cmp_agg.get("구매_af", pd.Series(dtype=float)).replace(0, pd.NA)

        color_col = "채널" if "채널" in cmp_agg.columns else "캠페인"
        size_col  = "구매_ch" if "구매_ch" in cmp_agg.columns else None

        fig = px.scatter(
            cmp_agg, x="비용", y="ROAS_ch",
            size=size_col, color=color_col,
            hover_data=["캠페인"] + ([c for c in ["ROAS_af", "CPA_af"] if c in cmp_agg.columns]),
            title="캠페인 비용 vs ROAS (버블=구매수 CH, hover=AF 지표)",
        )
        fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="ROAS 100%")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(cmp_agg.sort_values("ROAS_ch", ascending=False), use_container_width=True)


# ── 탭4: 소재 ─────────────────────────────────────────────────

with tab_creative:
    if "소재" not in fdf.columns:
        st.info("소재 컬럼 없음")
    else:
        fdf_cr = fdf.copy()
        fdf_cr["소재타입"] = fdf_cr["소재"].str.split("_").str[0]
        fdf_cr["AB"] = fdf_cr["소재"].apply(
            lambda x: next((p for p in str(x).split("_") if p in ("A", "B")), "단일")
        )

        cr_agg_map: dict = {"비용": ("비용", "sum")}
        for src in ("ch", "af"):
            for m in ("구매매출", "구매", "클릭"):
                c = get_col(fdf_cr, m, src)
                if c in fdf_cr.columns:
                    cr_agg_map[f"{m}_{src}"] = (c, "sum")

        cr_agg = fdf_cr.groupby(["소재", "소재타입", "AB"]).agg(**cr_agg_map).reset_index()
        rank_col = "구매매출_ch" if "구매매출_ch" in cr_agg.columns else "비용"
        cr_agg["ROAS_ch"] = cr_agg.get("구매매출_ch", 0) / cr_agg["비용"].replace(0, pd.NA) * 100

        top_n = st.slider("TOP N 소재", 5, 30, 15)
        top = cr_agg.nlargest(top_n, rank_col)

        c1, c2 = st.columns([3, 1])
        with c1:
            fig = go.Figure()
            if "구매매출_ch" in top.columns:
                fig.add_trace(go.Bar(y=top["소재"], x=top["구매매출_ch"], name="매출 CH", orientation="h"))
            if "구매매출_af" in top.columns:
                fig.add_trace(go.Bar(y=top["소재"], x=top["구매매출_af"], name="매출 AF", orientation="h", marker_opacity=0.6))
            fig.update_layout(barmode="group", height=max(400, top_n * 28), xaxis_title="구매매출 (₩)")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("##### 소재타입별 매출")
            type_agg = cr_agg.groupby("소재타입")[rank_col].sum().reset_index()
            fig2 = px.pie(type_agg, names="소재타입", values=rank_col,
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig2, use_container_width=True)

        if st.checkbox("AB 테스트 비교 보기"):
            ab_agg = fdf_cr.groupby(["소재타입", "AB"]).agg(**cr_agg_map).reset_index()
            ab_agg["ROAS_ch"] = ab_agg.get("구매매출_ch", 0) / ab_agg["비용"].replace(0, pd.NA) * 100
            fig3 = px.bar(ab_agg, x="소재타입", y="ROAS_ch", color="AB", barmode="group",
                          title="소재타입 × AB 테스트별 ROAS CH")
            st.plotly_chart(fig3, use_container_width=True)


# ── 탭5: Braze CRM ────────────────────────────────────────────

with tab_braze:
    purchases = braze["purchases"]
    users     = braze["users"]
    campaigns = braze["campaigns"]

    if purchases.empty and users.empty and campaigns.empty:
        st.info("Braze 데이터가 없습니다.\n\n" + (
            "data/raw/braze/ 폴더에 파일을 넣어주세요." if IS_LOCAL
            else "사이드바 'Braze 데이터' 항목에서 파일을 업로드하세요."
        ))
    else:
        bz1, bz2, bz3 = st.tabs(["구매 트랜잭션", "유저 세그먼트", "CRM 캠페인"])

        with bz1:
            if purchases.empty:
                st.info("purchases 파일 없음")
            else:
                pur_mask = (
                    (purchases["purchase_at"].dt.date >= date_range[0]) &
                    (purchases["purchase_at"].dt.date <= date_range[-1])
                )
                pur = purchases[pur_mask]
                k1, k2, k3 = st.columns(3)
                k1.metric("총 구매건 (Braze)", f"{len(pur):,}")
                k2.metric("총 매출 (Braze)",   f"₩{pur['amount'].sum():,.0f}")
                k3.metric("객단가",             f"₩{pur['amount'].mean():,.0f}")

                daily_pur = pur.groupby(pur["purchase_at"].dt.date).agg(
                    건수=("order_id", "count"), 매출=("amount", "sum")
                ).reset_index().rename(columns={"purchase_at": "일"})
                fig = px.bar(daily_pur, x="일", y="매출", title="Braze 일별 구매 매출")
                st.plotly_chart(fig, use_container_width=True)

        with bz2:
            if users.empty:
                st.info("users 파일 없음")
            else:
                seg_col = "_segment_truth" if "_segment_truth" in users.columns else None
                if seg_col:
                    seg_dist = users[seg_col].value_counts().reset_index()
                    seg_dist.columns = ["세그먼트", "유저수"]
                    c1, c2 = st.columns(2)
                    with c1:
                        fig = px.pie(seg_dist, names="세그먼트", values="유저수",
                                     title="유저 세그먼트 분포",
                                     color_discrete_sequence=px.colors.qualitative.Set2)
                        st.plotly_chart(fig, use_container_width=True)
                    with c2:
                        if "attribution_source" in users.columns:
                            attr = users.groupby(["attribution_source", seg_col]).size().reset_index(name="유저수")
                            fig2 = px.bar(attr, x="attribution_source", y="유저수", color=seg_col,
                                          title="유입 채널별 세그먼트 분포", barmode="stack")
                            st.plotly_chart(fig2, use_container_width=True)
                st.dataframe(users.head(200), use_container_width=True)

        with bz3:
            if campaigns.empty:
                st.info("campaigns 파일 없음")
            else:
                cmp_mask = (
                    (campaigns["sent_at"].dt.date >= date_range[0]) &
                    (campaigns["sent_at"].dt.date <= date_range[-1])
                )
                cmp = campaigns[cmp_mask]
                agg_keys = [c for c in ["canvas_name", "variant", "target_segment"] if c in cmp.columns]
                cmp_bz = cmp.groupby(agg_keys).agg(
                    발송=("delivered", "sum"),
                    오픈=("opened", "sum"),
                    클릭=("clicked", "sum"),
                    전환=("converted", "sum"),
                    전환매출=("conversion_value", "sum"),
                ).reset_index()
                cmp_bz["오픈율"] = cmp_bz["오픈"] / cmp_bz["발송"].replace(0, pd.NA) * 100
                cmp_bz["전환율"] = cmp_bz["전환"] / cmp_bz["발송"].replace(0, pd.NA) * 100

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("총 발송",  f"{cmp['delivered'].sum():,}")
                k2.metric("오픈율",   f"{cmp['opened'].sum()/max(cmp['delivered'].sum(),1)*100:.1f}%")
                k3.metric("클릭율",   f"{cmp['clicked'].sum()/max(cmp['delivered'].sum(),1)*100:.1f}%")
                k4.metric("전환율",   f"{cmp['converted'].sum()/max(cmp['delivered'].sum(),1)*100:.1f}%")

                if "variant" in cmp_bz.columns:
                    fig = px.bar(cmp_bz, x="canvas_name", y="전환율", color="variant",
                                 barmode="group", title="CRM 캠페인 AB 전환율 비교")
                    st.plotly_chart(fig, use_container_width=True)

                st.dataframe(cmp_bz, use_container_width=True)


# ── 탭6: 원본 데이터 ──────────────────────────────────────────

with tab_raw:
    src_opt = st.radio("데이터 소스", ["조인 데이터", "Channel 원본", "AppsFlyer 원본"], horizontal=True)
    if src_opt == "조인 데이터":
        st.dataframe(fdf, use_container_width=True)
        st.caption(f"필터 적용 {len(fdf):,}행 / 전체 {len(df):,}행")
    elif src_opt == "Channel 원본":
        st.dataframe(ch_raw, use_container_width=True)
        st.caption(f"{len(ch_raw):,}행")
    else:
        st.dataframe(af_raw, use_container_width=True)
        st.caption(f"{len(af_raw):,}행")
