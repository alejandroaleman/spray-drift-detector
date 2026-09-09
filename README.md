# 🛰️ spray-drift-detector: Post-Application Quality & Drift Audit Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Google Earth Engine](https://img.shields.io/badge/Google%20Earth%20Engine-API-brightgreen?logo=google)](https://earthengine.google.com)
[![Copernicus Sentinel-2](https://img.shields.io/badge/Sentinel--2-MSI%2010m-orange)](https://sentinels.copernicus.eu/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An Earth Observation analytics tool using **Sentinel-2 multispectral imagery** and **Google Earth Engine (GEE)** to audit agricultural chemical applications (herbicides, defoliants, fungicides) ex-post.

It automatically evaluates:
1. **Application Uniformity & Efficacy:** Evaluates in-field canopy impact via $\Delta\text{NDVI}$ (pre- vs post-application) and calculates spatial coefficient of variation.
2. **Missed Passes / Strips:** Identifies untreated rows or nozzle blockage zones.
3. **Off-Target Spray Drift:** Dynamically generates outer boundary buffer zones to detect unintended chemical drift onto neighboring plots or natural reserves.

---

## 🎯 Agronomic Context & Motivation
Agricultural spraying is vulnerable to weather variables (wind speed, thermal inversions) and operational errors (improper boom height, nozzle clogs). Traditional field scouting only samples tiny fractions of a field.

By leveraging **Sentinel-2 MSI Surface Reflectance (10 m/pixel)** combined with **QA60 cloud/cirrus masking**, this pipeline quantifies real vegetation response across entire agricultural plots.

```
       Field Boundary (AOI)
     ┌────────────────────────┐
     │   Target Area          │   ===> Pre-spray NDVI Composite
     │   (Field Polygon)      │   ===> Post-spray NDVI Composite
     └────────────────────────┘   ===> Delta NDVI ($\Delta\text{NDVI}$)
               │
    [Outer Buffer Ring: 60m] ===> Drift / Off-Target Impact Detection
```

---

## 🔬 Methodology

1. **Cloud & Shadow Filtering:** Uses Sentinel-2 QA60 bitmasking (Bits 10 & 11) to eliminate cloud contamination.
2. **Temporal Window Compositing:** Computes median reflectance across targeted acquisition windows prior to and following the spraying event date.
3. **Spectral Indices:**
   $$\text{NDVI} = \frac{\text{B8 (NIR)} - \text{B4 (Red)}}{\text{B8 (NIR)} + \text{B4 (Red)}}$$
   $$\Delta\text{NDVI} = \text{NDVI}_{\text{post}} - \text{NDVI}_{\text{pre}}$$
   - **Herbicide / Chemical Fallow:** Sharp negative delta ($\Delta\text{NDVI} < -0.15$) validates successful burndown.
   - **Unintended Drift:** Negative delta detected within the surrounding buffer zone flags potential drift claims.
4. **Zonal Statistics:** Computes mean response, standard deviation, and identifies spatial outliers.

---

## 📁 Repository Structure

```text
spray-drift-detector/
├── data/
│   ├── input/               # Boundary GeoJSON/Shapefile files
│   └── output/              # Exported GeoTIFFs and analytical reports
├── notebooks/
│   └── 01_drift_audit_workflow.ipynb  # Interactive walkthrough with geemap
├── src/
│   ├── __init__.py
│   └── audit_engine.py      # Core Earth Engine processing pipeline
├── requirements.txt         # Dependencies
└── README.md                # Project documentation
```

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/alejandroaleman/spray-drift-detector.git
cd spray-drift-detector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Earth Engine Authentication
```bash
earthengine authenticate
```

### 3. Usage Example
```python
import ee
from src.audit_engine import initialize_earth_engine, compute_spray_impact

initialize_earth_engine(project_id="your-gee-project-id")

# Define target plot
aoi = ee.Geometry.Polygon([[[...]]])

# Run audit: Pre vs Post spray windows
results = compute_spray_impact(
    aoi_geometry=aoi,
    pre_dates=("2024-11-20", "2024-12-04"),
    post_dates=("2024-12-18", "2025-01-05"),
    buffer_distance_meters=60.0
)

print("In-field Statistics:", results["infield_stats"].getInfo())
print("Buffer Drift Statistics:", results["drift_zone_stats"].getInfo())
```

---

## 👨‍💻 Author
**Alejandro Alemán Virasoro**  
*Agricultural Engineer | Geospatial Data Scientist & Remote Sensing Specialist*  
- LinkedIn: [ing-alejandro-aleman](https://www.linkedin.com/in/ing-alejandro-aleman/)  
- GitHub: [@alejandroaleman](https://github.com/alejandroaleman)  
- Email: aaleman@fca.unl.edu.ar / janoaleman@gmail.com
