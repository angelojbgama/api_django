# locations/admin.py

from django.contrib import admin
from .models import DeviceLocation, RideRequest, RidePosition

# ================================================
# Inline para exibir as posições de cada corrida
# dentro da interface de RideRequest
# ================================================
class RidePositionInline(admin.TabularInline):
    model = RidePosition
    extra = 0                 # não exibe linhas em branco adicionais
    readonly_fields = (
        'latitude',
        'longitude',
        'timestamp',
    )                         # campos somente leitura no inline
    # evita que posições sejam criadas/alteradas pelo admin via inline
    can_delete = False        

# ================================================
# Configuração de admin para o modelo RideRequest
# ================================================
@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = (
        'ride_id',
        'user_id',
        'driver_id',
        'status',
        'created_at',
    )                         # colunas exibidas na lista de objetos
    list_filter = (
        'status',
        'created_at',
    )                         # filtros laterais por status e data
    search_fields = (
        'ride_id',
        'user_id',
        'driver_id',
    )                         # campo de busca
    readonly_fields = (
        'created_at',
    )                         # campos somente leitura no detalhe
    inlines = (
        RidePositionInline,
    )                         # incorpora o inline de posições

# ================================================
# Configuração de admin para o modelo RidePosition
# (caso queira vê-las isoladamente)
# ================================================
@admin.register(RidePosition)
class RidePositionAdmin(admin.ModelAdmin):
    list_display = (
        'ride',
        'latitude',
        'longitude',
        'timestamp',
    )
    list_filter = (
        'ride',
        'timestamp',
    )
    search_fields = (
        'ride__ride_id',
    )
    readonly_fields = (
        'ride',
        'latitude',
        'longitude',
        'timestamp',
    )

# ================================================
# Configuração de admin para o modelo DeviceLocation
# ================================================
@admin.register(DeviceLocation)
class DeviceLocationAdmin(admin.ModelAdmin):
    list_display = (
        'device_type',
        'device_id',
        'latitude',
        'longitude',
        'timestamp',
    )
    list_filter = (
        'device_type',
        'timestamp',
    )
    search_fields = (
        'device_id',
    )
    readonly_fields = (
        'timestamp',
    )                         # timestamp gerado automaticamente, então readonly
