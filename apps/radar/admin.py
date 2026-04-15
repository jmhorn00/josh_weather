from datetime import timedelta

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.db.models import Count, Max
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from django.shortcuts import render

from .models import (
    RadarStation, ActiveStation, MRMSTile,
    RadarScan, RadarTile, HailReport, NWSAlert,
)


# ── Custom Admin Site with dashboard ─────────────────────────────────────────

class WxRadarAdminSite(AdminSite):
    site_header = 'WxRadar Administration'
    site_title = 'WxRadar Admin'
    index_title = 'System Dashboard'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
        ]
        return custom + urls

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['dashboard_stats'] = self._get_dashboard_stats()
        return super().index(request, extra_context)

    def _get_dashboard_stats(self):
        now = timezone.now()
        one_hour_ago = now - timedelta(hours=1)

        # Active stations
        active_stations = list(
            ActiveStation.objects.filter(expires_at__gt=now)
            .select_related('station')
            .order_by('station__code')
        )

        # MRMS freshness
        latest_mrms = MRMSTile.objects.filter(
            product='reflectivity', processed=True
        ).order_by('-valid_time').first()
        mrms_age_min = None
        mrms_status = 'no-data'
        if latest_mrms:
            mrms_age_min = int((now - latest_mrms.valid_time).total_seconds() / 60)
            mrms_status = 'ok' if mrms_age_min < 5 else ('warn' if mrms_age_min < 15 else 'stale')

        # Alert counts by severity
        alert_counts = dict(
            NWSAlert.objects.filter(expires__gt=now)
            .values('severity')
            .annotate(n=Count('id'))
            .values_list('severity', 'n')
        )
        total_alerts = sum(alert_counts.values())

        # Recent scan counts (last hour)
        scans_last_hour = RadarScan.objects.filter(fetched_at__gte=one_hour_ago).count()
        unprocessed = RadarScan.objects.filter(processed=False).count()

        # Tile counts
        mrms_tile_count = MRMSTile.objects.filter(processed=True).count()
        station_tile_count = RadarTile.objects.count()

        return {
            'active_stations': active_stations,
            'active_count': len(active_stations),
            'latest_mrms': latest_mrms,
            'mrms_age_min': mrms_age_min,
            'mrms_status': mrms_status,
            'total_alerts': total_alerts,
            'alert_counts': alert_counts,
            'scans_last_hour': scans_last_hour,
            'unprocessed_scans': unprocessed,
            'mrms_tile_count': mrms_tile_count,
            'station_tile_count': station_tile_count,
        }

    def dashboard_view(self, request):
        stats = self._get_dashboard_stats()
        context = {
            **self.each_context(request),
            'title': 'System Dashboard',
            'stats': stats,
        }
        return render(request, 'admin/dashboard.html', context)


admin_site = WxRadarAdminSite(name='wxradar_admin')


# ── Model Admins ──────────────────────────────────────────────────────────────

@admin.register(RadarStation, site=admin_site)
class RadarStationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'state', 'latitude', 'longitude',
                    'elevation', 'is_active', 'last_scan_time', 'is_currently_active')
    list_filter = ('is_active', 'state', 'region')
    search_fields = ('code', 'name', 'state')
    ordering = ('state', 'code')
    readonly_fields = ('last_scan_time',)

    def is_currently_active(self, obj):
        active = ActiveStation.objects.filter(
            station=obj, expires_at__gt=timezone.now()
        ).exists()
        color = '#28a745' if active else '#6c757d'
        label = 'Active' if active else 'Idle'
        return format_html('<span style="color:{};font-weight:bold;">{}</span>', color, label)
    is_currently_active.short_description = 'Polling'


@admin.register(ActiveStation, site=admin_site)
class ActiveStationAdmin(admin.ModelAdmin):
    list_display = ('station', 'activated_at', 'expires_at', 'time_remaining')
    readonly_fields = ('activated_at',)

    def time_remaining(self, obj):
        remaining = obj.expires_at - timezone.now()
        total_sec = int(remaining.total_seconds())
        if total_sec <= 0:
            return format_html('<span style="color:#dc3545;">Expired</span>')
        mins = total_sec // 60
        secs = total_sec % 60
        return format_html('<span style="color:#28a745;">{}m {}s</span>', mins, secs)
    time_remaining.short_description = 'Remaining TTL'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('station')


