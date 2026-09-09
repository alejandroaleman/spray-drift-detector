# Architecture & Data Flow Pipeline

This document details the software architecture, data lifecycle, function specifications, and execution flow of the **`spray-drift-detector`** engine.

---

## 1. System Pipeline Flow

The execution workflow is designed to ingest target agricultural parcels, dynamically define temporal baselines based on chemical mode of action (MoA), filter atmospheric contamination via Sentinel-2 Scene Classification Layer (SCL), and export multi-band spatial rasters ready for GIS inspection.

```mermaid
flowchart TD
    classDef inputStyle fill:#e1f5fe,stroke:#0288d1,stroke-width:1.5px,color:#01579b;
    classDef funcStyle fill:#e8f5e9,stroke:#388e3c,stroke-width:1.5px,color:#1b5e20;
    classDef objStyle fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px,color:#e65100;
    classDef outputStyle fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1.5px,color:#4a148c;

    subgraph UserInputs ["1. User & Operational Arguments (CLI / run_audit.py)"]
        AOI["--aoi: Path to GeoJSON / Shapefile"]:::inputStyle
        DATE["--date: Spray Event Date (YYYY-MM-DD)"]:::inputStyle
        CONFIG["--lag (10d), --pre-days (15d), --post-days (15d), --buffer (120m)"]:::inputStyle
    end

    subgraph Initialization ["2. GEE Session Setup"]
        F_INIT["initialize_earth_engine(project_id)"]:::funcStyle
        F_INIT -->|"Resolves project from arg, env EE_PROJECT_ID, or local credentials"| GEE_SESSION[Active GEE Session]:::objStyle
    end

    subgraph CoreOrchestrator ["3. Core Pipeline (audit_engine.py)"]
        AOI & DATE & CONFIG --> F_BUILD["build_spray_audit_raster(...)"]:::funcStyle
        
        F_BUILD -->|"aoi.buffer(buffer_meters)"| ROI_EXT["roi_extended (ee.Geometry)"]:::objStyle
        F_BUILD -->|"Compute Pre, Latency Lag, and Post Windows"| WINDOWS["Temporal Windows (Dates)"]:::objStyle

        subgraph CompositePipeline ["Temporal Composite Sub-pipeline"]
            WINDOWS & ROI_EXT --> F_COMP["get_temporal_composite(roi, start, end)"]:::funcStyle
            
            F_COMP -->|"Query S2_SR_HARMONIZED by bounds and dates"| COLL_RAW["Raw ImageCollection"]:::objStyle
            COLL_RAW --> F_SCL["mask_s2_sr_scl(image)"]:::funcStyle
            F_SCL -->|"SCL mask: Discard clouds, cirrus, cloud shadows"| COLL_MASKED[Masked Surface Reflectance Collection]:::objStyle
            
            COLL_MASKED --> F_NDVI["calculate_ndvi(image)"]:::funcStyle
            F_NDVI -->|"Attach (B8 - B4) / (B8 + B4)"| COLL_NDVI[Collection with NDVI Band]:::objStyle
            
            COLL_NDVI -->|"collection.median().clip(roi)"| COMPOSITE["ee.Image (Cloud-free Composite)"]:::objStyle
        end

        COMPOSITE -->|"Generate Pre Baseline"| PRE_IMG["pre_ndvi (ee.Image)"]:::objStyle
        COMPOSITE -->|"Generate Post Response"| POST_IMG["post_ndvi (ee.Image)"]:::objStyle

        PRE_IMG & POST_IMG -->|"post_ndvi.subtract(pre_ndvi)"| DELTA["delta_ndvi (ee.Image)"]:::objStyle
        DELTA & PRE_IMG & POST_IMG --> MULTIBAND["audit_multiband (7-Band ee.Image)"]:::objStyle
    end

    subgraph ExportSection ["4. Delivery Strategy"]
        MULTIBAND --> COND{--export-drive enabled?}
        
        COND -->|No: Local Direct Download| F_DOWN["download_audit_geotiff(image, region, ...)"]:::funcStyle
        F_DOWN -->|"getDownloadURL() stream"| TIF_LOCAL["data/output/*.tif (Local Multi-band GeoTIFF)"]:::outputStyle
        
        COND -->|Yes: Batch Cloud Task| F_DRIVE["export_audit_to_drive(image, description, ...)"]:::funcStyle
        F_DRIVE -->|"Export.image.toDrive()"| DRIVE_TASK["Google Drive / GIS_Export"]:::outputStyle
    end

    TIF_LOCAL --> QGIS["GIS Inspection: Endo-drift vs Exo-drift"]:::outputStyle
```

---

## 2. Technical Function Reference

### Module: `src/audit_engine.py`

