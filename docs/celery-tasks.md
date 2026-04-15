# Celery Tasks

All tasks are defined in `apps/radar/tasks.py`. All tasks are idempotent — safe to call multiple times with the same arguments.

## Beat Schedule

| Task | Interval | Purpose |
|------|----------|---------|
| `poll_mrms_mosaic` | every 120s | Download + render latest MRMS national mosaic |
| `poll_active_stations` | every 90s | Trigger scan checks for all active stations |
| `poll_nws_alerts` | every 60s | Fetch + upsert national NWS alerts |
| `cleanup_old_data` | hourly (`:00`) | Delete old tiles, scans, reports, alerts |

The Beat scheduler uses `django_celery_beat.schedulers:DatabaseScheduler`. Schedules are stored in the PostgreSQL `django_celery_beat_*` tables.

---

## Task Reference

### `poll_mrms_mosaic`

**Trigger:** Beat, every 120 seconds  
**Retries:** 3 (30-second cooldown)  

```
1. get_latest_mrms_key('reflectivity') → S3 key
2. Check MRMSTile.objects.filter(s3_key=key).exists() → skip if already done
3. download_mrms(key, dest) → local .grib2.gz file
4. parse_mrms_grib(path) → xarray Dataset
5. render_mrms_reflectivity(ds, output_path) → PNG + bounds
6. MRMSTile.objects.create(..., processed=True)
7. Delete MRMSTile records + files older than 60 minutes
```

---

### `poll_active_stations`

**Trigger:** Beat, every 90 seconds  
**Retries:** 3  

```
1. Query ActiveStation.objects.filter(expires_at__gt=now())
2. For each: check_station_for_new_scans.delay(code)
3. Delete expired ActiveStation records
```

---

### `check_station_for_new_scans`

**Trigger:** `poll_active_stations`, `activate_station`  
**Args:** `station_code` (str)  
**Retries:** 3 (30-second cooldown)  

```
1. list_nexrad_scans(code, today) → list of S3 keys
2. If empty, try yesterday (UTC rollover handling)
3. Find keys not yet in RadarScan table
4. process_nexrad_scan.delay(code, key) for each new key (max 5)
```

---

### `process_nexrad_scan`

**Trigger:** `check_station_for_new_scans`  
**Args:** `station_code` (str), `s3_key` (str)  
**Retries:** 3 (60-second cooldown)  

```
1. RadarScan.objects.get_or_create(s3_key=key) → idempotency check
2. download_nexrad(key, dest) → local file
3. Parse scan time from filename
4. load_nexrad(path) → Py-ART Radar
5. dealias_velocity(radar) → adds 'dealiased_velocity' field
6. radar_to_grid(radar, ['reflectivity', 'velocity']) → Cartesian Grid
7. render_reflectivity_tile(grid, path) → RadarTile(product='reflectivity')
8. render_velocity_tile(grid, path) → RadarTile(product='velocity')
9. calculate_mesh(radar) → HailReport
10. scan.processed = True; station.last_scan_time = scan.scan_time
11. If processed_count >= 4: generate_nowcast.delay(code)
```

**Typical duration:** 30–90 seconds depending on server speed.

---

### `generate_nowcast`

**Trigger:** `process_nexrad_scan` (when station has ≥ 4 processed scans)  
**Args:** `station_code` (str)  
**Retries:** 0 (failure is non-critical)  

```
1. Fetch last 4 processed RadarScan records (ordered by scan_time)
2. load_nexrad + radar_to_grid for each
3. build_precip_stack(grids) → (4, H, W) numpy array
4. run_nowcast(stack) → list of 12 forecast arrays
5. For each array:
   - Determine product name (nowcast_00 … nowcast_60)
   - render_nowcast_tile(array, path) → PNG
   - RadarTile.update_or_create(scan=latest_scan, product=...)
```

**Typical duration:** 15–45 seconds.

---

### `activate_station`

**Trigger:** Called directly from `station_activate` view (also importable as a task)  
**Args:** `station_code` (str)  

```
1. RadarStation.objects.get(code=code)
2. ActiveStation.update_or_create(station, expires_at=now()+TTL)
3. check_station_for_new_scans.delay(code)
```

---

### `poll_nws_alerts`

**Trigger:** Beat, every 60 seconds  
**Retries:** 3 (30-second cooldown)  

```
1. fetch_active_alerts() → GET api.weather.gov/alerts/active
2. For each feature: parse_alert(feature) → dict
3. upsert_alert(dict) → NWSAlert.update_or_create(alert_id=...)
4. expire_old_alerts() → delete NWSAlert where expires < now()
```

---

### `cleanup_old_data`

**Trigger:** Beat, hourly at `:00`  

```
Deletes:
- MRMSTile + files older than 2 hours
- RadarScan + files older than 24h (only for stations NOT in ActiveStation)
- RadarTile records older than 24h
- HailReport records older than 24h
- Expired NWSAlert records
```

Logs a summary of counts deleted for each model.

---

## Monitoring Tasks

### View task queue depth (Redis CLI)

```bash
docker compose exec redis redis-cli llen celery
```

### View recent task results

```bash
docker compose exec web python manage.py shell -c "
from celery.result import AsyncResult
# Paste a task ID from logs
r = AsyncResult('your-task-id-here')
print(r.state, r.result)
"
```

### Purge all queued tasks (use with caution)

```bash
docker compose exec worker celery -A config purge
```

### Trigger tasks manually

```bash
docker compose run --rm web python manage.py shell -c "
from apps.radar.tasks import poll_mrms_mosaic, poll_nws_alerts
poll_mrms_mosaic.delay()
poll_nws_alerts.delay()
"
```

---

## Task Failure Handling

All tasks with `bind=True` use `self.retry(exc=exc, countdown=N)` on failure. This means:

- The task is re-queued with a delay (not retried immediately)
- After `max_retries` attempts the exception propagates and is logged
- Celery marks the task as `FAILURE`
- Sentry captures the exception in production (if `SENTRY_DSN` is configured)

The MRMS and NEXRAD tasks are idempotent so retrying is always safe.
