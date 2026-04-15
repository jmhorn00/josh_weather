from django.contrib import admin
from .models import (
    RadarStation, ActiveStation, MRMSTile,
    RadarScan, RadarTile, HailReport, NWSAlert,
)


@admin.register(RadarStation)
class RadarStationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'state', 'latitude', 'longitude', 'elevation', 'is_active', 'last_scan_time')
    list_filter = ('is_active', 'state', 'region')
    search_fields = ('code', 'name', 'state')
    ordering = ('state', 'code')
    readonly_fields = ('last_scan_time',)


@admin.register(ActiveStation)
class ActiveStationAdmin(admin.ModelAdmin):
    list_display = ('station', 'activated_at', 'expires_at')
    readonly_fields = ('activated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('station')


@admin.register(MRMSTile)
class MRMSTileAdmin(admin.ModelAdmin):
    list_display = ('product', 'valid_time', 'processed', 'fetched_at', 's3_key')
    list_filter = ('product', 'processed')
    ordering = ('-valid_time',)
    readonly_fields = ('fetched_at',)


@admin.register(RadarScan)
class RadarScanAdmin(admin.ModelAdmin):
    list_display = ('station', 'scan_time', 'processed', 'fetched_at', 's3_key')
    list_filter = ('processed', 'station__state')
    search_fields = ('station__code', 's3_key')
    ordering = ('-scan_time',)
    readonly_fields = ('fetched_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('station')


@admin.register(RadarTile)
class RadarTileAdmin(admin.ModelAdmin):
    list_display = ('get_station_code', 'product', 'valid_time', 'created_at')
    list_filter = ('product',)
    ordering = ('-valid_time',)
    readonly_fields = ('created_at',)

    def get_station_code(self, obj):
        return obj.scan.station.code
    get_station_code.short_description = 'Station'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('scan__station')


@admin.register(HailReport)
class HailReportAdmin(admin.ModelAdmin):
    list_display = ('get_station_code', 'valid_time', 'max_mesh_mm', 'created_at')
    ordering = ('-valid_time',)
    readonly_fields = ('created_at',)

    def get_station_code(self, obj):
        return obj.scan.station.code
    get_station_code.short_description = 'Station'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('scan__station')


@admin.register(NWSAlert)
class NWSAlertAdmin(admin.ModelAdmin):
    list_display = ('event', 'severity', 'area_desc', 'sent', 'expires', 'nws_office')
    list_filter = ('event', 'severity', 'status')
    search_fields = ('event', 'area_desc', 'alert_id')
    ordering = ('-sent',)
    readonly_fields = ('fetched_at',)
