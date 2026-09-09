"""
spray-drift-detector: Core Analytics Module
Author: Alejandro Alemán Virasoro
Description: Post-application quality assessment, uniformity audit,
             and drift detection (exoderiva / endoderiva) using Sentinel-2 and GEE.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import ee


def initialize_earth_engine(project_id: str = "eefcainterpolation") -> None:
    """Initialize Google Earth Engine session."""
    try:
        ee.Initialize(project=project_id)
    except Exception:
        ee.Initialize()


def mask_s2_sr_scl(image: ee.Image) -> ee.Image:
    """
    Mask clouds, cirrus, and cloud shadows using the Scene Classification Layer (SCL)
    from Sentinel-2 Level-2A (COPERNICUS/S2_SR_HARMONIZED).
    
    SCL Classes to keep (clear land/vegetation):
      4: Vegetation
      5: Bare soil
      6: Water
      7: Unclassified (low confidence)
    
    Classes filtered out:
      0: No data
      1: Saturated or defective
      2: Dark area pixels
      3: Cloud shadows
      8: Cloud medium probability
      9: Cloud high probability
      10: Thin cirrus
      11: Snow / Ice
    """
    scl = image.select('SCL')
    valid_mask = (
        scl.eq(4)
        .Or(scl.eq(5))
        .Or(scl.eq(6))
        .Or(scl.eq(7))
    )
    return image.updateMask(valid_mask).divide(10000)


def calculate_ndvi(image: ee.Image) -> ee.Image:
    """Calculate Normalized Difference Vegetation Index (NDVI) from B8 (NIR) and B4 (Red)."""
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')


def get_temporal_composite(
    roi: ee.Geometry,
    start_date: str,
    end_date: str,
    max_cloud_percentage: float = 30.0
) -> ee.Image:
    """
    Generate cloud/shadow-free median composite for a specified temporal window.
    Using median() minimizes residual cloud/shadow artifacts.
    """
    collection = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_percentage))
        .map(mask_s2_sr_scl)
        .map(lambda img: img.addBands(calculate_ndvi(img)))
    )
    
    return collection.median().clip(roi)


def build_spray_audit_raster(
    aoi_geometry: ee.Geometry,
    application_date: str,
    pre_window_days: int = 15,
    lag_days: int = 10,
    post_window_days: int = 15,
    buffer_meters: float = 120.0
) -> Dict[str, Any]:
    """
    Builds the pre-spray, post-spray, and Delta-NDVI rasters considering product mode of action lag.
    
    Args:
        aoi_geometry: Target field polygon (ee.Geometry).
        application_date: Date of chemical spray (YYYY-MM-DD).
        pre_window_days: Days before application to build pre-spray baseline (default: 15).
        lag_days: Days required for herbicide/chemical mode of action to take full effect (default: 10).
        post_window_days: Length of post-application observation window after lag (default: 15).
        buffer_meters: Outward buffer around field boundary to detect exoderiva (spray drift) (default: 120m).
    
    Timeline:
        [pre_start -------- pre_end (app_date)] === SPRAY === [lag_days] === [post_start -------- post_end]
    """
    app_dt = datetime.strptime(application_date, "%Y-%m-%d")
    
    pre_end_dt = app_dt
    pre_start_dt = app_dt - timedelta(days=pre_window_days)
    
    post_start_dt = app_dt + timedelta(days=lag_days)
    post_end_dt = post_start_dt + timedelta(days=post_window_days)
    
    pre_start = pre_start_dt.strftime("%Y-%m-%d")
    pre_end = pre_end_dt.strftime("%Y-%m-%d")
    post_start = post_start_dt.strftime("%Y-%m-%d")
    post_end = post_end_dt.strftime("%Y-%m-%d")
    
    # Extended region of interest (Field + Drift Buffer)
    roi_extended = aoi_geometry.buffer(buffer_meters)
    
    # Generate composites
    pre_composite = get_temporal_composite(roi_extended, pre_start, pre_end)
    post_composite = get_temporal_composite(roi_extended, post_start, post_end)
    
    pre_ndvi = pre_composite.select('NDVI').rename('NDVI_pre')
    post_ndvi = post_composite.select('NDVI').rename('NDVI_post')
    
    # Delta NDVI: Post - Pre
    delta_ndvi = post_ndvi.subtract(pre_ndvi).rename('Delta_NDVI')
    
    # Combine multi-band audit image for QGIS analysis
    # Bands: [Delta_NDVI, NDVI_pre, NDVI_post, B4_post, B3_post, B2_post, B8_post]
    audit_multiband = (
        delta_ndvi
        .addBands(pre_ndvi)
        .addBands(post_ndvi)
        .addBands(post_composite.select(['B4', 'B3', 'B2', 'B8']))
    )
    
    return {
        "audit_raster": audit_multiband,
        "delta_ndvi": delta_ndvi,
        "pre_ndvi": pre_ndvi,
        "post_ndvi": post_ndvi,
        "roi_extended": roi_extended,
        "windows": {
            "application_date": application_date,
            "pre": (pre_start, pre_end),
            "lag_days": lag_days,
            "post": (post_start, post_end),
            "buffer_meters": buffer_meters
        }
    }


def export_audit_to_drive(
    image: ee.Image,
    description: str,
    folder: str,
    file_name: str,
    region: ee.Geometry,
    scale: int = 10,
    crs: str = 'EPSG:4326'
) -> ee.batch.Task:
    """
    Submits a batch export task to Google Drive to download GeoTIFF.
    """
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder=folder,
        fileNamePrefix=file_name,
        region=region,
        scale=scale,
        crs=crs,
        maxPixels=1e9
    )
    task.start()
    return task


def download_audit_geotiff(
    image: ee.Image,
    region: ee.Geometry,
    output_filepath: str,
    scale: int = 10,
    crs: str = 'EPSG:4326'
) -> str:
    """
    Directly downloads GeoTIFF using ee.data.getDownloadURL (ideal for field-scale rasters).
    Bypasses Google Drive batch waiting time for interactive local workflows.
    """
    import urllib.request
    
    url = image.getDownloadURL({
        'scale': scale,
        'crs': crs,
        'region': region,
        'format': 'GEO_TIFF'
    })
    
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    urllib.request.urlretrieve(url, output_filepath)
    return output_filepath
