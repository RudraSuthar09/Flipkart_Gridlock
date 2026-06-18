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
    st.title("Enforcement Funnel")
    st.html('<div class="page-subtitle">Visualizing conversion from detection algorithms to enforcement actions — and where it collapses.</div>')

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

    # Callout boxes
    ca, cb, cc = st.columns(3)
    with ca:
        st.html(
            f'<div style="background:#fde8e8;border-left:4px solid {DANGER};'
            f'padding:12px;border-radius:8px;">'
            '<b>0 enforcement actions recorded</b><br>across 298,449 violations</div>'
        )
    with cb:
        st.html(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:12px;border-radius:8px;">'
            '<b>60.1% of captures happen at 5am</b><br>roads are empty</div>'
        )
    with cc:
        st.html(
            f'<div style="background:#fef5e7;border-left:4px solid {AMBER};'
            f'padding:12px;border-radius:8px;">'
            '<b>Kodigehalli sends only 54.7%</b><br>of violations to SCITA</div>'
        )

    st.html("<br>")

    # Funnel chart
    fig_funnel = go.Figure(go.Funnel(
        y=["Captured", "Validated (Approved)", "Sent to SCITA", "Action Taken"],
        x=[298449, 115400, 255893, 1],
        textinfo="value+percent initial",
        marker=dict(color=[CHARCOAL, AMBER, AMBER, DANGER]),
    ))
    fig_funnel.update_layout(
        title="The 4-stage enforcement pipeline",
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_family="Inter Tight",
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # 24-hour bar chart
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
        fig_hour = px.bar(hour_df, x="hour", y="count", title="Violations by hour of day")
        fig_hour.update_traces(marker_color=colours_24h)
        fig_hour.add_vrect(x0=-0.5, x1=6.5, fillcolor=DANGER, opacity=0.08,
                           annotation_text="60% captured here (0-6am)",
                           annotation_position="top left")
        fig_hour.add_vrect(x0=8.5, x1=18.5, fillcolor=SAGE, opacity=0.08,
                           annotation_text="Peak congestion (9am-6pm)",
                           annotation_position="top right")
        fig_hour.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                               font_family="Inter Tight",
                               xaxis_title="Hour of day", yaxis_title="Violations")
        st.plotly_chart(fig_hour, use_container_width=True)

    # Station funnel breakdown
    if station_funnel is not None:
        with st.container(border=True):
            st.html('<div class="card-header"><span>SCITA Send Rate by Police Station</span>'
                    '<span class="badge badge-amber">Station Level</span></div>')
            flagged = station_funnel[station_funnel["low_scita_flag"]]
            list_html = '<ul class="panel-list">'
            for _, r in station_funnel.sort_values("scita_send_rate").head(10).iterrows():
                badge = "badge-danger" if r["low_scita_flag"] else "badge-sage"
                label = "Below 75%" if r["low_scita_flag"] else "OK"
                list_html += (
                    f'<li class="panel-list-item">'
                    f'<div><div class="panel-list-title">{r["police_station"]}</div>'
                    f'<div class="panel-list-meta">{r["total_records"]:,} total records</div></div>'
                    f'<div style="text-align:right;">'
                    f'<div class="badge {badge}" style="margin-bottom:4px;">{label}</div>'
                    f'<div class="panel-list-meta">{r["scita_send_rate"]*100:.1f}% sent</div>'
                    f'</div></li>'
                )
            list_html += "</ul>"
            st.html(list_html)

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
        with st.container(border=True):
            st.html('<div class="card-header"><span>Simulation Controls</span>'
                    '<span class="badge badge-charcoal">Scenarios</span></div>')
            col_ctrl1, col_ctrl2 = st.columns(2)
            with col_ctrl1:
                enforcement_rate = st.slider("Enforcement action rate (%)", 0, 100, 0, format="%d%%")
                scope = st.selectbox("Target junctions", ["Top 5", "Top 10", "Top 20", "All"])
            with col_ctrl2:
                st.html(
                    f'<div style="padding:12px;background:#fef5e7;border-radius:8px;'
                    f'border-left:4px solid {AMBER};margin-top:8px;">'
                    f'<b>Current state</b><br>'
                    f'0% enforcement = Rs.{pis_scores["loss_INR_per_day"].sum():,.0f} lost daily'
                    f'</div>'
                )

        n_map = {"Top 5": 5, "Top 10": 10, "Top 20": 20, "All": len(pis_scores)}
        n        = n_map[scope]
        selected = pis_scores.nsmallest(n, "rank")
        vh_saved       = (enforcement_rate / 100) * selected["vehicle_hours_lost_per_day"].sum()
        inr_day        = vh_saved * 150
        inr_year       = inr_day * 365
        total_vh       = max(pis_scores["vehicle_hours_lost_per_day"].sum(), 1)
        congestion_pct = vh_saved / total_vh * 100

        st.subheader("Model Projections")
        rc1, rc2, rc3, rc4 = st.columns(4)
        with rc1:
            with st.container(border=True):
                st.metric("Hrs Saved / Day", f"{vh_saved:,.1f}")
                st.html('<span class="badge badge-sage">Time Recovered</span>')
        with rc2:
            with st.container(border=True):
                st.metric("Rs. Saved / Day", f"Rs.{inr_day:,.0f}")
                st.html('<span class="badge badge-sage">Daily Saving</span>')
        with rc3:
            with st.container(border=True):
                st.metric("Rs. Saved / Year", f"Rs.{inr_year:,.0f}")
                st.html('<span class="badge badge-sage">Annual Saving</span>')
        with rc4:
            with st.container(border=True):
                st.metric("Congestion Drop", f"{congestion_pct:.1f}%")
                st.html('<span class="badge badge-amber">Projected</span>')

        chart_df = pis_scores.copy()
        chart_df["selected"] = chart_df["rank"] <= n
        chart_df["colour"]   = chart_df["selected"].map({True: AMBER, False: "#DDDDDD"})
        top20_chart = chart_df.head(20)
        fig_bar = px.bar(top20_chart, x="junction_name", y="PIS",
                         title=f"Top 20 junctions — {n} targeted (amber)")
        fig_bar.update_traces(marker_color=top20_chart["colour"].tolist())
        fig_bar.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                              font_family="Inter Tight", xaxis_tickangle=-45,
                              xaxis_title="", yaxis_title="PIS Score")
        st.plotly_chart(fig_bar, use_container_width=True)

