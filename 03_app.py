import os
import pandas as pd
import numpy as np
import streamlit as st
import folium
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import st_folium

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ParkIQ – Bengaluru Enforcement Intelligence",
    page_icon="🚦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------
AMBER    = "#F7B558"
SAGE     = "#A5D48C"
CHARCOAL = "#363236"
DANGER   = "#E05252"
SURFACE  = "#F2F2F0"

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter Tight', sans-serif !important; }
.stApp { background-color: #F2F2F0 !important; }
section[data-testid="stSidebar"] > div { background-color: #363236 !important; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] p { color: #FFFFFF !important; }
[data-testid="stMetricValue"] { color: #F7B558 !important; font-weight: 600 !important; }
.stButton > button {
    background-color: #F7B558 !important;
    color: #363236 !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 20px !important;
}
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))

@st.cache_data
def load_pis():
    path = os.path.join(ROOT, "outputs", "pis_scores.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    # Normalise junction column name used throughout the app
    if "junction_name_final" in df.columns:
        df = df.rename(columns={"junction_name_final": "junction_name"})
    # PIS percentile fix: colour by relative rank, not absolute score
    df["PIS_pct"] = df["PIS"].rank(pct=True)
    return df

@st.cache_data
def load_dark_fleet():
    path = os.path.join(ROOT, "outputs", "dark_fleet.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)

@st.cache_data
def load_violations():
    path = os.path.join(ROOT, "data", "violations_clean.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, low_memory=False)
    if "junction_name_final" in df.columns:
        df = df.rename(columns={"junction_name_final": "junction_name"})
    return df

@st.cache_data
def load_station_funnel():
    path = os.path.join(ROOT, "data", "station_funnel.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)

pis_scores      = load_pis()
dark_fleet      = load_dark_fleet()
violations_df   = load_violations()
station_funnel  = load_station_funnel()

if pis_scores is None:
    st.warning("outputs/pis_scores.csv not found — run 02_analytics.py first")
if violations_df is None:
    st.warning("data/violations_clean.csv not found — run 01_clean_and_resolve.py first")
if station_funnel is None:
    st.warning("data/station_funnel.csv not found — run 01_clean_and_resolve.py first")

def _pis_colour(pis_pct: float) -> str:
    if pis_pct >= 0.85:
        return DANGER
    if pis_pct >= 0.60:
        return AMBER
    return SAGE

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.markdown(
    '<h2 style="color:#F7B558;font-family:Inter Tight;margin-bottom:2px;">ParkIQ</h2>',
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    '<p style="color:#8A8789;font-size:11px;margin-top:0;">Bengaluru Enforcement Intelligence</p>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "",
    ["Operations Map", "Enforcement Funnel", "Dark Fleet",
     "Junction Deep-Dive", "What-If Simulator", "Patrol Planner"],
)

# ===========================================================================
# PAGE: Operations Map
# ===========================================================================
if page == "Operations Map":
    st.markdown(
        '<h1 style="font-family:Inter Tight;margin-bottom:4px;">Operations Map</h1>',
        unsafe_allow_html=True,
    )

    if pis_scores is not None:
        # Stat bar
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Violations", "298,449")
        col2.metric("Junctions Analysed", len(pis_scores))
        col3.metric(
            "Vehicle-hrs Lost / Day",
            f"{pis_scores['vehicle_hours_lost_per_day'].sum():,.0f}",
        )
        col4.metric(
            "₹ Lost / Day",
            f"₹{pis_scores['loss_INR_per_day'].sum():,.0f}",
        )

        # Folium map
        m = folium.Map(
            location=[12.9716, 77.5946],
            zoom_start=12,
            tiles="CartoDB positron",
        )

        junction_fg   = folium.FeatureGroup(name="Junctions", show=True)
        dark_fleet_fg = folium.FeatureGroup(name="Dark Fleet", show=False)

        # Junction circles
        for _, row in pis_scores.iterrows():
            if pd.isna(row["lat_mean"]) or pd.isna(row["lon_mean"]):
                continue
            colour = _pis_colour(row["PIS_pct"])
            radius = max(6, min(25, int(row["violation_volume"] / 500)))
            popup_html = f"""
            <div style="font-family:sans-serif;min-width:200px;">
              <b style="font-size:13px;">{row['junction_name']}</b><br>
              <span style="background:{colour};color:white;padding:2px 8px;
                    border-radius:4px;font-size:11px;">{row['action_type']}</span>
              <br><br>
              <b>PIS Score:</b> {row['PIS']:.3f} (Rank #{int(row['rank'])})<br>
              <b>Violations:</b> {int(row['violation_volume']):,}<br>
              <b>Vehicle-hrs lost/day:</b> {row['vehicle_hours_lost_per_day']:.1f}<br>
              <b>₹ Lost/day:</b> ₹{row['loss_INR_per_day']:,.0f}
            </div>"""
            folium.CircleMarker(
                location=[row["lat_mean"], row["lon_mean"]],
                radius=radius,
                color=colour,
                fill=True,
                fill_color=colour,
                fill_opacity=0.7,
                weight=1.5,
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(junction_fg)

        # Dark Fleet markers (fleet leaders only)
        if dark_fleet is not None:
            junc_loc = (
                pis_scores.dropna(subset=["lat_mean", "lon_mean"])
                .set_index("junction_name")[["lat_mean", "lon_mean"]]
            )
            for _, fl_row in dark_fleet[dark_fleet["is_fleet_leader"]].iterrows():
                junctions = str(fl_row["junction_list"]).split(";")
                for junc in junctions:
                    junc = junc.strip()
                    if junc in junc_loc.index:
                        jlat = junc_loc.loc[junc, "lat_mean"]
                        jlon = junc_loc.loc[junc, "lon_mean"]
                        folium.Marker(
                            location=[jlat, jlon],
                            popup=folium.Popup(
                                f"Cluster {fl_row['fleet_cluster_id']} | "
                                f"{fl_row['vehicle_number']} | "
                                f"{fl_row['total_hits']} hits",
                                max_width=200,
                            ),
                            icon=folium.DivIcon(
                                html='<div style="background:#111111;color:white;'
                                     'border-radius:50%;width:20px;height:20px;'
                                     'display:flex;align-items:center;'
                                     'justify-content:center;font-weight:700;'
                                     'font-size:12px;border:2px solid white;">F</div>',
                                icon_size=(20, 20),
                                icon_anchor=(10, 10),
                            ),
                        ).add_to(dark_fleet_fg)

        junction_fg.add_to(m)
        dark_fleet_fg.add_to(m)
        folium.LayerControl().add_to(m)
        st_folium(m, use_container_width=True, height=500, returned_objects=[])

        # Top 10 table
        st.markdown(
            '<div style="background:white;border-radius:12px;'
            'padding:16px;margin-top:12px;">',
            unsafe_allow_html=True,
        )
        st.markdown("**Top 10 junctions by impact**")
        display_cols = [
            "rank", "junction_name", "PIS", "action_type",
            "violation_volume", "loss_INR_per_day",
        ]
        st.dataframe(
            pis_scores[display_cols].head(10).rename(
                columns={
                    "rank":             "Rank",
                    "junction_name":    "Junction",
                    "PIS":              "PIS Score",
                    "action_type":      "Action",
                    "violation_volume": "Violations",
                    "loss_INR_per_day": "₹ Loss/Day",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

# ===========================================================================
# PAGE: Enforcement Funnel
# ===========================================================================
elif page == "Enforcement Funnel":
    st.title("Enforcement pipeline — where it breaks")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f'<div style="background:#fde8e8;border-left:4px solid {DANGER};'
            f'padding:12px;border-radius:8px;">'
            "<b>0 enforcement actions recorded</b><br>"
            "across 298,449 violations"
            "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:12px;border-radius:8px;">'
            "<b>60.1% of captures happen at 5am</b><br>"
            "roads are empty"
            "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:12px;border-radius:8px;">'
            "<b>Kodigehalli sends only 54.7%</b><br>"
            "of violations to SCITA"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Funnel chart
    fig_funnel = go.Figure(
        go.Funnel(
            y=["Captured", "Validated (Approved)", "Sent to SCITA", "Action Taken"],
            x=[298449, 115400, 255893, 1],
            textinfo="value+percent initial",
            marker=dict(color=[CHARCOAL, AMBER, AMBER, DANGER]),
        )
    )
    fig_funnel.update_layout(
        title="The 4-stage enforcement pipeline",
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font_family="Inter Tight",
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # 24-hour bar chart
    if violations_df is not None:
        hour_df = (
            violations_df["hour"]
            .dropna()
            .astype(int)
            .value_counts()
            .sort_index()
            .reset_index()
        )
        hour_df.columns = ["hour", "count"]
        colours_24h = [
            DANGER if h <= 6 else (SAGE if 9 <= h <= 18 else "#CCCCCC")
            for h in hour_df["hour"]
        ]
        fig_hour = px.bar(
            hour_df,
            x="hour",
            y="count",
            title="Violations by hour of day",
        )
        fig_hour.update_traces(marker_color=colours_24h)
        fig_hour.add_vrect(
            x0=-0.5, x1=6.5,
            fillcolor=DANGER, opacity=0.08,
            annotation_text="60% captured here (0–6am)",
            annotation_position="top left",
        )
        fig_hour.add_vrect(
            x0=8.5, x1=18.5,
            fillcolor=SAGE, opacity=0.08,
            annotation_text="Peak congestion (9am–6pm)",
            annotation_position="top right",
        )
        fig_hour.update_layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font_family="Inter Tight",
            xaxis_title="Hour of day",
            yaxis_title="Violations",
        )
        st.plotly_chart(fig_hour, use_container_width=True)

# ===========================================================================
# PAGE: Dark Fleet
# ===========================================================================
elif page == "Dark Fleet":
    st.title("Dark Fleet Detector")

    if dark_fleet is None:
        st.info("Run 03_dark_fleet.py first to generate outputs/dark_fleet.csv")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fleet Vehicles",       len(dark_fleet))
        c2.metric("Fleet Clusters",       dark_fleet["fleet_cluster_id"].nunique())
        c3.metric("Top Offender Hits",    int(dark_fleet["total_hits"].max()))
        c4.metric(
            "Avg Junctions / Vehicle",
            f"{dark_fleet['distinct_junctions'].mean():.1f}",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        plot_df = dark_fleet.assign(vehicle_idx=range(len(dark_fleet)))
        fig_scatter = px.scatter(
            plot_df,
            x="vehicle_idx",
            y="total_hits",
            size="total_hits",
            color=plot_df["fleet_cluster_id"].astype(str),
            hover_data=["vehicle_number", "junction_list", "distinct_junctions"],
            color_discrete_sequence=[AMBER, SAGE, "#7BBFEA", "#C97ED4", "#F09F7C"],
            title="Fleet vehicles by hit count — sized by violations",
            labels={"vehicle_idx": "Vehicle index", "total_hits": "Total violations"},
        )
        fig_scatter.update_layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font_family="Inter Tight",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.dataframe(dark_fleet, use_container_width=True, hide_index=True)

# ===========================================================================
# PAGE: What-If Simulator
# ===========================================================================
elif page == "What-If Simulator":
    st.title("What-If Enforcement Simulator")
    st.markdown("*Move the sliders. Watch the city save money.*")

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        left, right = st.columns([1, 2])

        with left:
            enforcement_rate = st.slider(
                "Enforcement action rate", 0, 100, 0, format="%d%%"
            )
            scope = st.selectbox(
                "Target junctions", ["Top 5", "Top 10", "Top 20", "All"]
            )
            st.markdown("---")
            st.markdown(
                f"**Current state:** 0% enforcement = "
                f"₹{pis_scores['loss_INR_per_day'].sum():,.0f} lost daily"
            )

        with right:
            n_map = {"Top 5": 5, "Top 10": 10, "Top 20": 20, "All": len(pis_scores)}
            n = n_map[scope]
            selected = pis_scores.nsmallest(n, "rank")

            vh_saved      = (enforcement_rate / 100) * selected["vehicle_hours_lost_per_day"].sum()
            inr_day       = vh_saved * 150
            inr_year      = inr_day * 365
            total_vh      = max(pis_scores["vehicle_hours_lost_per_day"].sum(), 1)
            congestion_pct = vh_saved / total_vh * 100

            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Hrs saved / day",   f"{vh_saved:,.1f}")
            rc2.metric("₹ saved / day", f"₹{inr_day:,.0f}")
            rc3.metric("₹ saved / year",f"₹{inr_year:,.0f}")
            rc4.metric("Congestion drop",   f"{congestion_pct:.1f}%")

            chart_df = pis_scores.copy()
            chart_df["selected"] = chart_df["rank"] <= n
            chart_df["colour"]   = chart_df["selected"].map(
                {True: AMBER, False: "#DDDDDD"}
            )
            top20_chart = chart_df.head(20)
            fig_bar = px.bar(
                top20_chart,
                x="junction_name",
                y="PIS",
                title=f"Top 20 junctions — {n} targeted (amber)",
            )
            fig_bar.update_traces(
                marker_color=top20_chart["colour"].tolist()
            )
            fig_bar.update_layout(
                paper_bgcolor=SURFACE,
                plot_bgcolor=SURFACE,
                font_family="Inter Tight",
                xaxis_tickangle=-45,
                xaxis_title="",
                yaxis_title="PIS Score",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# ===========================================================================
# PAGE: Junction Deep-Dive
# ===========================================================================
elif page == "Junction Deep-Dive":
    st.title("Junction Deep-Dive")

    if pis_scores is None or violations_df is None:
        st.warning("Required data files not loaded.")
    else:
        junction = st.selectbox(
            "Select junction", pis_scores["junction_name"].tolist()
        )
        row = pis_scores[pis_scores["junction_name"] == junction].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PIS Score",  f"{row['PIS']:.3f}")
        c2.metric("Rank",       f"#{int(row['rank'])} of {len(pis_scores)}")
        c3.metric("₹ Loss / Day", f"₹{row['loss_INR_per_day']:,.0f}")
        c4.metric("Action",     row["action_type"])

        junc_violations = violations_df[
            violations_df["junction_name"] == junction
        ]

        if junc_violations.empty:
            st.info("No violation records found for this junction.")
        else:
            col1, col2, col3 = st.columns(3)

            with col1:
                hour_counts = (
                    junc_violations["hour"]
                    .dropna()
                    .astype(int)
                    .value_counts()
                    .sort_index()
                    .reset_index()
                )
                hour_counts.columns = ["hour", "count"]
                fig_h = px.bar(
                    hour_counts, x="hour", y="count",
                    title="Violations by hour",
                    color_discrete_sequence=[AMBER],
                )
                fig_h.update_layout(
                    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                    font_family="Inter Tight",
                )
                st.plotly_chart(fig_h, use_container_width=True)

            with col2:
                vtype_counts = (
                    junc_violations["vehicle_type"]
                    .value_counts()
                    .reset_index()
                )
                vtype_counts.columns = ["vehicle_type", "count"]
                fig_v = px.bar(
                    vtype_counts.head(10),
                    x="count", y="vehicle_type",
                    orientation="h",
                    title="By vehicle type",
                    color_discrete_sequence=[SAGE],
                )
                fig_v.update_layout(
                    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                    font_family="Inter Tight", yaxis_title="",
                )
                st.plotly_chart(fig_v, use_container_width=True)

            with col3:
                month_order = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December",
                ]
                monthly = (
                    junc_violations.groupby("month")
                    .size()
                    .reset_index(name="count")
                )
                monthly["month_num"] = monthly["month"].map(
                    {m: i for i, m in enumerate(month_order)}
                )
                monthly = monthly.sort_values("month_num")
                fig_m = px.line(
                    monthly, x="month", y="count",
                    title="Monthly trend",
                    markers=True,
                    color_discrete_sequence=[CHARCOAL],
                )
                fig_m.update_layout(
                    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                    font_family="Inter Tight", xaxis_title="",
                )
                st.plotly_chart(fig_m, use_container_width=True)

# ===========================================================================
# PAGE: Patrol Planner
# ===========================================================================
elif page == "Patrol Planner":
    st.title("Patrol Planner")
    st.info(
        "Patrol route optimisation coming in next build. "
        "For now, here are the top priority junctions for manual patrol assignment."
    )

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        top20 = pis_scores.head(20)[
            ["rank", "junction_name", "action_type",
             "violation_volume", "loss_INR_per_day",
             "lat_mean", "lon_mean"]
        ]
        st.dataframe(top20, use_container_width=True, hide_index=True)

        m2 = folium.Map(
            location=[12.9716, 77.5946],
            zoom_start=12,
            tiles="CartoDB positron",
        )
        for _, row in top20.iterrows():
            if pd.notna(row["lat_mean"]) and pd.notna(row["lon_mean"]):
                folium.Marker(
                    location=[row["lat_mean"], row["lon_mean"]],
                    popup=f"#{int(row['rank'])} {row['junction_name']}",
                    icon=folium.DivIcon(
                        html=(
                            f'<div style="background:{AMBER};color:{CHARCOAL};'
                            f'border-radius:50%;width:24px;height:24px;'
                            f'display:flex;align-items:center;justify-content:center;'
                            f'font-weight:600;font-size:11px;'
                            f'border:2px solid white;">'
                            f'{int(row["rank"])}</div>'
                        ),
                        icon_size=(24, 24),
                        icon_anchor=(12, 12),
                    ),
                ).add_to(m2)

        st_folium(m2, use_container_width=True, height=400, returned_objects=[])