#### `initialize_earth_engine(project_id: str | None = None) -> None`
- **Description:** Authenticates and starts an Earth Engine session dynamically.
- **Parameters:**
  - `project_id` (*str | None*): Target Google Cloud project. If not supplied, falls back to `EE_PROJECT_ID` environment variable or active local CLI credentials.

---

#### `mask_s2_sr_scl(image: ee.Image) -> ee.Image`
- **Description:** Performs pixel-level cloud, shadow, and cirrus masking using Sentinel-2 L2A Scene Classification Layer (SCL).
- **Parameters:**
  - `image` (*ee.Image*): Single Sentinel-2 Level-2A scene (`COPERNICUS/S2_SR_HARMONIZED`).
- **Internal Mechanism:**
  - Preserves valid land cover classes: `4` (Vegetation), `5` (Bare Soil), `6` (Water), `7` (Unclassified).
  - Eliminates invalid classes: `3` (Cloud Shadows), `8` (Medium Cloud Prob), `9` (High Cloud Prob), `10` (Cirrus).
  - Normalizes surface reflectance to $[0, 1]$ by scaling by $10000$.
- **Returns:** Scaled and masked `ee.Image`.

---

#### `calculate_ndvi(image: ee.Image) -> ee.Image`
- **Description:** Computes the Normalized Difference Vegetation Index.
- **Parameters:**
  - `image` (*ee.Image*): Multiband scene containing Band 8 (NIR) and Band 4 (Red).
- **Formula:** $\text{NDVI} = \frac{\text{B8} - \text{B4}}{\text{B8} + \text{B4}}$
- **Returns:** Single-band `ee.Image` named `'NDVI'`.

---

#### `get_temporal_composite(roi: ee.Geometry, start_date: str, end_date: str, max_cloud_percentage: float = 30.0) -> ee.Image`
- **Description:** Builds a cloud-free median mosaic over the extended parcel buffer across a given temporal window.
- **Parameters:**
  - `roi` (*ee.Geometry*): Extended parcel geometry (AOI + outer buffer).
  - `start_date` (*str*): Start of temporal window (`"YYYY-MM-DD"`).
  - `end_date` (*str*): End of temporal window (`"YYYY-MM-DD"`).
  - `max_cloud_percentage` (*float*): Cloud scene metadata threshold (default: `30.0`).
- **Mechanism:** Queries the collection, applies SCL masking, calculates NDVI, takes the pixel-wise **temporal median** (`.median()`), and clips to `roi`.
- **Returns:** Cloud-free `ee.Image`.

---

#### `build_spray_audit_raster(...) -> dict[str, Any]`
- **Description:** Main pipeline orchestrator that computes pre/post windows, evaluates vegetation response, and builds the multi-band audit raster.
- **Parameters:**
  - `aoi_geometry` (*ee.Geometry*): Field boundary polygon.
  - `application_date` (*str*): Spraying operation date (`"YYYY-MM-DD"`).
  - `pre_window_days` (*int*): Days prior to spray date to establish vigor baseline (default: `15`).
  - `lag_days` (*int*): Product latency / mode of action delay before post window opens (default: `10`).
  - `post_window_days` (*int*): Post-spray evaluation window duration (default: `15`).
  - `buffer_meters` (*float*): Distance in meters for the outward exo-drift buffer (default: `120.0`).
- **Returns:** `dict` containing:
  - `"audit_raster"`: 7-band `ee.Image` for export (`Delta_NDVI`, `NDVI_pre`, `NDVI_post`, `B4`, `B3`, `B2`, `B8`).
  - `"delta_ndvi"`: Single-band `ee.Image` ($\Delta\text{NDVI} = \text{NDVI}_{\text{post}} - \text{NDVI}_{\text{pre}}$).
  - `"roi_extended"`: `ee.Geometry` including the outward buffer.
  - `"windows"`: Computed dates dictionary.

---

#### `download_audit_geotiff(image: ee.Image, region: ee.Geometry, output_filepath: str, scale: int = 10, crs: str = 'EPSG:4326') -> str`
- **Description:** Direct stream download of field-scale GeoTIFFs using `ee.data.getDownloadURL` into the local file system.

---

#### `export_audit_to_drive(...) -> ee.batch.Task`
- **Description:** Submits an asynchronous batch export task to Google Drive for large regional footprints.

---

### Module: `run_audit.py` (CLI Interface)
- CLI entrypoint built with `argparse`.
- Parses `--aoi`, `--date`, `--lag`, `--buffer`, `--pre-days`, `--post-days`, and `--export-drive`.
- Automatically checks local AOI geometry, invokes `build_spray_audit_raster()`, and manages local GeoTIFF streaming or Google Drive task dispatch.
