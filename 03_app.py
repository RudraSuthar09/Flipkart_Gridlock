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
def load_fleet_edges():
    path = os.path.join(ROOT, "outputs", "fleet_graph_edges.csv")
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
fleet_edges     = load_fleet_edges()
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

# Session-state page navigation (allows buttons to switch pages)
if "page" not in st.session_state:
    st.session_state.page = "Operations Map"

RADIO_PAGES = [
    "Operations Map", "Enforcement Funnel", "Dark Fleet",
    "Junction Deep-Dive", "What-If Simulator", "Patrol Planner",
]

# If session_state was set by a button, pre-select that page in the radio
default_idx = (
    RADIO_PAGES.index(st.session_state.page)
    if st.session_state.page in RADIO_PAGES else 0
)
page = st.sidebar.radio(
    "",
    RADIO_PAGES,
    index=default_idx,
    key="page_radio",
)
# Keep session_state in sync with the radio
st.session_state.page = page

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

        # ── Folium map ──────────────────────────────────────────────────────
        m = folium.Map(
            location=[12.9716, 77.5946],
            zoom_start=12,
            tiles=None,
        )
        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name="Street Map",
            max_zoom=19,
            subdomains="abc",
        ).add_to(m)

        junction_fg   = folium.FeatureGroup(name="Junctions", show=True)
        dark_fleet_fg = folium.FeatureGroup(name="Dark Fleet", show=False)

        # Top-10 junctions for hover tooltips
        top10_names = set(pis_scores.nsmallest(10, "rank")["junction_name"])

        # ── Junction circle markers ──────────────────────────────────────────
        for _, row in pis_scores.iterrows():
            if pd.isna(row["lat_mean"]) or pd.isna(row["lon_mean"]):
                continue

            colour = _pis_colour(row["PIS_pct"])

            # Tier-based visual weight
            if row["PIS_pct"] >= 0.85:
                radius, fill_opacity, weight = 20, 0.85, 2
            elif row["PIS_pct"] >= 0.60:
                radius, fill_opacity, weight = 14, 0.75, 1.5
            else:
                radius, fill_opacity, weight = 8, 0.60, 1

            popup_html = (
                '<div style="font-family:Inter Tight,sans-serif;width:220px;padding:4px;">'
                f'<div style="font-weight:600;font-size:13px;margin-bottom:6px;">{row["junction_name"]}</div>'
                f'<div style="background:{colour};color:white;display:inline-block;'
                f'padding:2px 10px;border-radius:20px;font-size:11px;font-weight:600;'
                f'margin-bottom:8px;">{row["action_type"]}</div>'
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                '<span style="color:#666;font-size:12px;">PIS Score</span>'
                f'<span style="font-weight:600;font-size:12px;">{row["PIS"]:.3f}</span>'
                '</div>'
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                '<span style="color:#666;font-size:12px;">Rank</span>'
                f'<span style="font-weight:600;font-size:12px;">#{int(row["rank"])} of {len(pis_scores)}</span>'
                '</div>'
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                '<span style="color:#666;font-size:12px;">Violations</span>'
                f'<span style="font-weight:600;font-size:12px;">{int(row["violation_volume"]):,}</span>'
                '</div>'
                '<div style="border-top:1px solid #eee;margin-top:8px;padding-top:6px;">'
                '<div style="display:flex;justify-content:space-between;">'
                '<span style="color:#666;font-size:12px;">&#8377; Lost / day</span>'
                f'<span style="font-weight:600;font-size:12px;color:#E05252;">&#8377;{row["loss_INR_per_day"]:,.0f}</span>'
                '</div></div></div>'
            )

            marker = folium.CircleMarker(
                location=[row["lat_mean"], row["lon_mean"]],
                radius=radius,
                color="white",
                fill=True,
                fill_color=colour,
                fill_opacity=fill_opacity,
                weight=weight,
                popup=folium.Popup(popup_html, max_width=260),
            )

            # Hover tooltip for top-10 only
            if row["junction_name"] in top10_names:
                marker.add_child(folium.Tooltip(row["junction_name"], sticky=False))

            marker.add_to(junction_fg)

        # ── Dark Fleet markers (fleet leaders at their highest-weight junction) ──
        if dark_fleet is not None and fleet_edges is not None:
            junc_loc = (
                pis_scores.dropna(subset=["lat_mean", "lon_mean"])
                .set_index("junction_name")[["lat_mean", "lon_mean"]]
            )
            # Best junction per vehicle = highest weight edge
            best_junc = (
                fleet_edges.sort_values("weight", ascending=False)
                .drop_duplicates(subset="vehicle_number", keep="first")
                .set_index("vehicle_number")["junction_name"]
            )
            for _, fl_row in dark_fleet[dark_fleet["is_fleet_leader"]].iterrows():
                vn = fl_row["vehicle_number"]
                junc = best_junc.get(vn)
                if junc is None or junc not in junc_loc.index:
                    continue
                jlat = junc_loc.loc[junc, "lat_mean"]
                jlon = junc_loc.loc[junc, "lon_mean"]
                folium.Marker(
                    location=[jlat, jlon],
                    tooltip=folium.Tooltip(
                        f"Fleet cluster {fl_row['fleet_cluster_id']} — {fl_row['total_hits']} hits",
                        sticky=False,
                    ),
                    popup=folium.Popup(
                        f"<b>{fl_row['vehicle_number']}</b><br>"
                        f"Cluster {fl_row['fleet_cluster_id']} | "
                        f"{fl_row['total_hits']} total hits | "
                        f"{fl_row['distinct_junctions']} junctions",
                        max_width=220,
                    ),
                    icon=folium.DivIcon(
                        html=(
                            '<div style="background:#363236;color:#F7B558;'
                            'border-radius:50%;width:28px;height:28px;'
                            'display:flex;align-items:center;justify-content:center;'
                            'font-weight:700;font-size:13px;'
                            'border:2px solid #F7B558;'
                            'box-shadow:0 2px 6px rgba(0,0,0,0.4);">F</div>'
                        ),
                        icon_size=(28, 28),
                        icon_anchor=(14, 14),
                    ),
                ).add_to(dark_fleet_fg)

        # ── Legend ──────────────────────────────────────────────────────────
        legend_html = """
        <div style="position:fixed;bottom:30px;right:10px;background:white;
                    padding:12px 16px;border-radius:10px;
                    box-shadow:0 2px 10px rgba(0,0,0,0.2);
                    font-family:sans-serif;font-size:12px;z-index:9999;">
          <div style="font-weight:600;margin-bottom:8px;">Parking Impact Score</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#E05252;"></div>
            Critical (top 15%)
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#F7B558;"></div>
            High (top 40%)
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#A5D48C;"></div>
            Monitor
          </div>
          <div style="border-top:1px solid #eee;padding-top:8px;
                      display:flex;align-items:center;gap:8px;">
            <div style="width:14px;height:14px;border-radius:50%;
                        background:#363236;border:2px solid #F7B558;"></div>
            Dark fleet
          </div>
        </div>"""
        m.get_root().html.add_child(folium.Element(legend_html))

        junction_fg.add_to(m)
        dark_fleet_fg.add_to(m)
        folium.LayerControl().add_to(m)
        st_folium(m, use_container_width=True, height=600, returned_objects=[])

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
    st.title("The enforcement pipeline — where it breaks")

    # ── Callout KPI cards ────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f'<div style="background:#fde8e8;border-left:4px solid {DANGER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:13px;font-weight:700;color:{DANGER};">CRITICAL</span><br>'
            "<b>0 enforcement actions recorded</b><br>"
            "<span style='color:#555;font-size:13px;'>across 298,449 violations</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:13px;font-weight:700;color:#B45309;">TIMING GAP</span><br>'
            "<b>60.1% of captures happen at 5am</b><br>"
            "<span style='color:#555;font-size:13px;'>roads are empty — no congestion impact</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:13px;font-weight:700;color:#B45309;">STATION FAILURE</span><br>'
            "<b>Kodigehalli sends only 54.7%</b><br>"
            "<span style='color:#555;font-size:13px;'>of violations to SCITA</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section A: Funnel chart ───────────────────────────────────────────────
    st.subheader("Section A — Pipeline stages")

    fig_funnel = go.Figure(
        go.Funnel(
            y=["Captured", "Validated (Approved)", "Sent to SCITA", "Action Taken"],
            # Use 1 for Action Taken so it renders as a visible sliver
            x=[298449, 115400, 255893, 1],
            textinfo="value+percent initial",
            textposition="inside",
            marker=dict(color=[CHARCOAL, AMBER, AMBER, DANGER]),
            connector=dict(line=dict(color="rgba(0,0,0,0.08)", width=1)),
        )
    )
    # Annotate the sliver bar with "0 actions" in red above it
    fig_funnel.add_annotation(
        x=1,  # right of the funnel values axis
        y="Action Taken",
        text="<b>0 actions</b>",
        showarrow=True,
        arrowhead=2,
        arrowcolor=DANGER,
        font=dict(color=DANGER, size=13, family="Inter Tight"),
        ax=80,
        ay=0,
        bgcolor="#fde8e8",
        bordercolor=DANGER,
        borderwidth=1,
        borderpad=4,
    )
    fig_funnel.update_layout(
        title=dict(
            text="The enforcement pipeline — where it breaks",
            font=dict(size=16, family="Inter Tight"),
        ),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font_family="Inter Tight",
        height=380,
        margin=dict(l=0, r=120, t=60, b=20),
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # ── Section B: 24-hour violation pattern ─────────────────────────────────
    st.subheader("Section B — 24-hour violation pattern")

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

        fig_hour = go.Figure(
            go.Bar(
                x=hour_df["hour"],
                y=hour_df["count"],
                marker_color=colours_24h,
                hovertemplate="Hour %{x}:00 — %{y:,} violations<extra></extra>",
            )
        )

        # Red band 0-6
        fig_hour.add_vrect(
            x0=-0.5, x1=6.5,
            fillcolor=DANGER, opacity=0.10,
            layer="below", line_width=0,
        )
        fig_hour.add_annotation(
            x=3, y=hour_df["count"].max() * 0.97,
            text="<b>60% of captures</b><br>roads are empty",
            showarrow=False,
            font=dict(color=DANGER, size=11, family="Inter Tight"),
            align="center",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=DANGER,
            borderwidth=1,
            borderpad=4,
        )

        # Green band 9-18
        fig_hour.add_vrect(
            x0=8.5, x1=18.5,
            fillcolor=SAGE, opacity=0.10,
            layer="below", line_width=0,
        )
        fig_hour.add_annotation(
            x=13.5, y=hour_df["count"].max() * 0.97,
            text="<b>Peak congestion</b><br>only 2.6% captured",
            showarrow=False,
            font=dict(color="#166534", size=11, family="Inter Tight"),
            align="center",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=SAGE,
            borderwidth=1,
            borderpad=4,
        )

        fig_hour.update_layout(
            title="Violations captured by hour of day",
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font_family="Inter Tight",
            xaxis=dict(title="Hour of day", dtick=1, gridcolor="#E8E8E6"),
            yaxis=dict(title="Violation count", gridcolor="#E8E8E6"),
            bargap=0.15,
            height=380,
            margin=dict(l=0, r=0, t=50, b=40),
        )
        st.plotly_chart(fig_hour, use_container_width=True)
    else:
        st.info("violations_clean.csv not loaded — run 01_clean_and_resolve.py first.")

    # ── Section C: Police-station SCITA send-rate ─────────────────────────────
    st.subheader("Section C — SCITA send-rate by police station")

    if station_funnel is not None:
        sf = station_funnel.sort_values("scita_send_rate", ascending=True).copy()
        sf["colour"] = sf["scita_send_rate"].apply(
            lambda r: DANGER if r < 0.75 else (AMBER if r < 0.85 else SAGE)
        )

        fig_station = go.Figure(
            go.Bar(
                x=sf["scita_send_rate"],
                y=sf["police_station"],
                orientation="h",
                marker_color=sf["colour"].tolist(),
                text=[f"{r*100:.1f}%" for r in sf["scita_send_rate"]],
                textposition="outside",
                hovertemplate="%{y}: %{x:.1%}<extra></extra>",
            )
        )

        # Reference line at 75%
        fig_station.add_vline(
            x=0.75,
            line_width=2,
            line_dash="dash",
            line_color=CHARCOAL,
            annotation_text="75% threshold",
            annotation_position="top right",
            annotation_font=dict(color=CHARCOAL, size=11, family="Inter Tight"),
        )

        # Annotate Kodigehalli in red if it's in the dataset
        kodige_rows = sf[sf["police_station"].str.contains("Kodigehalli", case=False, na=False)]
        if not kodige_rows.empty:
            kr = kodige_rows.iloc[0]
            fig_station.add_annotation(
                x=kr["scita_send_rate"] + 0.01,
                y=kr["police_station"],
                text="<b>Kodigehalli ⚠</b>",
                showarrow=True,
                arrowhead=2,
                arrowcolor=DANGER,
                font=dict(color=DANGER, size=11, family="Inter Tight"),
                ax=80, ay=0,
                bgcolor="#fde8e8",
                bordercolor=DANGER,
                borderwidth=1,
                borderpad=3,
            )

        fig_station.update_layout(
            title="SCITA send-rate per police station (sorted ascending)",
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font_family="Inter Tight",
            xaxis=dict(
                title="Send rate",
                tickformat=".0%",
                range=[0, 1.15],
                gridcolor="#E8E8E6",
            ),
            yaxis=dict(title="", automargin=True),
            height=max(350, len(sf) * 26),
            margin=dict(l=0, r=60, t=50, b=40),
        )
        st.plotly_chart(fig_station, use_container_width=True)
    else:
        st.info("station_funnel.csv not loaded — run 01_clean_and_resolve.py first.")

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
    st.markdown("*Move the sliders — watch the city save money.*")

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        left, right = st.columns([1, 2])

        # ── Left column: controls ─────────────────────────────────────────────
        with left:
            st.markdown(
                f'<div style="background:{CHARCOAL};border-radius:12px;padding:20px 18px;'
                f'margin-bottom:12px;">'
                f'<p style="color:#A0A0A0;font-size:12px;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;">'
                f'Simulation Controls</p>',
                unsafe_allow_html=True,
            )
            enforcement_rate = st.slider(
                "Enforcement action rate (%)", 0, 100, 0, format="%d%%",
                key="wif_enf",
            )
            scope = st.selectbox(
                "Target junctions", ["Top 5", "Top 10", "Top 20", "All"],
                key="wif_scope",
            )
            officers = st.slider(
                "Officers deployed", 1, 10, 3, key="wif_officers",
            )
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown(
                f'<div style="background:#1E1B1E;border-radius:8px;padding:12px 14px;'
                f'border-left:3px solid {DANGER};">'
                f'<span style="color:#A0A0A0;font-size:12px;">Current state (0% enforcement)</span><br>'
                f'<span style="color:{DANGER};font-weight:700;font-size:15px;">'
                f'₹{pis_scores["loss_INR_per_day"].sum():,.0f} lost / day</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Right column: results ─────────────────────────────────────────────
        with right:
            n_map = {"Top 5": 5, "Top 10": 10, "Top 20": 20, "All": len(pis_scores)}
            n = n_map[scope]
            selected = pis_scores.nsmallest(n, "rank")

            total_vh = max(pis_scores["vehicle_hours_lost_per_day"].sum(), 1)
            vh_saved           = (enforcement_rate / 100) * selected["vehicle_hours_lost_per_day"].sum()
            inr_saved_day      = vh_saved * 150
            inr_saved_year     = inr_saved_day * 365
            violations_prevented = (enforcement_rate / 100) * selected["violation_volume"].sum() * 0.3
            congestion_reduction = vh_saved / total_vh * 100

            # 4 metric cards — dark charcoal background, amber values
            def _dark_metric(label, value, icon=""):
                return (
                    f'<div style="background:{CHARCOAL};border-radius:10px;'
                    f'padding:16px 18px;text-align:center;">'
                    f'<div style="color:#A0A0A0;font-size:11px;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">{icon} {label}</div>'
                    f'<div style="color:{AMBER};font-size:22px;font-weight:700;'
                    f'letter-spacing:-0.5px;">{value}</div>'
                    f'</div>'
                )

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.markdown(_dark_metric("Vehicle-hrs saved / day", f"{vh_saved:,.1f} hrs", "⏱"), unsafe_allow_html=True)
            mc2.markdown(_dark_metric("₹ Saved per day",          f"₹{inr_saved_day:,.0f}", "💰"), unsafe_allow_html=True)
            mc3.markdown(_dark_metric("₹ Saved per year",         f"₹{inr_saved_year:,.0f}", "📈"), unsafe_allow_html=True)
            mc4.markdown(_dark_metric("Congestion reduction",      f"{congestion_reduction:.1f}%", "🚦"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Bar chart: amber selected, grey unselected (top 20 shown)
            chart_df = pis_scores.copy()
            chart_df["selected"] = chart_df["rank"] <= n
            chart_df["colour"] = chart_df["selected"].map({True: AMBER, False: "#DDDDDD"})
            top20_chart = chart_df.head(20)

            fig_bar = go.Figure()
            # Grey bars first (unselected)
            grey_df = top20_chart[~top20_chart["selected"]]
            if not grey_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=grey_df["junction_name"],
                    y=grey_df["PIS"],
                    marker_color="#DDDDDD",
                    name="Not targeted",
                    hovertemplate="%{x}<br>PIS: %{y:.3f}<extra></extra>",
                ))
            # Amber bars (selected)
            amber_df = top20_chart[top20_chart["selected"]]
            if not amber_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=amber_df["junction_name"],
                    y=amber_df["PIS"],
                    marker_color=AMBER,
                    name=f"Targeted (top {n})",
                    hovertemplate="%{x}<br>PIS: %{y:.3f}<extra></extra>",
                ))

            fig_bar.update_layout(
                title=f"Top 20 junctions — {n} targeted (amber) | {officers} officer(s)",
                barmode="overlay",
                paper_bgcolor=SURFACE,
                plot_bgcolor=SURFACE,
                font_family="Inter Tight",
                xaxis=dict(
                    tickangle=-40,
                    title="",
                    gridcolor="#E8E8E6",
                    categoryorder="total descending",
                ),
                yaxis=dict(title="PIS Score", gridcolor="#E8E8E6"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=0, r=0, t=60, b=100),
                height=400,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Amber button → navigate to Patrol Planner
            st.markdown(
                f'<style>.patrol-btn > button {{background-color:{AMBER} !important;'
                f'color:{CHARCOAL} !important;font-weight:700 !important;'
                f'border-radius:8px !important;padding:10px 28px !important;'
                f'font-size:15px !important;border:none !important;'
                f'box-shadow:0 4px 12px rgba(247,181,88,0.35) !important;'
                f'transition:transform 0.15s ease !important;}}'
                f'.patrol-btn > button:hover {{transform:translateY(-2px) !important;}}</style>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="patrol-btn">', unsafe_allow_html=True)
            if st.button("→ Generate Patrol Plan", key="goto_patrol"):
                st.session_state.page = "Patrol Planner"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

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
            tiles=None,
        )
        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name="Street Map",
            max_zoom=19,
            subdomains="abc",
        ).add_to(m2)
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
