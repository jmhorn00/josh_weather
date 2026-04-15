"""
S3 service for accessing NOAA public buckets (no credentials required).
All buckets use unsigned (anonymous) access via botocore UNSIGNED config.
"""
import logging
import os
from datetime import datetime, timezone as dt_tz

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from django.conf import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    return boto3.client(
        's3',
        region_name=settings.AWS_REGION,
        config=Config(signature_version=UNSIGNED),
    )


# ── NEXRAD Level 2 ────────────────────────────────────────────────────────────

def list_nexrad_scans(station_code, date):
    """
    List all S3 keys for a given station and date.
    S3 path: noaa-nexrad-level2/YYYY/MM/DD/KXXX/
    Returns list of S3 keys (strings).
    """
    client = get_s3_client()
    prefix = (
        f"{date.strftime('%Y/%m/%d')}/{station_code.upper()}/"
    )
    keys = []
    paginator = client.get_paginator('list_objects_v2')
    try:
        for page in paginator.paginate(Bucket=settings.AWS_NEXRAD_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Filter to Level 2 archive files (not NWS metadata)
                if '_V06' in key or '_V08' in key:
                    keys.append(key)
    except Exception as exc:
        logger.error('list_nexrad_scans(%s, %s): %s', station_code, date, exc)
    return sorted(keys)


def get_latest_nexrad_key(station_code):
    """Return the most recent NEXRAD S3 key for today (falls back to yesterday)."""
    from datetime import timedelta
    today = datetime.now(dt_tz.utc)
    keys = list_nexrad_scans(station_code, today)
    if not keys:
        yesterday = today - timedelta(days=1)
        keys = list_nexrad_scans(station_code, yesterday)
    return keys[-1] if keys else None


def download_nexrad(s3_key, dest_path):
    """
    Download a NEXRAD Level 2 file from S3 to dest_path.
    Returns dest_path on success.
    """
    if os.path.exists(dest_path):
        logger.debug('download_nexrad: already cached %s', dest_path)
        return dest_path
    client = get_s3_client()
    logger.info('download_nexrad: downloading s3://%s/%s', settings.AWS_NEXRAD_BUCKET, s3_key)
    client.download_file(settings.AWS_NEXRAD_BUCKET, s3_key, dest_path)
    return dest_path


# ── MRMS ──────────────────────────────────────────────────────────────────────

MRMS_PRODUCT_PATHS = {
    'reflectivity': 'CONUS/MergedReflectivityQC_00.00',
    'precip_type':  'CONUS/PrecipFlag_00.00',
    'mesh':         'CONUS/MESH_Max_60min_00.50',
}


def list_mrms_files(product, date):
    """
    List MRMS S3 keys for a given product and date.
    S3 path: noaa-mrms-pds/CONUS/<product>/YYYYMMDD/
    Returns sorted list of S3 keys.
    """
    client = get_s3_client()
    product_path = MRMS_PRODUCT_PATHS.get(product, MRMS_PRODUCT_PATHS['reflectivity'])
    prefix = f"{product_path}/{date.strftime('%Y%m%d')}/"
    keys = []
    paginator = client.get_paginator('list_objects_v2')
    try:
        for page in paginator.paginate(Bucket=settings.AWS_MRMS_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.grib2.gz'):
                    keys.append(key)
    except Exception as exc:
        logger.error('list_mrms_files(%s, %s): %s', product, date, exc)
    return sorted(keys)


def get_latest_mrms_key(product):
    """Return the most recent MRMS S3 key for the given product."""
    from datetime import timedelta
    today = datetime.now(dt_tz.utc)
    keys = list_mrms_files(product, today)
    if not keys:
        yesterday = today - timedelta(days=1)
        keys = list_mrms_files(product, yesterday)
    return keys[-1] if keys else None


def download_mrms(s3_key, dest_path):
    """
    Download an MRMS grib2.gz file from S3 to dest_path.
    Returns dest_path on success.
    """
    if os.path.exists(dest_path):
        logger.debug('download_mrms: already cached %s', dest_path)
        return dest_path
    client = get_s3_client()
    logger.info('download_mrms: downloading s3://%s/%s', settings.AWS_MRMS_BUCKET, s3_key)
    client.download_file(settings.AWS_MRMS_BUCKET, s3_key, dest_path)
    return dest_path