@admin.register(MRMSTile, site=admin_site)
class MRMSTileAdmin(admin.ModelAdmin):
    list_display = ('product', 'valid_time', 'age_minutes', 'processed', 'fetched_at')
    list_filter = ('product', 'processed')
    ordering = ('-valid_time',)
    readonly_fields = ('fetched_at',)

    def age_minutes(self, obj):
        mins = int((timezone.now() - obj.valid_time).total_seconds() / 60)
        color = '#28a745' if mins < 5 else ('#ffc107' if mins < 15 else '#dc3545')
        return format_html('<span style="color:{};">{}m ago</span>', color, mins)
    age_minutes.short_description = 'Age'


@admin.register(RadarScan, site=admin_site)
class RadarScanAdmin(admin.ModelAdmin):
    list_display = ('station', 'scan_time', 'processed', 'fetched_at', 's3_key_short')
    list_filter = ('processed', 'station__state')
    search_fields = ('station__code', 's3_key')
    ordering = ('-scan_time',)
    readonly_fields = ('fetched_at',)

    def s3_key_short(self, obj):
        return obj.s3_key.split('/')[-1] if obj.s3_key else ''
    s3_key_short.short_description = 'File'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('station')


@admin.register(RadarTile, site=admin_site)
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


@admin.register(HailReport, site=admin_site)
class HailReportAdmin(admin.ModelAdmin):
    list_display = ('get_station_code', 'valid_time', 'max_mesh_mm', 'hail_size_label', 'created_at')
    ordering = ('-valid_time',)
    readonly_fields = ('created_at',)

    def get_station_code(self, obj):
        return obj.scan.station.code
    get_station_code.short_description = 'Station'

    def hail_size_label(self, obj):
        mm = obj.max_mesh_mm
        if mm >= 51:
            label, color = 'Softball 2"+ ', '#8b0000'
        elif mm >= 38:
            label, color = 'Baseball 2"', '#dc3545'
        elif mm >= 25:
            label, color = 'Golf Ball 1.5"', '#fd7e14'
        elif mm >= 19:
            label, color = 'Quarter 1"', '#ffc107'
        else:
            label, color = 'Small', '#6c757d'
        return format_html('<span style="color:{};">{}</span>', color, label)
    hail_size_label.short_description = 'Size'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('scan__station')


@admin.register(NWSAlert, site=admin_site)
class NWSAlertAdmin(admin.ModelAdmin):
    list_display = ('colored_event', 'severity', 'area_desc_short', 'sent', 'expires',
                    'nws_office', 'is_active_now')
    list_filter = ('event', 'severity', 'status')
    search_fields = ('event', 'area_desc', 'alert_id')
    ordering = ('-sent',)
    readonly_fields = ('fetched_at',)

    def colored_event(self, obj):
        color = obj.map_color
        return format_html(
            '<span style="display:inline-block;width:10px;height:10px;'
            'background:{};border-radius:50%;margin-right:6px;"></span>{}',
            color, obj.event
        )
    colored_event.short_description = 'Event'

    def area_desc_short(self, obj):
        return obj.area_desc[:60] + ('…' if len(obj.area_desc) > 60 else '')
    area_desc_short.short_description = 'Area'

    def is_active_now(self, obj):
        if obj.is_active:
            return format_html('<span style="color:#28a745;font-weight:bold;">Active</span>')
        return format_html('<span style="color:#6c757d;">Expired</span>')
    is_active_now.short_description = 'Status'


# Also register with the default admin site (for compatibility)
admin.register(RadarStation)(RadarStationAdmin)
admin.register(ActiveStation)(ActiveStationAdmin)
admin.register(MRMSTile)(MRMSTileAdmin)
admin.register(RadarScan)(RadarScanAdmin)
admin.register(RadarTile)(RadarTileAdmin)
admin.register(HailReport)(HailReportAdmin)
admin.register(NWSAlert)(NWSAlertAdmin)
