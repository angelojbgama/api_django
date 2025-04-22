from django.contrib import admin
from .models import Dispositivo, SolicitacaoCorrida


@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = (
        'nome', 'uuid', 'tipo', 'status', 'assentos_disponiveis',
        'latitude', 'longitude', 'criado_em', 'atualizado_em'
    )
    list_filter = ('tipo', 'status')
    search_fields = ('nome', 'uuid')
    ordering = ('-atualizado_em',)
    readonly_fields = ('uuid', 'criado_em', 'atualizado_em')


@admin.register(SolicitacaoCorrida)
class SolicitacaoCorridaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'passageiro', 'eco_taxi', 'status',
        'assentos_necessarios', 'endereco_partida',
        'endereco_destino', 'criada_em', 'expiracao'
    )
    list_filter = ('status', 'criada_em')
    search_fields = (
        'passageiro__nome', 'eco_taxi__nome',
        'endereco_partida', 'endereco_destino'
    )
    ordering = ('-criada_em',)
    autocomplete_fields = ('passageiro', 'eco_taxi')
    readonly_fields = ('criada_em', 'expiracao')
