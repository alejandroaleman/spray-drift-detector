# 🛰️ spray-drift-detector: Post-Application Quality & Drift Audit Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Google Earth Engine](https://img.shields.io/badge/Google%20Earth%20Engine-API-brightgreen?logo=google)](https://earthengine.google.com)
[![Copernicus Sentinel-2](https://img.shields.io/badge/Sentinel--2-MSI%2010m-orange)](https://sentinels.copernicus.eu/)
[![QGIS Ready](https://img.shields.io/badge/QGIS-MultiBand%20GeoTIFF-589632?logo=qgis&logoColor=white)](https://qgis.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A remote sensing analytics pipeline utilizing **Copernicus Sentinel-2 Surface Reflectance** and **Google Earth Engine (GEE)** to conduct ex-post audits on agricultural spraying operations (chemical fallow, herbicides, desiccants, fungicides).

Designed to identify and diagnose both:
- **Exo-drift (Off-Target Drift):** Chemical escape impacting neighboring crops, tree lines, or natural reserves outside the field perimeter.
- **Endo-drift & Application Uniformity:** Untreated strips, nozzle clogging, or phytotoxicity within the target plot.

---

## 🔬 Core Methodology & Agronomic Logic

### 1. Herbicide Mode of Action (MoA) Latency (`lag_days`)
Herbicides do not cause immediate spectral changes:
- **Contact desiccants:** 48–72 hours.
- **Systemic herbicides (Glyphosate, Hormonals, ALS/ACCase inhibitors):** require **7 to 15+ days** to induce full cellular chlorosis and drop reflectance in the NIR band (B8).
The engine introduces a customizable `lag_days` parameter between the application date and the post-spray observation window.

```
Timeline:
[pre_start -------- pre_end (Spray Date)] === SPRAY === [lag_days] === [post_start -------- post_end]
      Pre-spray Baseline Window                                         Post-spray Response Window
```

### 2. Multi-temporal Cloud/Shadow Masking via SCL
To prevent false-positive drops in vegetation indices caused by cloud shadows or thin cirrus, the engine filters scenes using the **Scene Classification Layer (SCL)** from Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`), discarding cloud shadows, cirrus, and high/medium cloud probabilities. Composites are then aggregated using the **temporal median**, ensuring robust cloud-free mosaics.

### 3. Extended Exo-drift Buffer
Rather than clipping strictly to the field boundary, the raster is exported with a surrounding outward buffer (default: **120 meters**). When visualized in QGIS, any chemical drift following the prevailing wind direction is immediately detectable beyond the boundary fence.

$$\Delta\text{NDVI} = \text{NDVI}_{\text{post}} - \text{NDVI}_{\text{pre}}$$

---

## 📁 Multi-band GeoTIFF Output (QGIS Ready)

The engine generates a 7-band GeoTIFF ready for GIS analysis:
- **Band 1 (`Delta_NDVI`):** Post - Pre NDVI difference. Values $<-0.20$ indicate strong burndown / drift impact.
- **Band 2 (`NDVI_pre`):** Pre-spray baseline vigor.
- **Band 3 (`NDVI_post`):** Post-spray canopy vigor.
- **Bands 4–7 (`B4, B3, B2, B8`):** True-color and NIR bands for contextual high-resolution background inspection.

---

## 🚀 Usage

### 1. Requirements & Setup
```bash
git clone https://github.com/alejandroaleman/spray-drift-detector.git
cd spray-drift-detector
pip install -r requirements.txt
earthengine authenticate
```

### 2. Run Audit via CLI
Directly download the GeoTIFF for QGIS:
```bash
python run_audit.py \
    --aoi data/input/santa_ana_18.geojson \
    --date 2024-12-05 \
    --lag 12 \
    --buffer 120
```

Export large areas to Google Drive:
```bash
python run_audit.py \
    --aoi data/input/santa_ana_18.geojson \
    --date 2024-12-05 \
    --lag 12 \
    --buffer 150 \
    --export-drive \
    --drive-folder GIS_Export
```

---

## 👨‍💻 Author
**Alejandro Alemán Virasoro**  
*Agricultural Engineer | Geospatial Data Scientist & Remote Sensing Specialist*  
- LinkedIn: [ing-alejandro-aleman](https://www.linkedin.com/in/ing-alejandro-aleman/)  
- GitHub: [@alejandroaleman](https://github.com/alejandroaleman)  
- Email: aaleman@fca.unl.edu.ar / janoaleman@gmail.com
