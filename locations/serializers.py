from rest_framework import serializers
from .models import Dispositivo, SolicitacaoCorrida
from django.utils import timezone


class DispositivoSerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(required=True, read_only=False)
    class Meta:
        model  = Dispositivo
        fields = '__all__'


class SolicitacaoCorridaCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            'passageiro',
            'latitude_partida',
            'longitude_partida',
            'endereco_partida',
            'latitude_destino',
            'longitude_destino',
            'endereco_destino',
            'assentos_necessarios'
        ]

    def validate(self, data):
        if data['passageiro'].tipo != 'passageiro':
            raise serializers.ValidationError("Dispositivo informado não é um passageiro.")
        return data

    def create(self, validated_data):
        validated_data['expiracao'] = timezone.now() + timezone.timedelta(minutes=5)
        return super().create(validated_data)


class SolicitacaoCorridaDetailSerializer(serializers.ModelSerializer):
    passageiro = DispositivoSerializer()
    eco_taxi = DispositivoSerializer()

    class Meta:
        model = SolicitacaoCorrida
        fields = '__all__'


class CorridaEcoTaxiListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            'id',
            'uuid',
            'endereco_partida',
            'endereco_destino',
            'latitude_partida',
            'longitude_partida',
            'latitude_destino',
            'longitude_destino',
            'assentos_necessarios',
            'status',
            'expiracao'
        ]
