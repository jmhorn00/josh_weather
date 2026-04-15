from django.db import models
from django.utils import timezone

NWS_ALERT_COLORS = {
    'Tornado Emergency':            '#FF0000',
    'Tornado Warning':              '#FF0000',
    'Severe Thunderstorm Warning':  '#FFA500',
    'Tornado Watch':                '#FFFF00',
    'Severe Thunderstorm Watch':    '#DB7093',
    'Flash Flood Emergency':        '#8B0000',
    'Flash Flood Warning':          '#008B00',
    'Flash Flood Watch':            '#2E8B57',
    'Flood Warning':                '#00FF00',
    'Winter Storm Warning':         '#FF69B4',
    'Ice Storm Warning':            '#8B008B',
    'Blizzard Warning':             '#FF4500',
    'High Wind Warning':            '#DAA520',
    'Excessive Heat Warning':       '#C71585',
    'Special Weather Statement':    '#FFE4B5',
}


class RadarStation(models.Model):
    code = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()
    elevation = models.IntegerField()
    is_active = models.BooleanField(default=True)
    region = models.CharField(max_length=50, blank=True)
    last_scan_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['state', 'code']

    def __str__(self):
        return f"{self.code} — {self.name}, {self.state}"


class ActiveStation(models.Model):
    station = models.OneToOneField(RadarStation, on_delete=models.CASCADE)
    activated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=['expires_at'])]

    def __str__(self):
        return f"{self.station.code} (expires {self.expires_at})"


class MRMSTile(models.Model):
    PRODUCT_CHOICES = [
        ('reflectivity', 'Merged Reflectivity QC'),
        ('precip_type', 'Precipitation Type'),
        ('mesh', 'MESH Hail 60-min Max'),
    ]
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    valid_time = models.DateTimeField(db_index=True)
    s3_key = models.CharField(max_length=500, unique=True)
    tile_path = models.CharField(max_length=500, blank=True)
    bounds_json = models.JSONField()
    processed = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-valid_time']
        indexes = [models.Index(fields=['product', '-valid_time'])]

    def __str__(self):
        return f"MRMS {self.product} @ {self.valid_time}"


class RadarScan(models.Model):
    station = models.ForeignKey(RadarStation, on_delete=models.CASCADE)
    s3_key = models.CharField(max_length=255, unique=True)
    scan_time = models.DateTimeField(db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    local_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-scan_time']
        indexes = [models.Index(fields=['station', '-scan_time'])]

    def __str__(self):
        return f"{self.station.code} scan @ {self.scan_time}"


class RadarTile(models.Model):
    PRODUCT_CHOICES = [
        ('reflectivity', 'Reflectivity'),
        ('velocity', 'Velocity'),
        ('mesh', 'MESH Hail'),
        ('nowcast_00', 'Nowcast +0min'),
        ('nowcast_15', 'Nowcast +15min'),
        ('nowcast_30', 'Nowcast +30min'),
        ('nowcast_45', 'Nowcast +45min'),
        ('nowcast_60', 'Nowcast +60min'),
    ]
    scan = models.ForeignKey(RadarScan, on_delete=models.CASCADE)
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    valid_time = models.DateTimeField()
    tile_path = models.CharField(max_length=500)
    bounds_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['scan', 'product']]
        indexes = [models.Index(fields=['product', '-valid_time'])]

    def __str__(self):
        return f"{self.scan.station.code} {self.product} @ {self.valid_time}"


class HailReport(models.Model):
    scan = models.OneToOneField(RadarScan, on_delete=models.CASCADE)
    valid_time = models.DateTimeField()
    max_mesh_mm = models.FloatField()
    geojson = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Hail {self.scan.station.code} @ {self.valid_time} max={self.max_mesh_mm}mm"


class NWSAlert(models.Model):
    alert_id = models.CharField(max_length=255, unique=True)
    event = models.CharField(max_length=100)
    severity = models.CharField(max_length=20)
    headline = models.TextField()
    description = models.TextField(blank=True)
    instruction = models.TextField(blank=True)
    area_desc = models.TextField()
    sent = models.DateTimeField()
    effective = models.DateTimeField()
    expires = models.DateTimeField(db_index=True)
    onset = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20)
    message_type = models.CharField(max_length=20)
    geojson = models.JSONField(null=True, blank=True)
    nws_office = models.CharField(max_length=10, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self):
        return self.expires > timezone.now()

    @property
    def map_color(self):
        return NWS_ALERT_COLORS.get(self.event, '#999999')

    class Meta:
        ordering = ['-sent']
        indexes = [
            models.Index(fields=['expires']),
            models.Index(fields=['event', 'expires']),
        ]

    def __str__(self):
        return f"{self.event} — {self.area_desc[:50]}"
