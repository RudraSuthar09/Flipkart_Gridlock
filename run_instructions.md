# Running the Flipkart Gridlock Project (ParkIQ — BLR)

This guide provides step-by-step instructions on setting up and running the **ParkIQ Bengaluru** project. The project is a Streamlit-based intelligence dashboard for real-time parking violations, economic impact scoring, and dark fleet detection.

---

## 🛠️ Step 1: Install Dependencies

We have created a `requirements.txt` file in the project directory containing all the necessary libraries. 

Open your terminal (PowerShell, Command Prompt, or Git Bash) inside the project directory (`e:\Flipkart_Gridlock\Flipkart_Gridlock`) and run:

```powershell
pip install -r requirements.txt
```

This will install:
- **Web App**: `streamlit`, `streamlit-folium`, `folium` (for map rendering), `plotly` (for analytical plots).
- **Geospatial & Network Analysis**: `h3` (for geohashing), `osmnx` (for road network snapping), `pyproj`, `networkx`, `python-louvain` (for community detection).
- **Data & Progress Bar**: `pandas`, `numpy`, `scikit-learn`, `tqdm`.

---

## 🚀 Step 2: Run the Streamlit Application

Since the repository already contains all the precomputed datasets in the `data/` and `outputs/` directories, **you can launch the dashboard immediately** without running the preprocessing scripts.

Run the following command from the project root (`e:\Flipkart_Gridlock\Flipkart_Gridlock`):

```powershell
streamlit run app.py
```

Alternatively, you can run the helper script:
```powershell
python run_app.py
```

Once started, Streamlit will print the local URL to access the dashboard. Open it in your browser:
👉 **`http://localhost:8501`**

---

## 📊 Overview of the Data Pipelines

If you ever need to re-run the analysis pipelines from scratch or update the source data, you can run the python scripts in order:

> [!NOTE]
> Running the initial cleanup script `01_clean_and_resolve.py` requires the raw dataset file `dataset.csv` to be present in the root of the project directory.

### 1. Data Cleaning & Junction Snapping
```powershell
python 01_clean_and_resolve.py
```
- **What it does**: Parses dates, groups unresolved "No Junction" records using H3 geohashing, snaps centroids to the closest OpenStreetMap roads using `OSMnx`, and computes SCITA police station send rates.
- **Outputs generated**: `data/violations_clean.csv`, `data/device_audit.csv`, `data/station_funnel.csv`.

### 2. Computing the Parking Impact Score (PIS)
```powershell
python 02_analytics.py
```
- **What it does**: Maps vehicle size footprints (blockage severity), snaps junctions to OSMnx road networks to compute betweenness centrality, applies a weighted score (PIS), maps junctions to priority actions, and computes daily economic time & INR loss.
- **Outputs generated**: `outputs/pis_scores.csv`.

### 3. Louvain Cluster Community Detection
```powershell
python 03_dark_fleet.py
```
- **What it does**: Builds a bipartite vehicle-to-junction network graph, filters out persistent repeat offenders (3+ junctions and 10+ violations), projects onto a vehicle-only graph, and applies the Louvain community detection algorithm to locate organized fleet clusters.
- **Outputs generated**: `outputs/dark_fleet.csv`, `outputs/fleet_graph_edges.csv`.

---

## 🗺️ Project Navigation Pages

Once you open the Streamlit app at `http://localhost:8501`, you can navigate through:
- **Operations Map**: Folium interactive map showing critical hotspots (PIS >= 0.85 in red) and dark fleet nodes.
- **Enforcement Funnel**: Visual representation of the conversion drop-off from raw detection to actual penalty actions.
- **Dark Fleet**: Louvain community groups showing organized vehicle clusters and top offenders.
- **Junction Deep-Dive**: Hourly, vehicle type, and monthly trend breakdowns for any chosen junction in Bengaluru.
- **What-If Simulator**: Interactive sliders modeling economic time and INR savings depending on enforcement levels.
- **Patrol Planner**: Priority lists and map locations for manual officer patrol scheduling.
