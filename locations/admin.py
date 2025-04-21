# locations/admin.py

from django.contrib import admin
from .models import DeviceLocation, RideRequest, RidePosition

# ---------------------------------------------------
# Inline para exibir Histórico de Posições na RideRequest
# ---------------------------------------------------
class RidePositionInline(admin.TabularInline):
    model = RidePosition
    extra = 0
    readonly_fields = ('latitude', 'longitude', 'timestamp')
    can_delete = False
    verbose_name = 'Posição da Corrida'
    verbose_name_plural = 'Posições da Corrida'

# ---------------------------------------------------
# Admin para RideRequest (solicitação de corrida)
# ---------------------------------------------------
@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = (
        'ride_id',
        'user_id',
        'driver_id',
        'pickup_latitude',
        'pickup_longitude',
        'status',
        'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('ride_id', 'user_id', 'driver_id')
    readonly_fields = ('ride_id', 'created_at')
    fieldsets = (
        (None, {
            'fields': (
                'ride_id',
                'user_id',
                'driver_id',
                ('pickup_latitude', 'pickup_longitude'),
                'status',
                'created_at',
            )
        }),
    )
    inlines = (RidePositionInline,)
    ordering = ('-created_at',)

# ---------------------------------------------------
# Admin para RidePosition (posição ao longo da corrida)
# ---------------------------------------------------
@admin.register(RidePosition)
class RidePositionAdmin(admin.ModelAdmin):
    list_display = ('ride', 'latitude', 'longitude', 'timestamp')
    list_filter = ('ride', 'timestamp')
    search_fields = ('ride__ride_id',)
    readonly_fields = ('ride', 'latitude', 'longitude', 'timestamp')
    ordering = ('-timestamp',)

# ---------------------------------------------------
# Admin para DeviceLocation (última posição de cada device)
# ---------------------------------------------------
@admin.register(DeviceLocation)
class DeviceLocationAdmin(admin.ModelAdmin):
    list_display = (
        'device_type',
        'device_id',
        'latitude',
        'longitude',
        'seats_available',
        'timestamp',
    )
    list_filter = ('device_type', 'seats_available', 'timestamp')
    search_fields = ('device_id',)
    readonly_fields = ('timestamp',)
    fieldsets = (
        (None, {
            'fields': (
                'device_type',
                'device_id',
                ('latitude', 'longitude'),
                'seats_available',
                'timestamp',
            )
        }),
    )
    ordering = ('-timestamp',)
