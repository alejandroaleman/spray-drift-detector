#!/usr/bin/env python3
"""
CLI Runner for Spray Drift & Uniformity Audit
Usage example:
    python run_audit.py --aoi data/input/santa_ana_18.geojson --date 2024-12-05 --lag 12 --buffer 120
"""

import os
import sys
import json
import argparse
import ee

from src.audit_engine import (
    initialize_earth_engine,
    build_spray_audit_raster,
    download_audit_geotiff,
    export_audit_to_drive
)


def parse_args():
    parser = argparse.ArgumentParser(description="Sentinel-2 Spray Drift & Uniformity Audit Engine")
    parser.add_argument("--aoi", required=True, help="Path to AOI GeoJSON or Shapefile")
    parser.add_argument("--date", required=True, help="Application Date (YYYY-MM-DD)")
    parser.add_argument("--pre-days", type=int, default=15, help="Days before spray for pre-baseline (default: 15)")
    parser.add_argument("--lag", type=int, default=10, help="Mode of action latency days (default: 10)")
    parser.add_argument("--post-days", type=int, default=15, help="Observation window days after lag (default: 15)")
    parser.add_argument("--buffer", type=float, default=120.0, help="Exoderiva outer buffer distance in meters (default: 120.0)")
    parser.add_argument("--export-drive", action="store_true", help="Export to Google Drive instead of direct download")
    parser.add_argument("--drive-folder", default="GIS_Export", help="Google Drive folder for export")
    parser.add_argument("--project", default="eefcainterpolation", help="Google Cloud project for Earth Engine")
    return parser.parse_args()


def main():
    args = parse_args()
    
    print(f"[*] Initializing Earth Engine (project: {args.project})...")
    initialize_earth_engine(project_id=args.project)
    
    if not os.path.exists(args.aoi):
        print(f"[!] Error: AOI file not found at '{args.aoi}'")
        sys.exit(1)
        
    with open(args.aoi, 'r') as f:
        geojson_data = json.load(f)
    
    aoi_geom = ee.Geometry(geojson_data['features'][0]['geometry'])
    base_name = os.path.splitext(os.path.basename(args.aoi))[0]
    
    print(f"[*] Building audit raster for AOI: {base_name}")
    print(f"    - Application date: {args.date}")
    print(f"    - Pre-spray window: {args.pre_days} days")
    print(f"    - Product lag period: {args.lag} days")
    print(f"    - Post-spray window: {args.post_days} days")
    print(f"    - Exoderiva buffer: {args.buffer} meters")
    
    audit_data = build_spray_audit_raster(
        aoi_geometry=aoi_geom,
        application_date=args.date,
        pre_window_days=args.pre_days,
        lag_days=args.lag,
        post_window_days=args.post_days,
        buffer_meters=args.buffer
    )
    
    file_tag = f"{base_name}_spray_audit_{args.date}_lag{args.lag}d_buf{int(args.buffer)}m"
    
    if args.export_drive:
        print(f"[*] Submitting export task to Google Drive folder: '{args.drive_folder}'...")
        task = export_audit_to_drive(
            image=audit_data["audit_raster"],
            description=f"Export_{file_tag}",
            folder=args.drive_folder,
            file_name=file_tag,
            region=audit_data["roi_extended"],
            scale=10
        )
        print(f"[+] Task submitted successfully (Task ID: {task.id}). Check Google Drive.")
    else:
        out_path = os.path.join("data", "output", f"{file_tag}.tif")
        print(f"[*] Directly downloading GeoTIFF for QGIS to: {out_path}...")
        try:
            download_audit_geotiff(
                image=audit_data["audit_raster"],
                region=audit_data["roi_extended"],
                output_filepath=out_path,
                scale=10
            )
            print(f"[✓] GeoTIFF successfully generated at '{out_path}'!")
            print("    -> Band 1: Delta_NDVI (Post - Pre)")
            print("    -> Band 2: NDVI_pre")
            print("    -> Band 3: NDVI_post")
            print("    -> Bands 4-7: B4 (Red), B3 (Green), B2 (Blue), B8 (NIR)")
            print("    -> Ready to drag & drop into QGIS!")
        except Exception as e:
            print(f"[!] Direct download failed ({e}), falling back to Google Drive export...")
            export_audit_to_drive(
                image=audit_data["audit_raster"],
                description=f"Export_{file_tag}",
                folder=args.drive_folder,
                file_name=file_tag,
                region=audit_data["roi_extended"],
                scale=10
            )
            print("[+] Export task submitted to Google Drive.")


if __name__ == "__main__":
    main()
