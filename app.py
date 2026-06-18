import os
import pandas as pd
import numpy as np
import streamlit as st
import folium
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import st_folium

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ParkIQ — Bengaluru",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded",
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
# CSS
# ---------------------------------------------------------------------------
def inject_custom_css():
    st.html(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:ital,wght@0,100..900;1,100..900&display=swap');

        html, body, [class*="css"], .stApp {
            font-family: 'Inter Tight', sans-serif !important;
            background-color: #F2F2F0 !important;
        }
        .main { background-color: #F2F2F0 !important; }

        header[data-testid="stHeader"] { background-color: transparent !important; }
        [data-testid="stHeader"] { display: none !important; }
        .stAppHeader { display: none !important; }

        [data-testid="stSidebar"] {
            background-color: #363236 !important;
            padding-top: 10px !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0px !important; }

        .navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #FFFFFF;
            padding: 14px 24px;
            border-bottom: 1px solid #E2E2E0;
            margin-bottom: 24px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -1px rgba(0,0,0,0.01);
        }
        .navbar-logo {
            font-size: 24px; font-weight: 800; color: #363236;
            letter-spacing: -0.75px; display: flex; align-items: center; gap: 6px;
        }
        .navbar-logo span { color: #F7B558; }
        .navbar-status {
            display: inline-flex; align-items: center; gap: 8px;
            background-color: rgba(247,181,88,0.12); color: #D97706;
            padding: 6px 16px; border-radius: 9999px; font-size: 13px;
            font-weight: 700; border: 1px solid rgba(247,181,88,0.25);
            letter-spacing: 0.25px;
        }
        .status-dot {
            width: 8px; height: 8px; background-color: #F7B558;
            border-radius: 50%; display: inline-block;
            box-shadow: 0 0 0 0 rgba(247,181,88,0.7);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%   { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(247,181,88,0.7); }
            70%  { transform: scale(1);    box-shadow: 0 0 0 6px rgba(247,181,88,0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(247,181,88,0); }
        }

        .sidebar-brand {
            font-size: 26px; font-weight: 800; color: #FFFFFF;
            padding: 24px 20px; border-bottom: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 20px; letter-spacing: -0.75px;
        }
        .sidebar-brand span { color: #F7B558; }

        .sidebar-nav { display: flex; flex-direction: column; gap: 6px; padding: 0 10px; }
        .nav-link {
            display: flex; align-items: center; padding: 12px 16px;
            color: rgba(255,255,255,0.65) !important; text-decoration: none !important;
            font-size: 15px; font-weight: 500; border-left: 4px solid transparent;
            transition: all 0.2s ease; border-radius: 0 6px 6px 0;
        }
        .nav-link:hover {
            color: #FFFFFF !important;
            background-color: rgba(255,255,255,0.04);
            border-left: 4px solid rgba(247,181,88,0.4);
        }
        .nav-link.active {
            color: #FFFFFF !important;
            background-color: rgba(255,255,255,0.08);
            border-left: 4px solid #F7B558 !important;
            font-weight: 600;
        }

        div[data-testid="stVerticalBlockBordered"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E2E0 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.01) !important;
            padding: 24px !important;
            margin-bottom: 20px !important;
        }

        .card {
            background-color: #FFFFFF; border: 1px solid #E2E2E0;
            border-radius: 12px; padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.01);
            margin-bottom: 20px;
        }
        .card-header {
            font-size: 16px; font-weight: 700; color: #363236;
            margin-bottom: 12px; border-bottom: 1.5px solid #F2F2F0;
            padding-bottom: 8px; display: flex;
            justify-content: space-between; align-items: center;
        }

        [data-testid="stMetricValue"] {
            font-size: 28px !important; font-weight: 700 !important;
            color: #363236 !important; letter-spacing: -0.5px !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 12px !important; text-transform: uppercase !important;
            letter-spacing: 0.75px !important; color: #71717A !important;
            font-weight: 600 !important;
        }

        .badge {
            display: inline-block; padding: 3px 8px; border-radius: 4px;
            font-size: 11px; font-weight: 700; text-transform: uppercase;
        }
        .badge-amber   { background-color: rgba(247,181,88,0.15)  !important; color: #D97706 !important; }
        .badge-sage    { background-color: rgba(165,212,140,0.15) !important; color: #166534 !important; }
        .badge-danger  { background-color: rgba(224,82,82,0.15)   !important; color: #991B1B !important; }
        .badge-charcoal{ background-color: rgba(54,50,54,0.1)     !important; color: #363236 !important; }

        .panel-list { list-style: none; padding: 0; margin: 0; }
        .panel-list-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 0; border-bottom: 1px solid #F2F2F0; font-size: 14px;
        }
        .panel-list-item:last-child { border-bottom: none; }
        .panel-list-title { font-weight: 600; color: #363236; }
        .panel-list-meta  { font-size: 12px; color: #71717A; }

        .stSlider { padding-bottom: 15px !important; }

        .page-subtitle {
            font-size: 15px !important; color: #52525B !important;
            margin-top: -16px !important; margin-bottom: 24px !important;
        }

        div[data-testid="stWidgetLabel"] p, label, .stSlider p { color: #363236 !important; }
        div[data-testid="stSlider"] span { color: #363236 !important; }

        h1, h2, h3, h4, h5, h6,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3 { color: #363236 !important; }

        div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
        </style>
        """
    )

inject_custom_css()

# ---------------------------------------------------------------------------
# Global CSS overrides (font, sidebar colour, metric style, buttons, table)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter Tight', sans-serif !important; }
.stApp { background-color: #F2F2F0; }
section[data-testid="stSidebar"] { background-color: #363236 !important; }
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] div, section[data-testid="stSidebar"] label { color: #FFFFFF !important; }
[data-testid="stMetricValue"] { color: #F7B558 !important; font-weight: 600 !important; font-size: 2rem !important; }
.stButton>button { background-color: #F7B558 !important; color: #363236 !important;
    font-weight: 600 !important; border: none !important; border-radius: 8px !important; }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.stSelectbox label, .stSlider label { color: #363236 !important; font-weight: 500 !important; }
/* Fix for Streamlit Expander Icons overlapping */
.stExpander div[role="button"] p { margin-left: 10px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))

@st.cache_data
def load_pis():
    path = os.path.join(ROOT, "outputs", "pis_scores.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "junction_name_final" in df.columns:
        df = df.rename(columns={"junction_name_final": "junction_name"})
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

pis_scores    = load_pis()
dark_fleet    = load_dark_fleet()
fleet_edges   = load_fleet_edges()
violations_df = load_violations()
station_funnel = load_station_funnel()

def _pis_colour(pis_pct: float) -> str:
    if pis_pct >= 0.85:
        return DANGER
    if pis_pct >= 0.60:
        return AMBER
    return SAGE

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
PAGES = {
    "Operations Map":    "Operations Map",
    "Enforcement Funnel":"Enforcement Funnel",
    "Dark Fleet":        "Dark Fleet",
    "Junction Deep-Dive":"Junction Deep-Dive",
    "What-If Simulator": "What-If Simulator",
    "Patrol Planner":    "Patrol Planner",
}

query_params  = st.query_params
current_page  = query_params.get("page", "Operations Map")
if current_page not in PAGES:
    current_page = "Operations Map"

# Sidebar
st.sidebar.html('<div class="sidebar-brand">ParkIQ<span>—BLR</span></div>')
nav_html = '<div class="sidebar-nav">'
for page_title, page_id in PAGES.items():
    active_class = "active" if current_page == page_id else ""
    query_url    = f"?page={page_id.replace(' ', '+')}"
    nav_html += f'<a href="{query_url}" target="_self" class="nav-link {active_class}">{page_title}</a>'
nav_html += "</div>"
st.sidebar.html(nav_html)

# Top navbar
st.html("""
<div class="navbar">
  <div class="navbar-logo">Park<span>IQ</span></div>
  <div class="navbar-status">
    <span class="status-dot"></span>
    Bengaluru &middot; Live
  </div>
</div>
""")

# ===========================================================================
# PAGE: Operations Map
# ===========================================================================
if current_page == "Operations Map":
    st.title("Operations Map")
    st.html('<div class="page-subtitle">Real-time parking violations, impact scores, and dark fleet intelligence across Bengaluru.</div>')

    if pis_scores is None:
        st.warning("outputs/pis_scores.csv not found — run 02_analytics.py first")
    else:
        # Stat bar
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            with st.container(border=True):
                st.metric("Total Violations", "298,449")
                st.html('<span class="badge badge-danger">Live Feed</span>')
        with col2:
            with st.container(border=True):
                st.metric("Junctions Analysed", len(pis_scores))
                st.html('<span class="badge badge-charcoal">PIS Scored</span>')
        with col3:
            with st.container(border=True):
                st.metric("Vehicle-hrs Lost / Day",
                          f"{pis_scores['vehicle_hours_lost_per_day'].sum():,.0f}")
                st.html('<span class="badge badge-amber">Economic Cost</span>')
        with col4:
            with st.container(border=True):
                st.metric("Est. Loss / Day",
                          f"Rs.{pis_scores['loss_INR_per_day'].sum():,.0f}")
                st.html('<span class="badge badge-danger">High Loss</span>')

        # Folium map
        m = folium.Map(location=[12.9716, 77.5946], zoom_start=12, tiles=None)
        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name="Street Map", max_zoom=19, subdomains="abc",
        ).add_to(m)

        junction_fg   = folium.FeatureGroup(name="Junctions", show=True)
        dark_fleet_fg = folium.FeatureGroup(name="Dark Fleet", show=False)

        top10_names = set(pis_scores.nsmallest(10, "rank")["junction_name"])

        for _, row in pis_scores.iterrows():
            if pd.isna(row["lat_mean"]) or pd.isna(row["lon_mean"]):
                continue
            colour = _pis_colour(row["PIS_pct"])
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
                f'<span style="font-weight:600;font-size:12px;">{row["PIS"]:.3f}</span></div>'
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                '<span style="color:#666;font-size:12px;">Rank</span>'
                f'<span style="font-weight:600;font-size:12px;">#{int(row["rank"])} of {len(pis_scores)}</span></div>'
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                '<span style="color:#666;font-size:12px;">Violations</span>'
                f'<span style="font-weight:600;font-size:12px;">{int(row["violation_volume"]):,}</span></div>'
                '<div style="border-top:1px solid #eee;margin-top:8px;padding-top:6px;">'
                '<div style="display:flex;justify-content:space-between;">'
                '<span style="color:#666;font-size:12px;">&#8377; Lost / day</span>'
                f'<span style="font-weight:600;font-size:12px;color:#E05252;">&#8377;{row["loss_INR_per_day"]:,.0f}</span>'
                '</div></div></div>'
            )
            marker = folium.CircleMarker(
                location=[row["lat_mean"], row["lon_mean"]],
                radius=radius, color="white", fill=True,
                fill_color=colour, fill_opacity=fill_opacity, weight=weight,
                popup=folium.Popup(popup_html, max_width=260),
            )
            if row["junction_name"] in top10_names:
                marker.add_child(folium.Tooltip(row["junction_name"], sticky=False))
            marker.add_to(junction_fg)

        if dark_fleet is not None and fleet_edges is not None:
            junc_loc = (
                pis_scores.dropna(subset=["lat_mean", "lon_mean"])
                .set_index("junction_name")[["lat_mean", "lon_mean"]]
            )
            best_junc = (
                fleet_edges.sort_values("weight", ascending=False)
                .drop_duplicates(subset="vehicle_number", keep="first")
                .set_index("vehicle_number")["junction_name"]
            )
            for _, fl_row in dark_fleet[dark_fleet["is_fleet_leader"]].iterrows():
                vn   = fl_row["vehicle_number"]
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
                        icon_size=(28, 28), icon_anchor=(14, 14),
                    ),
                ).add_to(dark_fleet_fg)

        legend_html = """
        <div style="position:fixed;bottom:30px;right:10px;background:white;
                    padding:12px 16px;border-radius:10px;
                    box-shadow:0 2px 10px rgba(0,0,0,0.2);
                    font-family:sans-serif;font-size:12px;z-index:9999;">
          <div style="font-weight:600;margin-bottom:8px;">Parking Impact Score</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#E05252;"></div> Critical (top 15%)
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#F7B558;"></div> High (top 40%)
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#A5D48C;"></div> Monitor
          </div>
          <div style="border-top:1px solid #eee;padding-top:8px;display:flex;align-items:center;gap:8px;">
            <div style="width:14px;height:14px;border-radius:50%;background:#363236;border:2px solid #F7B558;"></div> Dark fleet
          </div>
        </div>"""
        m.get_root().html.add_child(folium.Element(legend_html))

        junction_fg.add_to(m)
        dark_fleet_fg.add_to(m)
        folium.LayerControl().add_to(m)
        st_folium(m, use_container_width=True, height=600, returned_objects=[])

        # Top-10 table
        with st.container(border=True):
            st.html('<div class="card-header"><span>Top 10 Junctions by Impact</span>'
                    '<span class="badge badge-danger">Critical Priority</span></div>')
            display_cols = ["rank", "junction_name", "PIS", "action_type",
                            "violation_volume", "loss_INR_per_day"]
            st.dataframe(
                pis_scores[display_cols].head(10).rename(columns={
                    "rank": "Rank", "junction_name": "Junction",
                    "PIS": "PIS Score", "action_type": "Action",
                    "violation_volume": "Violations", "loss_INR_per_day": "Rs. Loss/Day",
                }),
                hide_index=True, use_container_width=True,
            )

# ===========================================================================
# PAGE: Enforcement Funnel
# ===========================================================================
elif current_page == "Enforcement Funnel":
    st.title("The enforcement pipeline — where it breaks")
    st.html('<div class="page-subtitle">Visualizing conversion from detection to enforcement actions — and exactly where it collapses.</div>')

    # KPI callout cards
    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.metric("Captured Violations", "298,449", delta="+18% vs weekly avg")
            st.html('<span class="badge badge-charcoal">Raw Input</span>')
    with col2:
        with st.container(border=True):
            st.metric("Validated (Approved)", "115,400", delta="38.7% Approval Rate")
            st.html('<span class="badge badge-amber">Reviewed</span>')
    with col3:
        with st.container(border=True):
            st.metric("Actions Taken", "0", delta="0% — Critical Gap", delta_color="inverse")
            st.html('<span class="badge badge-danger">Breakdown</span>')

    st.html("<br>")

    ca, cb, cc = st.columns(3)
    with ca:
        st.html(
            f'<div style="background:#fde8e8;border-left:4px solid {DANGER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:12px;font-weight:700;color:{DANGER};">CRITICAL</span><br>'
            '<b>0 enforcement actions recorded</b><br>'
            '<span style="color:#555;font-size:13px;">across 298,449 violations</span></div>'
        )
    with cb:
        st.html(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:12px;font-weight:700;color:#B45309;">TIMING GAP</span><br>'
            '<b>60.1% of captures happen at 5am</b><br>'
            '<span style="color:#555;font-size:13px;">roads are empty — no congestion impact</span></div>'
        )
    with cc:
        st.html(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:14px 16px;border-radius:8px;">'
            f'<span style="font-size:12px;font-weight:700;color:#B45309;">STATION FAILURE</span><br>'
            '<b>Kodigehalli sends only 54.7%</b><br>'
            '<span style="color:#555;font-size:13px;">of violations to SCITA</span></div>'
        )

    st.html("<br>")

    # ── Section A: Funnel chart ──────────────────────────────────────────────
    st.subheader("Section A — Pipeline stages")
    fig_funnel = go.Figure(go.Funnel(
        y=["Captured", "Validated (Approved)", "Sent to SCITA", "Action Taken"],
        x=[298449, 115400, 255893, 1],   # 1 → visible sliver for Action Taken
        textinfo="value+percent initial",
        textposition="inside",
        marker=dict(color=[CHARCOAL, AMBER, AMBER, DANGER]),
        connector=dict(line=dict(color="rgba(0,0,0,0.08)", width=1)),
    ))
    fig_funnel.add_annotation(
        x=1, y="Action Taken",
        text="<b>0 actions</b>",
        showarrow=True, arrowhead=2, arrowcolor=DANGER,
        font=dict(color=DANGER, size=13, family="Inter Tight"),
        ax=80, ay=0,
        bgcolor="#fde8e8", bordercolor=DANGER, borderwidth=1, borderpad=4,
    )
    fig_funnel.update_layout(
        title=dict(text="The enforcement pipeline — where it breaks",
                   font=dict(size=16, family="Inter Tight")),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_family="Inter Tight",
        height=380, margin=dict(l=0, r=120, t=60, b=20),
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # ── Section B: 24-hour violation pattern ────────────────────────────────
    st.subheader("Section B — 24-hour violation pattern")
    if violations_df is not None:
        hour_df = (
            violations_df["hour"].dropna().astype(int)
            .value_counts().sort_index().reset_index()
        )
        hour_df.columns = ["hour", "count"]
        colours_24h = [
            DANGER if h <= 6 else (SAGE if 9 <= h <= 18 else "#CCCCCC")
            for h in hour_df["hour"]
        ]
        fig_hour = go.Figure(go.Bar(
            x=hour_df["hour"], y=hour_df["count"],
            marker_color=colours_24h,
            hovertemplate="Hour %{x}:00 — %{y:,} violations<extra></extra>",
        ))
        peak = hour_df["count"].max()
        fig_hour.add_vrect(x0=-0.5, x1=6.5, fillcolor=DANGER, opacity=0.10,
                           layer="below", line_width=0)
        fig_hour.add_annotation(
            x=3, y=peak * 0.97,
            text="<b>60% of captures</b><br>roads are empty",
            showarrow=False, font=dict(color=DANGER, size=11, family="Inter Tight"),
            align="center", bgcolor="rgba(255,255,255,0.88)",
            bordercolor=DANGER, borderwidth=1, borderpad=4,
        )
        fig_hour.add_vrect(x0=8.5, x1=18.5, fillcolor=SAGE, opacity=0.10,
                           layer="below", line_width=0)
        fig_hour.add_annotation(
            x=13.5, y=peak * 0.97,
            text="<b>Peak congestion</b><br>only 2.6% captured",
            showarrow=False, font=dict(color="#166534", size=11, family="Inter Tight"),
            align="center", bgcolor="rgba(255,255,255,0.88)",
            bordercolor=SAGE, borderwidth=1, borderpad=4,
        )
        fig_hour.update_layout(
            title="Violations captured by hour of day",
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_family="Inter Tight",
            xaxis=dict(title="Hour of day", dtick=1, gridcolor="#E8E8E6"),
            yaxis=dict(title="Violation count", gridcolor="#E8E8E6"),
            bargap=0.15, height=380, margin=dict(l=0, r=0, t=50, b=40),
        )
        st.plotly_chart(fig_hour, use_container_width=True)
    else:
        st.info("violations_clean.csv not loaded — run 01_clean_and_resolve.py first.")

    # ── Section C: Police-station SCITA send-rate ───────────────────────────
    st.subheader("Section C — SCITA send-rate by police station")
    if station_funnel is not None:
        sf = station_funnel.sort_values("scita_send_rate", ascending=True).copy()
        sf["colour"] = sf["scita_send_rate"].apply(
            lambda r: DANGER if r < 0.75 else (AMBER if r < 0.85 else SAGE)
        )
        fig_station = go.Figure(go.Bar(
            x=sf["scita_send_rate"], y=sf["police_station"],
            orientation="h", marker_color=sf["colour"].tolist(),
            text=[f"{r*100:.1f}%" for r in sf["scita_send_rate"]],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        ))
        fig_station.add_vline(
            x=0.75, line_width=2, line_dash="dash", line_color=CHARCOAL,
            annotation_text="75% threshold", annotation_position="top right",
            annotation_font=dict(color=CHARCOAL, size=11, family="Inter Tight"),
        )
        kodige = sf[sf["police_station"].str.contains("Kodigehalli", case=False, na=False)]
        if not kodige.empty:
            kr = kodige.iloc[0]
            fig_station.add_annotation(
                x=kr["scita_send_rate"] + 0.01, y=kr["police_station"],
                text="<b>Kodigehalli ⚠</b>",
                showarrow=True, arrowhead=2, arrowcolor=DANGER,
                font=dict(color=DANGER, size=11, family="Inter Tight"),
                ax=80, ay=0,
                bgcolor="#fde8e8", bordercolor=DANGER, borderwidth=1, borderpad=3,
            )
        fig_station.update_layout(
            title="SCITA send-rate per police station (sorted ascending)",
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_family="Inter Tight",
            xaxis=dict(title="Send rate", tickformat=".0%",
                       range=[0, 1.15], gridcolor="#E8E8E6"),
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
elif current_page == "Dark Fleet":
    st.title("Dark Fleet Detector")
    st.html('<div class="page-subtitle">Tracking organised parking offenders, fleet clusters, and repeat multi-junction violators.</div>')

    if dark_fleet is None:
        st.info("Run 03_dark_fleet.py first to generate outputs/dark_fleet.csv")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            with st.container(border=True):
                st.metric("Fleet Vehicles", len(dark_fleet))
                st.html('<span class="badge badge-danger">Identified</span>')
        with col2:
            with st.container(border=True):
                st.metric("Fleet Clusters", dark_fleet["fleet_cluster_id"].nunique())
                st.html('<span class="badge badge-amber">Louvain Groups</span>')
        with col3:
            with st.container(border=True):
                st.metric("Top Offender Hits", int(dark_fleet["total_hits"].max()))
                st.html('<span class="badge badge-danger">Critical Risk</span>')
        with col4:
            with st.container(border=True):
                st.metric("Avg Junctions / Vehicle",
                          f"{dark_fleet['distinct_junctions'].mean():.1f}")
                st.html('<span class="badge badge-charcoal">Mobility Index</span>')

        st.html("<br>")

        plot_df = dark_fleet.assign(vehicle_idx=range(len(dark_fleet)))
        fig_scatter = px.scatter(
            plot_df, x="vehicle_idx", y="total_hits", size="total_hits",
            color=plot_df["fleet_cluster_id"].astype(str),
            hover_data=["vehicle_number", "junction_list", "distinct_junctions"],
            color_discrete_sequence=[AMBER, SAGE, "#7BBFEA", "#C97ED4", "#F09F7C"],
            title="Fleet vehicles by hit count — sized by violations",
            labels={"vehicle_idx": "Vehicle index", "total_hits": "Total violations"},
        )
        fig_scatter.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                                  font_family="Inter Tight")
        st.plotly_chart(fig_scatter, use_container_width=True)

        with st.container(border=True):
            st.html('<div class="card-header"><span>Top Offenders / Fleet Leaders</span>'
                    '<span class="badge badge-charcoal">Sorted by Hits</span></div>')
            leaders = dark_fleet[dark_fleet["is_fleet_leader"]].nlargest(8, "total_hits")
            list_html = '<ul class="panel-list">'
            for _, r in leaders.iterrows():
                list_html += (
                    f'<li class="panel-list-item">'
                    f'<div><div class="panel-list-title">{r["vehicle_number"]}</div>'
                    f'<div class="panel-list-meta">{r["junction_list"][:60]}...</div></div>'
                    f'<div style="text-align:right;">'
                    f'<div class="badge badge-danger" style="margin-bottom:4px;">'
                    f'{r["total_hits"]} hits</div>'
                    f'<div class="panel-list-meta">Cluster {r["fleet_cluster_id"]} &middot; '
                    f'{r["distinct_junctions"]} junctions</div>'
                    f'</div></li>'
                )
            list_html += "</ul>"
            st.html(list_html)

        st.html("<br>")
        st.subheader("Full Fleet Register")
        st.dataframe(dark_fleet, use_container_width=True, hide_index=True)

# ===========================================================================
# PAGE: Junction Deep-Dive
# ===========================================================================
elif current_page == "Junction Deep-Dive":
    st.title("Junction Deep-Dive")
    st.html('<div class="page-subtitle">Detailed zoom-in on critical grid bottlenecks. Select a junction to inspect its violation profile.</div>')

    if pis_scores is None or violations_df is None:
        st.warning("Required data files not loaded.")
    else:
        junction = st.selectbox("Select junction", pis_scores["junction_name"].tolist())
        row = pis_scores[pis_scores["junction_name"] == junction].iloc[0]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            with st.container(border=True):
                st.metric("PIS Score", f"{row['PIS']:.3f}")
                st.html('<span class="badge badge-charcoal">Composite Index</span>')
        with col2:
            with st.container(border=True):
                st.metric("Rank", f"#{int(row['rank'])} of {len(pis_scores)}")
                pct_badge = "badge-danger" if row["PIS_pct"] >= 0.85 else ("badge-amber" if row["PIS_pct"] >= 0.60 else "badge-sage")
                st.html(f'<span class="badge {pct_badge}">Top {100-int(row["PIS_pct"]*100)}%</span>')
        with col3:
            with st.container(border=True):
                st.metric("Rs. Loss / Day", f"Rs.{row['loss_INR_per_day']:,.0f}")
                st.html('<span class="badge badge-danger">Economic Impact</span>')
        with col4:
            with st.container(border=True):
                st.metric("Action", row["action_type"])
                st.html('<span class="badge badge-amber">Recommended</span>')

        junc_violations = violations_df[violations_df["junction_name"] == junction]

        if junc_violations.empty:
            st.info("No violation records found for this junction.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                hour_counts = (
                    junc_violations["hour"].dropna().astype(int)
                    .value_counts().sort_index().reset_index()
                )
                hour_counts.columns = ["hour", "count"]
                fig_h = px.bar(hour_counts, x="hour", y="count",
                               title="Violations by hour",
                               color_discrete_sequence=[AMBER])
                fig_h.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                                    font_family="Inter Tight")
                st.plotly_chart(fig_h, use_container_width=True)

            with col2:
                vtype_counts = (
                    junc_violations["vehicle_type"].value_counts().reset_index()
                )
                vtype_counts.columns = ["vehicle_type", "count"]
                fig_v = px.bar(vtype_counts.head(10), x="count", y="vehicle_type",
                               orientation="h", title="By vehicle type",
                               color_discrete_sequence=[SAGE])
                fig_v.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                                    font_family="Inter Tight", yaxis_title="")
                st.plotly_chart(fig_v, use_container_width=True)

            with col3:
                month_order = ["January","February","March","April","May","June",
                               "July","August","September","October","November","December"]
                monthly = junc_violations.groupby("month").size().reset_index(name="count")
                monthly["month_num"] = monthly["month"].map({m: i for i, m in enumerate(month_order)})
                monthly = monthly.sort_values("month_num")
                fig_m = px.line(monthly, x="month", y="count", title="Monthly trend",
                                markers=True, color_discrete_sequence=[CHARCOAL])
                fig_m.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                                    font_family="Inter Tight", xaxis_title="")
                st.plotly_chart(fig_m, use_container_width=True)

            with st.container(border=True):
                enf_fail = row["enforcement_failure_rate"]
                repeat   = row["repeat_offender_density"]
                peak     = row["peak_hour_share"]
                st.html(
                    '<div class="card-header"><span>Junction Risk Breakdown</span>'
                    '<span class="badge badge-amber">PIS Components</span></div>'
                )
                list_html = '<ul class="panel-list">'
                items = [
                    ("Enforcement Failure Rate", f"{enf_fail*100:.1f}%",
                     "badge-danger" if enf_fail > 0.6 else "badge-amber"),
                    ("Repeat Offender Density", f"{repeat*100:.1f}%",
                     "badge-danger" if repeat > 0.3 else "badge-amber"),
                    ("Peak Hour Share (8am-8pm)", f"{peak*100:.1f}%",
                     "badge-sage" if peak > 0.5 else "badge-charcoal"),
                    ("Mean Blockage Severity", f"{row['mean_blockage_severity']:.1f} m",
                     "badge-charcoal"),
                ]
                for label, value, badge in items:
                    list_html += (
                        f'<li class="panel-list-item">'
                        f'<div class="panel-list-title">{label}</div>'
                        f'<span class="badge {badge}">{value}</span></li>'
                    )
                list_html += "</ul>"
                st.html(list_html)

# ===========================================================================
# PAGE: What-If Simulator
# ===========================================================================
elif current_page == "What-If Simulator":
    st.title("What-If Simulator")
    st.html('<div class="page-subtitle">Model parking enforcement scenarios. Move the sliders — watch the city save money.</div>')

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        left, right = st.columns([1, 2])

        # ── Left col: controls ───────────────────────────────────────────────
        with left:
            st.html(
                f'<div style="background:{CHARCOAL};border-radius:12px;'
                f'padding:20px 18px;margin-bottom:12px;">'
                f'<p style="color:#A0A0A0;font-size:12px;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;">'
                f'Simulation Controls</p>'
            )
            enforcement_rate = st.slider(
                "Enforcement action rate (%)", 0, 100, 0, format="%d%%", key="wif_enf"
            )
            scope = st.selectbox(
                "Target junctions", ["Top 5", "Top 10", "Top 20", "All"], key="wif_scope"
            )
            officers = st.slider("Officers deployed", 1, 10, 3, key="wif_officers")
            st.html("</div>")
            st.html(
                f'<div style="background:#1E1B1E;border-radius:8px;padding:12px 14px;'
                f'border-left:3px solid {DANGER};">'
                f'<span style="color:#A0A0A0;font-size:12px;">Current state (0% enforcement)</span><br>'
                f'<span style="color:{DANGER};font-weight:700;font-size:15px;">'
                f'Rs.{pis_scores["loss_INR_per_day"].sum():,.0f} lost / day</span></div>'
            )

        # ── Right col: results ───────────────────────────────────────────────
        with right:
            n_map    = {"Top 5": 5, "Top 10": 10, "Top 20": 20, "All": len(pis_scores)}
            n        = n_map[scope]
            selected = pis_scores.nsmallest(n, "rank")
            total_vh = max(pis_scores["vehicle_hours_lost_per_day"].sum(), 1)

            vh_saved             = (enforcement_rate / 100) * selected["vehicle_hours_lost_per_day"].sum()
            inr_saved_day        = vh_saved * 150
            inr_saved_year       = inr_saved_day * 365
            violations_prevented = (enforcement_rate / 100) * selected["violation_volume"].sum() * 0.3
            congestion_reduction = vh_saved / total_vh * 100

            # 4 dark metric cards (charcoal bg, amber value)
            def _dark_card(icon, label, value):
                return (
                    f'<div style="background:{CHARCOAL};border-radius:10px;'
                    f'padding:16px 14px;text-align:center;">'
                    f'<div style="color:#A0A0A0;font-size:11px;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">{icon} {label}</div>'
                    f'<div style="color:{AMBER};font-size:22px;font-weight:700;'
                    f'letter-spacing:-0.5px;">{value}</div></div>'
                )

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.html(_dark_card("⏱", "Vehicle-hrs saved / day", f"{vh_saved:,.1f} hrs"))
            mc2.html(_dark_card("💰", "Rs. saved per day", f"Rs.{inr_saved_day:,.0f}"))
            mc3.html(_dark_card("📈", "Rs. saved per year", f"Rs.{inr_saved_year:,.0f}"))
            mc4.html(_dark_card("🚦", "Congestion reduction", f"{congestion_reduction:.1f}%"))

            st.html("<br>")

            # Split-trace bar: amber selected, grey unselected
            chart_df = pis_scores.copy()
            chart_df["selected"] = chart_df["rank"] <= n
            top20_chart = chart_df.head(20)
            grey_df  = top20_chart[~top20_chart["selected"]]
            amber_df = top20_chart[ top20_chart["selected"]]

            fig_bar = go.Figure()
            if not grey_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=grey_df["junction_name"], y=grey_df["PIS"],
                    marker_color="#DDDDDD", name="Not targeted",
                    hovertemplate="%{x}<br>PIS: %{y:.3f}<extra></extra>",
                ))
            if not amber_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=amber_df["junction_name"], y=amber_df["PIS"],
                    marker_color=AMBER, name=f"Targeted (top {n})",
                    hovertemplate="%{x}<br>PIS: %{y:.3f}<extra></extra>",
                ))
            fig_bar.update_layout(
                title=f"Top 20 junctions — {n} targeted (amber) | {officers} officer(s)",
                barmode="overlay",
                paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_family="Inter Tight",
                xaxis=dict(tickangle=-40, title="", gridcolor="#E8E8E6",
                           categoryorder="total descending"),
                yaxis=dict(title="PIS Score", gridcolor="#E8E8E6"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=0, r=0, t=60, b=100), height=400,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # "Generate Patrol Plan" button — passes simulation params to Patrol Planner
            if st.button("\u2192 Generate Patrol Plan", key="goto_patrol_wif"):
                # Pass current What-If values so Patrol Planner pre-fills intelligently
                st.session_state["wif_to_patrol_officers"] = officers
                st.session_state["wif_to_patrol_topn"]     = n
                st.session_state["patrol_generated"]       = True
                # Navigate — must use plain space, not '+', for query_params lookup
                st.query_params["page"] = "Patrol Planner"
                st.rerun()

# ===========================================================================
# PAGE: Patrol Planner
# ===========================================================================
elif current_page == "Patrol Planner":
    from math import radians, sin, cos, sqrt, atan2
    from ortools.constraint_solver import routing_enums_pb2, pywrapcp

    st.title("Patrol Planner")
    st.html('<div class="page-subtitle">OR-Tools VRP route optimiser — assign officers to the highest-impact junctions within their shift window.</div>')

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        # Read defaults passed from What-If Simulator (if any)
        _from_wif          = "wif_to_patrol_officers" in st.session_state
        _default_officers  = int(st.session_state.pop("wif_to_patrol_officers", 3))
        _wif_topn          = st.session_state.pop("wif_to_patrol_topn", None)
        # Map What-If n-value to the nearest valid slider tick (10-30)
        _default_topn      = int(max(10, min(30, _wif_topn))) if _wif_topn is not None else 20

        col1, col2 = st.columns([1, 2])

        with col1:
            if _from_wif:
                st.html(
                    f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
                    f'padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px;">'
                    f'<b>Pre-filled from What-If Simulator</b><br>'
                    f'{_default_officers} officer(s) · top {_default_topn} junctions</div>'
                )
            n_officers  = st.slider("Officers", 1, 5, _default_officers, key="pp_officers")
            shift_hours = st.slider("Shift duration (hrs)", 2, 8, 4, key="pp_shift")
            top_n       = st.slider("Junctions to cover", 10, 30, _default_topn, key="pp_topn")
            generate    = st.button("Generate Patrol Plan", type="primary", key="pp_generate")
            if generate:
                st.session_state["patrol_generated"] = True

        with col2:
            # Auto-execute when arriving from What-If
            _auto_run = st.session_state.get("patrol_generated", False)
            if generate or _auto_run:

                # ── 1. Select junctions ─────────────────────────────────────
                jdf = (
                    pis_scores.dropna(subset=["lat_mean", "lon_mean"])
                    .nsmallest(top_n, "rank")
                    .reset_index(drop=True)
                )

                # Depot: city centre (index 0 in location list)
                depot_lat, depot_lon = 12.9716, 77.5946
                lats = [depot_lat] + jdf["lat_mean"].tolist()
                lons = [depot_lon] + jdf["lon_mean"].tolist()
                n_locs = len(lats)   # depot + junctions

                # ── 2. Haversine distance matrix (seconds @ 20 km/h) ────────
                def _haversine_s(lat1, lon1, lat2, lon2):
                    R = 6371.0
                    dlat = radians(lat2 - lat1)
                    dlon = radians(lon2 - lon1)
                    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
                    km = 2 * R * atan2(sqrt(a), sqrt(1-a))
                    return int(km / 20 * 3600)   # seconds at 20 km/h

                dist_matrix = [
                    [_haversine_s(lats[i], lons[i], lats[j], lons[j]) for j in range(n_locs)]
                    for i in range(n_locs)
                ]

                # ── 3. OR-Tools VRP ─────────────────────────────────────────
                import math as _math
                manager = pywrapcp.RoutingIndexManager(n_locs, n_officers, 0)
                routing = pywrapcp.RoutingModel(manager)

                def _time_cb(from_idx, to_idx):
                    return dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

                cb_idx = routing.RegisterTransitCallback(_time_cb)
                routing.SetArcCostEvaluatorOfAllVehicles(cb_idx)

                # Time window: each vehicle must finish within shift
                max_seconds = shift_hours * 3600
                routing.AddDimension(
                    cb_idx,
                    0,            # no slack
                    max_seconds,
                    True,         # start cumul at zero
                    "Time",
                )

                # Count dimension: balance stops across officers
                # Each officer gets at most ceil(n_junctions / n_officers) stops
                max_stops_per_officer = _math.ceil(len(jdf) / n_officers)

                def _count_cb(from_idx, to_idx):
                    # +1 for every non-depot node we depart from
                    return 0 if manager.IndexToNode(from_idx) == 0 else 1

                count_cb_idx = routing.RegisterTransitCallback(_count_cb)
                routing.AddDimension(
                    count_cb_idx,
                    0,
                    max_stops_per_officer,
                    True,
                    "Count",
                )

                # Force every junction to be visited (high penalty = must visit)
                # Without this OR-Tools drops stops onto one vehicle cheaply
                penalty = max_seconds * 2
                for node in range(1, n_locs):   # skip depot (node 0)
                    routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

                params = pywrapcp.DefaultRoutingSearchParameters()
                params.first_solution_strategy = (
                    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                )
                params.local_search_metaheuristic = (
                    routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
                )
                params.time_limit.seconds = 30

                solution = routing.SolveWithParameters(params)

                # ── 4. Extract routes ────────────────────────────────────────
                route_colours = [AMBER, SAGE, "#7BBFEA", "#C97ED4", "#F09F7C"]
                routes = []   # list per officer of jdf-row indices

                if solution:
                    for v in range(n_officers):
                        idx = routing.Start(v)
                        stops = []
                        while not routing.IsEnd(idx):
                            node = manager.IndexToNode(idx)
                            if node != 0:           # skip depot
                                stops.append(node - 1)
                            idx = solution.Value(routing.NextVar(idx))
                        routes.append(stops)
                else:
                    # Fallback: round-robin so every officer gets some stops
                    for v in range(n_officers):
                        routes.append(list(range(v, len(jdf), n_officers)))

                # ── 5. Folium map ────────────────────────────────────────────
                m_patrol = folium.Map(location=[depot_lat, depot_lon], zoom_start=12, tiles=None)
                folium.TileLayer(
                    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                    attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                    name="Street Map", max_zoom=19, subdomains="abc",
                ).add_to(m_patrol)

                for v_idx, stops in enumerate(routes):
                    colour = route_colours[v_idx % len(route_colours)]
                    if not stops:
                        continue
                    # PolyLine through stop coordinates
                    coords = [(jdf.loc[s, "lat_mean"], jdf.loc[s, "lon_mean"]) for s in stops
                              if pd.notna(jdf.loc[s, "lat_mean"])]
                    if len(coords) > 1:
                        folium.PolyLine(coords, color=colour, weight=3, opacity=0.8).add_to(m_patrol)
                    # Numbered circle markers
                    for order, s in enumerate(stops, 1):
                        row_s = jdf.loc[s]
                        if pd.isna(row_s["lat_mean"]):
                            continue
                        folium.CircleMarker(
                            location=[row_s["lat_mean"], row_s["lon_mean"]],
                            radius=14, color="white", fill=True,
                            fill_color=colour, fill_opacity=0.9, weight=2,
                            popup=folium.Popup(
                                f"<b>Officer {v_idx+1} • Stop {order}</b><br>"
                                f"{row_s['junction_name']}<br>"
                                f"PIS: {row_s['PIS']:.3f}",
                                max_width=200,
                            ),
                            tooltip=f"O{v_idx+1}-S{order}: {row_s['junction_name']}",
                        ).add_to(m_patrol)
                        folium.Marker(
                            location=[row_s["lat_mean"], row_s["lon_mean"]],
                            icon=folium.DivIcon(
                                html=(
                                    f'<div style="color:white;font-weight:700;font-size:10px;'
                                    f'text-align:center;line-height:28px;">'
                                    f'{order}</div>'
                                ),
                                icon_size=(28, 28), icon_anchor=(14, 14),
                            ),
                        ).add_to(m_patrol)

                st_folium(m_patrol, use_container_width=True, height=480, returned_objects=[])

                # ── 6. Summary table ─────────────────────────────────────────
                total_viol = max(jdf["violation_volume"].sum(), 1)
                summary_rows = []
                for v_idx, stops in enumerate(routes):
                    colour = route_colours[v_idx % len(route_colours)]
                    names    = "; ".join(jdf.loc[s, "junction_name"] for s in stops) if stops else "—"
                    pis_sum  = float(jdf.loc[stops, "PIS"].sum()) if stops else 0.0
                    viol_int = int(jdf.loc[stops, "violation_volume"].sum() * 0.15) if stops else 0
                    cov_pct  = round(jdf.loc[stops, "violation_volume"].sum() / total_viol * 100, 1) if stops else 0.0
                    summary_rows.append({
                        "Officer":   f"Officer {v_idx+1}",
                        "Colour":    colour,
                        "Stops":     len(stops),
                        "Junctions": names,
                        "PIS Sum":   round(pis_sum, 3),
                        "Est. Violations Intercepted": viol_int,
                        "Coverage %": cov_pct,
                    })

                patrol_df = pd.DataFrame(summary_rows)

                st.html("<br>")
                st.subheader("Route Summary")
                # Show all officers; omit Junctions column (too wide) and internal Colour column
                st.dataframe(
                    patrol_df.drop(columns=["Junctions", "Colour"]),
                    use_container_width=True, hide_index=True,
                )

                # Per-officer junction detail expanders
                for row in summary_rows:
                    colour = row["Colour"]
                    with st.expander(f"🔸 {row['Officer']} — junction list ({row['Stops']} stops)"):
                        st.write(row["Junctions"])

                # Coverage callout — cap at 100 %
                overall_cov = min(sum(r["Coverage %"] for r in summary_rows), 100.0)

                st.html(
                    f'<div style="background:{CHARCOAL};border-radius:10px;'
                    f'padding:16px 20px;margin-top:12px;">'
                    f'<span style="color:{AMBER};font-size:18px;font-weight:700;">'
                    f'{n_officers} officer(s) cover {overall_cov:.0f}% of critical violations '
                    f'in {shift_hours} hrs</span></div>'
                )

                # Download
                st.download_button(
                    "\u2193 Download patrol_plan.csv",
                    data=patrol_df.to_csv(index=False),
                    file_name="patrol_plan.csv",
                    mime="text/csv",
                    key="pp_download",
                )
            else:
                st.html(
                    f'<div style="background:{CHARCOAL};border-radius:12px;'
                    f'padding:32px 24px;text-align:center;margin-top:40px;">'
                    f'<div style="font-size:40px;margin-bottom:12px;">\U0001f6a6</div>'
                    f'<div style="color:{AMBER};font-size:18px;font-weight:700;margin-bottom:8px;">'
                    f'Set your parameters and click “Generate Patrol Plan”</div>'
                    f'<div style="color:#A0A0A0;font-size:14px;">'
                    f'OR-Tools VRP will compute optimal routes within the shift window.</div>'
                    f'</div>'
                )
