from django.contrib import admin
from .models import Passageiro, EcoTaxi, SolicitacaoCorrida


@admin.register(Passageiro)
class PassageiroAdmin(admin.ModelAdmin):
    list_display = ('nome', 'uuid', 'criado_em')
    search_fields = ('nome', 'uuid')
    ordering = ('-criado_em',)
    readonly_fields = ('uuid', 'criado_em')


@admin.register(EcoTaxi)
class EcoTaxiAdmin(admin.ModelAdmin):
    list_display = ('nome', 'uuid', 'status', 'assentos_disponiveis', 'latitude', 'longitude', 'atualizado_em')
    list_filter = ('status',)
    search_fields = ('nome', 'uuid')
    ordering = ('-atualizado_em',)
    readonly_fields = ('uuid', 'atualizado_em')


@admin.register(SolicitacaoCorrida)
class SolicitacaoCorridaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'passageiro', 'eco_taxi', 'status',
        'assentos_necessarios', 'endereco_destino',
        'criada_em', 'expiracao'
    )
    list_filter = ('status', 'criada_em')
    search_fields = ('passageiro__nome', 'eco_taxi__nome', 'endereco_destino')
    ordering = ('-criada_em',)
    autocomplete_fields = ('passageiro', 'eco_taxi')
    readonly_fields = ('criada_em', 'expiracao')
