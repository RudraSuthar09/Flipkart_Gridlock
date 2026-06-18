import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk

# Set page config
st.set_page_config(
    page_title="ParkIQ — Bengaluru",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
def inject_custom_css():
    st.html(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:ital,wght@0,100..900;1,100..900&display=swap');
        
        /* Apply font and background globally */
        html, body, [class*="css"], .stApp {
            font-family: 'Inter Tight', sans-serif !important;
            background-color: #F2F2F0 !important;
        }
        
        /* Main background override */
        .main {
            background-color: #F2F2F0 !important;
        }
        
        /* Hide default Streamlit headers and footers */
        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }
        [data-testid="stHeader"] {
            display: none !important;
        }
        .stAppHeader {
            display: none !important;
        }
        
        /* Sidebar container styling */
        [data-testid="stSidebar"] {
            background-color: #363236 !important;
            padding-top: 10px !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0px !important;
        }
        
        /* Custom Navbar */
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
            font-size: 24px;
            font-weight: 800;
            color: #363236;
            letter-spacing: -0.75px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .navbar-logo span {
            color: #F7B558; /* Amber */
        }
        .navbar-status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background-color: rgba(247, 181, 88, 0.12);
            color: #D97706; /* Darker amber */
            padding: 6px 16px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 700;
            border: 1px solid rgba(247, 181, 88, 0.25);
            letter-spacing: 0.25px;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background-color: #F7B558;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 0 0 rgba(247, 181, 88, 0.7);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(247, 181, 88, 0.7);
            }
            70% {
                transform: scale(1);
                box-shadow: 0 0 0 6px rgba(247, 181, 88, 0);
            }
            100% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(247, 181, 88, 0);
            }
        }
        
        /* Custom Sidebar Brand */
        .sidebar-brand {
            font-size: 26px;
            font-weight: 800;
            color: #FFFFFF;
            padding: 24px 20px 24px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 20px;
            letter-spacing: -0.75px;
        }
        .sidebar-brand span {
            color: #F7B558;
        }
        
        /* Custom Sidebar Links */
        .sidebar-nav {
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 0 10px;
        }
        .nav-link {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            color: rgba(255, 255, 255, 0.65) !important;
            text-decoration: none !important;
            font-size: 15px;
            font-weight: 500;
            border-left: 4px solid transparent;
            transition: all 0.2s ease;
            border-radius: 0 6px 6px 0;
        }
        .nav-link:hover {
            color: #FFFFFF !important;
            background-color: rgba(255, 255, 255, 0.04);
            border-left: 4px solid rgba(247, 181, 88, 0.4);
        }
        .nav-link.active {
            color: #FFFFFF !important;
            background-color: rgba(255, 255, 255, 0.08);
            border-left: 4px solid #F7B558 !important;
            font-weight: 600;
        }
        
        /* White Card Panel styling at the bottom */
        div[data-testid="stVerticalBlockBordered"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E2E0 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.01) !important;
            padding: 24px !important;
            margin-bottom: 20px !important;
        }
        
        /* Custom cards inside markdown */
        .card {
            background-color: #FFFFFF;
            border: 1px solid #E2E2E0;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.01);
            margin-bottom: 20px;
        }
        .card-header {
            font-size: 16px;
            font-weight: 700;
            color: #363236;
            margin-bottom: 12px;
            border-bottom: 1.5px solid #F2F2F0;
            padding-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        /* Metric Styles */
        [data-testid="stMetricValue"] {
            font-size: 28px !important;
            font-weight: 700 !important;
            color: #363236 !important;
            letter-spacing: -0.5px !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 12px !important;
            text-transform: uppercase !important;
            letter-spacing: 0.75px !important;
            color: #71717A !important;
            font-weight: 600 !important;
        }
        
        /* Pill badges */
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge-amber { background-color: rgba(247, 181, 88, 0.15) !important; color: #D97706 !important; }
        .badge-sage { background-color: rgba(165, 212, 140, 0.15) !important; color: #166534 !important; }
        .badge-danger { background-color: rgba(224, 82, 82, 0.15) !important; color: #991B1B !important; }
        .badge-charcoal { background-color: rgba(54, 50, 54, 0.1) !important; color: #363236 !important; }
        
        /* Table / List styles */
        .panel-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .panel-list-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #F2F2F0;
            font-size: 14px;
        }
        .panel-list-item:last-child {
            border-bottom: none;
        }
        .panel-list-title {
            font-weight: 600;
            color: #363236;
        }
        .panel-list-meta {
            font-size: 12px;
            color: #71717A;
        }
        
        /* Slider overrides */
        .stSlider {
            padding-bottom: 15px !important;
        }
        
        /* PyDeck map card container */
        .map-container {
            border: 1px solid #E2E2E0;
            border-radius: 12px;
            overflow: hidden;
            background-color: #FFFFFF;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03);
            margin-bottom: 24px;
        }
        
        /* Force headings and subtitle text colors globally to charcoal */
        h1, h2, h3, h4, h5, h6,
        h1 *, h2 *, h3 *, h4 *, h5 *, h6 *,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h1 *,
        [data-testid="stMarkdownContainer"] h2 *,
        [data-testid="stMarkdownContainer"] h3 * {
            color: #363236 !important;
        }
        
        .page-subtitle {
            font-size: 15px !important;
            color: #52525B !important;
            margin-top: -16px !important;
            margin-bottom: 24px !important;
        }
        
        /* Widget/Slider labels and default body texts in the main panel */
        div[data-testid="stWidgetLabel"] p, label, .stSlider p {
            color: #363236 !important;
        }
        
        /* Slider values and bubble labels */
        div[data-testid="stSlider"] span {
            color: #363236 !important;
        }
        
        </style>
        """,
    )

inject_custom_css()

# Navigation definition
PAGES = {
    "Operations Map": "Operations Map",
    "Enforcement Funnel": "Enforcement Funnel",
    "Dark Fleet": "Dark Fleet",
    "Junction Deep-Dive": "Junction Deep-Dive",
    "What-If Simulator": "What-If Simulator",
    "Patrol Planner": "Patrol Planner"
}

# Fetch query parameters
query_params = st.query_params
current_page = query_params.get("page", "Operations Map")

# Ensure valid page
if current_page not in PAGES:
    current_page = "Operations Map"

# ----------------- SIDEBAR -----------------
# Render Custom Sidebar Title
st.sidebar.html('<div class="sidebar-brand">ParkIQ<span>—BLR</span></div>')

# Render Sidebar Links
nav_html = '<div class="sidebar-nav">'
for page_title, page_id in PAGES.items():
    is_active = (current_page == page_id)
    active_class = "active" if is_active else ""
    query_url = f"?page={page_id.replace(' ', '+')}"
    nav_html += f'<a href="{query_url}" target="_self" class="nav-link {active_class}">{page_title}</a>'
nav_html += '</div>'
st.sidebar.html(nav_html)

# ----------------- TOP NAVBAR -----------------
# Render top navbar inside main area
navbar_html = """
<div class="navbar">
    <div class="navbar-logo">Park<span>IQ</span></div>
    <div class="navbar-status">
        <span class="status-dot"></span>
        Bengaluru &middot; Live
    </div>
</div>
"""
st.html(navbar_html)

# ----------------- HELPER FOR PYDECK MAPS -----------------
def render_bengaluru_map(points_type="default", size_val=30, opacity=200):
    # Center coordinates of Bengaluru
    blr_lat, blr_lon = 12.9716, 77.5946
    
    # Generate static-random coordinates for consistency across page refreshes
    np.random.seed(42)
    num_points = 60
    
    # Random offsets around Bengaluru center
    lats = blr_lat + np.random.uniform(-0.03, 0.03, num_points)
    lons = blr_lon + np.random.uniform(-0.03, 0.03, num_points)
    
    if points_type == "violations":
        # Focus on violations: amber (occupied), danger (violations)
        statuses = np.random.choice(["Occupied", "Violation"], size=num_points, p=[0.4, 0.6])
    elif points_type == "dark_fleet":
        # Dark Fleet violations cluster heavily around Outer Ring Road
        statuses = np.random.choice(["Unregistered Fleet", "Suspected Offender"], size=num_points, p=[0.7, 0.3])
    elif points_type == "patrol":
        # Patrol units: active patrols (sage) vs dispatch events (amber)
        statuses = np.random.choice(["Active Patrol", "Responding"], size=num_points, p=[0.8, 0.2])
    elif points_type == "junction":
        # Centered tightly around Richmond Circle
        lats = 12.9602 + np.random.uniform(-0.005, 0.005, num_points)
        lons = 77.5975 + np.random.uniform(-0.005, 0.005, num_points)
        statuses = np.random.choice(["Blocked lane", "Illegal parking", "Clear"], size=num_points, p=[0.4, 0.4, 0.2])
    else:
        # Default: full distribution of available, occupied, and violation
        statuses = np.random.choice(["Available", "Occupied", "Violation"], size=num_points, p=[0.5, 0.3, 0.2])

    color_map = {
        "Available": [165, 212, 140, opacity],          # Sage #A5D48C
        "Occupied": [247, 181, 88, opacity],            # Amber #F7B558
        "Violation": [224, 82, 82, opacity],            # Danger #E05252
        "Unregistered Fleet": [224, 82, 82, opacity],   # Danger
        "Suspected Offender": [247, 181, 88, opacity],  # Amber
        "Active Patrol": [165, 212, 140, opacity],      # Sage
        "Responding": [247, 181, 88, opacity],         # Amber
        "Blocked lane": [224, 82, 82, opacity],         # Danger
        "Illegal parking": [247, 181, 88, opacity],     # Amber
        "Clear": [165, 212, 140, opacity]               # Sage
    }
    
    colors = [color_map[s] for s in statuses]
    sizes = np.random.uniform(size_val * 0.7, size_val * 1.3, num_points)
    
    df = pd.DataFrame({
        "lat": lats,
        "lon": lons,
        "status": statuses,
        "color": colors,
        "size": sizes
    })
    
    # Layer definition
    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position="[lon, lat]",
        get_color="color",
        get_radius="size",
        radius_scale=8,
        pickable=True
    )
    
    # Zoom levels based on view type
    zoom_level = 15 if points_type == "junction" else 12.5
    map_center_lat = 12.9602 if points_type == "junction" else blr_lat
    map_center_lon = 77.5975 if points_type == "junction" else blr_lon
    
    view_state = pdk.ViewState(
        latitude=map_center_lat,
        longitude=map_center_lon,
        zoom=zoom_level,
        pitch=20
    )
    
    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v10",
        tooltip={"text": "Status: {status}"}
    )
    
    # Render map inside container
    st.html('<div class="map-container">')
    st.pydeck_chart(r, width="stretch")
    st.html('</div>')

# ----------------- PAGE ROUTING AND RENDERING -----------------

if current_page == "Operations Map":
    st.title("Operations Map")
    st.html('<div class="page-subtitle">Real-time parking grid activity, occupied metrics, and warning hotspots.</div>')
    
    # Map (Dominant Top)
    render_bengaluru_map("default", size_val=30)
    
    # White Card Panel (Bottom)
    st.subheader("Grid Overview")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(label="Active Violations", value="482", delta="+12% vs last hour", delta_color="inverse")
            st.html('<span class="badge badge-danger">High Intensity</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Avg Occupancy Rate", value="76.4%", delta="-2.1% vs yesterday")
            st.html('<span class="badge badge-amber">Stable</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Patrol Coverage", value="18/24 Units", delta="6 Active Routes")
            st.html('<span class="badge badge-sage">Optimal</span>')
            
    # List Panel
    with st.container(border=True):
        st.html('<div class="card-header"><span>Critical Incidents Log</span><span class="badge badge-charcoal">Real-Time</span></div>')
        
        incidents = [
            ("Commercial Truck Double Parked", "Outer Ring Road (near Bellandur)", "2 mins ago", "badge-danger"),
            ("No-Parking Zone Obstruction", "Indiranagar 100 Feet Rd", "5 mins ago", "badge-amber"),
            ("Hydrant Obstruction Detected", "Koramangala 5th Block", "8 mins ago", "badge-danger"),
            ("Loading Zone Timeout Overrun", "MG Road Metro Station", "14 mins ago", "badge-amber")
        ]
        
        list_html = '<ul class="panel-list">'
        for title, location, elapsed, badge_class in incidents:
            list_html += f"""<li class="panel-list-item">
<div>
<div class="panel-list-title">{title}</div>
<div class="panel-list-meta">{location}</div>
</div>
<div style="text-align: right;">
<div class="badge {badge_class}" style="margin-bottom: 4px;">Alert</div>
<div class="panel-list-meta">{elapsed}</div>
</div>
</li>"""
        list_html += '</ul>'
        st.html(list_html)

elif current_page == "Enforcement Funnel":
    st.title("Enforcement Funnel")
    st.html('<div class="page-subtitle">Visualizing conversion from detection algorithms to ticket citations and paid fines.</div>')
    
    # Map (Dominant Top) - Show violation densities
    render_bengaluru_map("violations", size_val=35)
    
    # White Card Panel (Bottom)
    st.subheader("Funnel Conversions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(label="Detections (AI)", value="2,481", delta="+18% vs weekly avg")
            st.html('<span class="badge badge-charcoal">Raw Input</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Citations Generated", value="1,894", delta="76.3% Conversion Rate")
            st.html('<span class="badge badge-amber">Reviewed</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Paid Citations", value="₹1.48M", delta="61.4% Fine Pay-Rate", delta_color="normal")
            st.html('<span class="badge badge-sage">Settled</span>')
            
    # Detailed Funnel Metrics Card
    with st.container(border=True):
        st.html('<div class="card-header"><span>Funnel Step Breakdown</span><span class="badge badge-sage">Efficiency: High</span></div>')
        
        steps = [
            ("1. Video AI Detection", "Camera network identified 2,481 raw curb violations", "100%", "badge-charcoal"),
            ("2. Human Officer Validation", "1,985 events successfully validated by operators", "80.0%", "badge-sage"),
            ("3. Digital Ticket Issued", "1,894 citations successfully pushed to SMS & Fastag accounts", "76.3%", "badge-sage"),
            ("4. Escalated warning", "710 cases required follow-up warnings", "28.6%", "badge-amber"),
            ("5. Collection & Settlement", "1,162 fines resolved within the standard 48hr window", "46.8%", "badge-amber")
        ]
        
        list_html = '<ul class="panel-list">'
        for step_name, desc, conversion, badge in steps:
            list_html += f"""<li class="panel-list-item">
<div>
<div class="panel-list-title">{step_name}</div>
<div class="panel-list-meta">{desc}</div>
</div>
<div style="text-align: right;">
<span class="badge {badge}">{conversion}</span>
</div>
</li>"""
        list_html += '</ul>'
        st.html(list_html)

elif current_page == "Dark Fleet":
    st.title("Dark Fleet")
    st.html('<div class="page-subtitle">Tracking unregistered commercial vehicles, night operators, and recurring offenders parked illegally.</div>')
    
    # Map (Dominant Top) - Focus on clusters of offender fleets
    render_bengaluru_map("dark_fleet", size_val=40, opacity=220)
    
    # White Card Panel (Bottom)
    st.subheader("Fleet Aggregators & Violations")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(label="Identified Dark Fleets", value="14 Sites", delta="+2 this week", delta_color="inverse")
            st.html('<span class="badge badge-danger">Critical Risk</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Aggregators Flagged", value="9 Vehicles Avg", delta="Continuous Overnight Parking")
            st.html('<span class="badge badge-amber">Warning</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Est. Curb Revenue Leak", value="₹482,000", delta="+14% Leakage Trend", delta_color="inverse")
            st.html('<span class="badge badge-danger">High Loss</span>')
            
    # Fleet Roster
    with st.container(border=True):
        st.html('<div class="card-header"><span>Top Offenders / Fleet Vehicles</span><span class="badge badge-charcoal">Updates Hourly</span></div>')
        
        fleets = [
            ("KA-03-HA-8821 (Logistics Co.)", "7 violations in Hebbal Ward", "Overnight dwell time: 8.2 hrs", "badge-danger"),
            ("KA-51-MD-4509 (Delivery Van)", "5 violations in Silk Board Junction", "Overnight dwell time: 6.8 hrs", "badge-danger"),
            ("KA-01-EE-3211 (Private Carrier)", "4 violations in Whitefield", "Overnight dwell time: 5.4 hrs", "badge-amber"),
            ("KA-04-MM-9801 (Construction Cargo)", "3 violations in Indiranagar", "Overnight dwell time: 7.1 hrs", "badge-amber")
        ]
        
        list_html = '<ul class="panel-list">'
        for reg, details, dwell, badge in fleets:
            list_html += f"""<li class="panel-list-item">
<div>
<div class="panel-list-title">{reg}</div>
<div class="panel-list-meta">{details}</div>
</div>
<div style="text-align: right;">
<div class="badge {badge}" style="margin-bottom: 4px;">{dwell}</div>
</div>
</li>"""
        list_html += '</ul>'
        st.html(list_html)

elif current_page == "Junction Deep-Dive":
    st.title("Junction Deep-Dive")
    st.html('<div class="page-subtitle">Detailed zoom-in on critical grid bottlenecks. Selected: Richmond Circle, Bengaluru.</div>')
    
    # Map (Dominant Top) - Richmond Circle tight zoom
    render_bengaluru_map("junction", size_val=12)
    
    # White Card Panel (Bottom)
    st.subheader("Curb Impedance Index")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(label="Average Transit Delay", value="14.2 min", delta="+3.2 min vs average", delta_color="inverse")
            st.html('<span class="badge badge-danger">Severe Congestion</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Curb Impedance Event Rate", value="84 / hr", delta="+12% blockages")
            st.html('<span class="badge badge-danger">Overloaded</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Target Flow Recovery", value="85%", delta="Sage flow threshold")
            st.html('<span class="badge badge-sage">Recovering</span>')
            
    # Junction details list
    with st.container(border=True):
        st.html('<div class="card-header"><span>Richmond Circle Access Points</span><span class="badge badge-amber">Under Review</span></div>')
        
        lanes = [
            ("Richmond Circle Flyover Entry", "High frequency of double-parked shuttle buses", "Blocked 14m/hr avg", "badge-danger"),
            ("Vittal Mallya Road Exit", "Delivery fleets blocking left turns consistently", "Blocked 22m/hr avg", "badge-danger"),
            ("RRMR Road Lane 1", "Taxi pickup dwell exceeds allowed 60s limit", "Minor obstruction", "badge-amber"),
            ("Museum Road Access Link", "Enforcement patrol cleared current blockers", "Clear & Free Flowing", "badge-sage")
        ]
        
        list_html = '<ul class="panel-list">'
        for entry, issues, status, badge in lanes:
            list_html += f"""<li class="panel-list-item">
<div>
<div class="panel-list-title">{entry}</div>
<div class="panel-list-meta">{issues}</div>
</div>
<div style="text-align: right;">
<div class="badge {badge}">{status}</div>
</div>
</li>"""
        list_html += '</ul>'
        st.html(list_html)

elif current_page == "What-If Simulator":
    st.title("What-If Simulator")
    st.html('<div class="page-subtitle">Model parking occupancy, enforcement presence, and rate alterations before live implementation.</div>')
    
    # Map (Dominant Top)
    render_bengaluru_map("default", size_val=25)
    
    # Simulator Controls (Inputs)
    with st.container(border=True):
        st.html('<div class="card-header"><span>Simulation Controls & Parameters</span><span class="badge badge-charcoal">Scenarios</span></div>')
        
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            hourly_rate = st.slider("Hourly Base Parking Rate (₹)", min_value=10, max_value=150, value=60, step=10)
            enforcement_agents = st.slider("Active Enforcement Patrol Units", min_value=5, max_value=50, value=20, step=5)
        with col_ctrl2:
            fine_amount = st.slider("Penalty Fine Amount for Violations (₹)", min_value=500, max_value=5000, value=1500, step=250)
            target_compliance = st.slider("Target Compliance Rate (%)", min_value=50, max_value=98, value=85, step=5)

    # Simulated Results (Bottom White Card Panel)
    st.subheader("Model Projections")
    col1, col2, col3 = st.columns(3)
    
    # Calculate simulated effects based on parameters
    sim_occupancy = max(20, min(95, 95 - (hourly_rate * 0.4)))
    sim_revenue = (hourly_rate * sim_occupancy * 12) + (enforcement_agents * (fine_amount * 0.25))
    sim_revenue_formatted = f"₹{sim_revenue:,.0f}"
    
    if enforcement_agents >= 30:
        sim_compliance_status = "Optimal"
        sim_badge_class = "badge-sage"
    elif enforcement_agents >= 15:
        sim_compliance_status = "Moderate"
        sim_badge_class = "badge-amber"
    else:
        sim_compliance_status = "Sub-optimal"
        sim_badge_class = "badge-danger"
        
    with col1:
        with st.container(border=True):
            st.metric(label="Predicted Average Occupancy", value=f"{sim_occupancy:.1f}%", delta=f"{- (hourly_rate * 0.1):.1f}% Price Elasticity")
            st.html('<span class="badge badge-amber">Calculated</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Estimated Daily Revenue (Curb)", value=sim_revenue_formatted, delta=f"+{(hourly_rate * 2):.0f}% vs base rate")
            st.html('<span class="badge badge-sage">Profitable</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Projected Compliance Level", value=f"{target_compliance}% (Desired)", delta=f"Status: {sim_compliance_status}")
            st.html(f'<span class="badge {sim_badge_class}">{sim_compliance_status}</span>')

elif current_page == "Patrol Planner":
    st.title("Patrol Planner")
    st.html('<div class="page-subtitle">AI-assisted dispatch routes and scheduling for ward officers based on historical blockages.</div>')
    
    # Map (Dominant Top) - Focus on patrol locations
    render_bengaluru_map("patrol", size_val=28)
    
    # White Card Panel (Bottom)
    st.subheader("Patrol Overview")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(label="Active Patrol Sectors", value="12 Sectors", delta="Full Coverage")
            st.html('<span class="badge badge-sage">Broad Reach</span>')
            
    with col2:
        with st.container(border=True):
            st.metric(label="Avg Dispatch Response Time", value="6.4 mins", delta="-1.2 mins vs peak avg")
            st.html('<span class="badge badge-sage">Fast Response</span>')
            
    with col3:
        with st.container(border=True):
            st.metric(label="Enforcement Coverage Efficiency", value="92.1%", delta="+3.4% this week")
            st.html('<span class="badge badge-sage">Highly Efficient</span>')
            
    # Patrol Assignments
    with st.container(border=True):
        st.html('<div class="card-header"><span>Patrol Unit Dispatch Log & Assignments</span><span class="badge badge-sage">All Active</span></div>')
        
        patrols = [
            ("Unit Echo-3 (Officer Suresh K.)", "Route: Koramangala 80 Feet Road (Sector 4)", "Assigned: 4h 12m ago · 14 Citations", "badge-sage"),
            ("Unit Delta-2 (Officer Priya R.)", "Route: MG Road & Residency Road (Sector 1)", "Assigned: 2h 30m ago · 9 Citations", "badge-sage"),
            ("Unit Alpha-1 (Officer Anand G.)", "Route: Indiranagar Double Road (Sector 2)", "Assigned: 5h 05m ago · 22 Citations", "badge-sage"),
            ("Unit Bravo-4 (Officer Amit S.)", "Route: Outer Ring Road, Bellandur (Sector 8)", "Responding to Truck Obstruction", "badge-amber")
        ]
        
        list_html = '<ul class="panel-list">'
        for unit, route, status, badge in patrols:
            list_html += f"""<li class="panel-list-item">
<div>
<div class="panel-list-title">{unit}</div>
<div class="panel-list-meta">{route}</div>
</div>
<div style="text-align: right;">
<span class="badge {badge}">{status}</span>
</div>
</li>"""
        list_html += '</ul>'
        st.html(list_html)