# ===========================================================================
# PAGE: Patrol Planner
# ===========================================================================
elif current_page == "Patrol Planner":
    st.title("Patrol Planner")
    st.html('<div class="page-subtitle">AI-assisted dispatch routes and scheduling for ward officers based on historical blockages.</div>')

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.metric("Active Patrol Sectors", "12 Sectors", delta="Full Coverage")
            st.html('<span class="badge badge-sage">Broad Reach</span>')
    with col2:
        with st.container(border=True):
            st.metric("Avg Dispatch Response", "6.4 mins", delta="-1.2 mins vs peak avg")
            st.html('<span class="badge badge-sage">Fast Response</span>')
    with col3:
        with st.container(border=True):
            st.metric("Coverage Efficiency", "92.1%", delta="+3.4% this week")
            st.html('<span class="badge badge-sage">Highly Efficient</span>')

    if pis_scores is None:
        st.warning("PIS scores not loaded.")
    else:
        with st.container(border=True):
            st.html('<div class="card-header"><span>Priority Junctions for Patrol</span>'
                    '<span class="badge badge-danger">Top 20 by PIS</span></div>')
            top20 = pis_scores.head(20)[["rank", "junction_name", "action_type",
                                         "violation_volume", "loss_INR_per_day",
                                         "lat_mean", "lon_mean"]]
            st.dataframe(top20.rename(columns={
                "rank": "Rank", "junction_name": "Junction",
                "action_type": "Action", "violation_volume": "Violations",
                "loss_INR_per_day": "Rs. Loss/Day",
            }), use_container_width=True, hide_index=True)

        m2 = folium.Map(location=[12.9716, 77.5946], zoom_start=12, tiles=None)
        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name="Street Map", max_zoom=19, subdomains="abc",
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
                            f'font-weight:600;font-size:11px;border:2px solid white;">'
                            f'{int(row["rank"])}</div>'
                        ),
                        icon_size=(24, 24), icon_anchor=(12, 12),
                    ),
                ).add_to(m2)
        st_folium(m2, use_container_width=True, height=400, returned_objects=[])

        with st.container(border=True):
            st.html('<div class="card-header"><span>Patrol Unit Dispatch Log</span>'
                    '<span class="badge badge-sage">All Active</span></div>')
            patrols = [
                ("Unit Echo-3 (Officer Suresh K.)",  "Route: Koramangala 80 Feet Road (Sector 4)", "14 Citations", "badge-sage"),
                ("Unit Delta-2 (Officer Priya R.)",  "Route: MG Road & Residency Road (Sector 1)", "9 Citations",  "badge-sage"),
                ("Unit Alpha-1 (Officer Anand G.)",  "Route: Indiranagar Double Road (Sector 2)",  "22 Citations", "badge-sage"),
                ("Unit Bravo-4 (Officer Amit S.)",   "Route: Outer Ring Road, Bellandur (Sector 8)","Responding to Truck Obstruction", "badge-amber"),
            ]
            list_html = '<ul class="panel-list">'
            for unit, route, status, badge in patrols:
                list_html += (
                    f'<li class="panel-list-item">'
                    f'<div><div class="panel-list-title">{unit}</div>'
                    f'<div class="panel-list-meta">{route}</div></div>'
                    f'<div style="text-align:right;">'
                    f'<span class="badge {badge}">{status}</span></div></li>'
                )
            list_html += "</ul>"
            st.html(list_html)
