"""
spray-drift-detector: Core Analytics Module
Author: Alejandro Alemán Virasoro
Description: Post-application quality assessment, uniformity audit,
             and drift detection using Sentinel-2 and Google Earth Engine (GEE).
"""

import json
import os
from typing import Dict, Any, Tuple
import ee


def initialize_earth_engine(project_id: str = "eefcainterpolation") -> None:
    """Initialize Google Earth Engine session."""
    try:
        ee.Initialize(project=project_id)
    except Exception:
        # Fallback to default init if already authenticated
        ee.Initialize()


def mask_s2_clouds(image: ee.Image) -> ee.Image:
    """
    Mask clouds in Sentinel-2 Surface Reflectance imagery using the QA60 band.
    
    Bits 10 and 11 represent clouds and cirrus, respectively.
    """
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    
    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
        qa.bitwiseAnd(cirrus_bit_mask).eq(0)
    )
    
    return image.updateMask(mask).divide(10000)


def calculate_ndvi(image: ee.Image) -> ee.Image:
    """Calculate Normalized Difference Vegetation Index (NDVI) from B8 (NIR) and B4 (Red)."""
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')


def get_temporal_composite(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    max_cloud_percentage: float = 25.0
) -> ee.Image:
    """
    Query and generate cloud-free median composite for a specified time window.
    
    Returns:
        ee.Image with bands and calculated NDVI.
    """
    collection = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_percentage))
        .map(mask_s2_clouds)
        .map(lambda img: img.addBands(calculate_ndvi(img)))
    )
    
    composite = collection.median().clip(aoi)
    return composite


def compute_spray_impact(
    aoi_geometry: ee.Geometry,
    pre_dates: Tuple[str, str],
    post_dates: Tuple[str, str],
    buffer_distance_meters: float = 60.0
) -> Dict[str, Any]:
    """
    Computes pre vs post application metrics, NDVI differences,
    and analyzes surrounding buffer zones for spray drift detection.
    """
    pre_composite = get_temporal_composite(aoi_geometry, pre_dates[0], pre_dates[1])
    post_composite = get_temporal_composite(aoi_geometry, post_dates[0], post_dates[1])
    
    pre_ndvi = pre_composite.select('NDVI').rename('NDVI_pre')
    post_ndvi = post_composite.select('NDVI').rename('NDVI_post')
    
    # Delta NDVI: Post - Pre
    # For herbicide fallow: significant negative delta indicates successful burndown/kill
    # For fungicide/fertilizer: positive or sustained delta indicates response
    delta_ndvi = post_ndvi.subtract(pre_ndvi).rename('Delta_NDVI')
    
    # Buffer analysis for Drift detection (Off-target impact)
    external_buffer = aoi_geometry.buffer(buffer_distance_meters).difference(aoi_geometry)
    
    # In-field statistics
    infield_stats = delta_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            reducer2=ee.Reducer.minMax(), sharedInputs=True
        ),
        geometry=aoi_geometry,
        scale=10,
        maxPixels=1e8
    )
    
    # Buffer (Drift zone) statistics
    drift_zone_stats = delta_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.stdDev(), sharedInputs=True
        ),
        geometry=external_buffer,
        scale=10,
        maxPixels=1e8
    )
    
    return {
        "pre_image": pre_composite,
        "post_image": post_composite,
        "delta_ndvi": delta_ndvi,
        "external_buffer_geometry": external_buffer,
        "infield_stats": infield_stats,
        "drift_zone_stats": drift_zone_stats,
    }
