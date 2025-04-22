from rest_framework import serializers
from .models import Passageiro, EcoTaxi, SolicitacaoCorrida
from django.utils import timezone

# Serializer para Passageiro
class PassageiroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Passageiro
        fields = '__all__'


# Serializer para EcoTaxi
class EcoTaxiSerializer(serializers.ModelSerializer):
    class Meta:
        model = EcoTaxi
        fields = '__all__'


# Serializer para criação de solicitação de corrida
class SolicitacaoCorridaCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            'passageiro',
            'latitude_destino',
            'longitude_destino',
            'endereco_destino',
            'assentos_necessarios'
        ]

    def validate(self, data):
        # Valida se o passageiro existe
        if not Passageiro.objects.filter(id=data['passageiro'].id).exists():
            raise serializers.ValidationError("Passageiro inválido.")
        return data

    def create(self, validated_data):
        validated_data['expiracao'] = timezone.now() + timezone.timedelta(minutes=1)
        return super().create(validated_data)


# Serializer para leitura (incluir EcoTaxi e status)
class SolicitacaoCorridaDetailSerializer(serializers.ModelSerializer):
    passageiro = PassageiroSerializer()
    eco_taxi = EcoTaxiSerializer()

    class Meta:
        model = SolicitacaoCorrida
        fields = '__all__'

# Serializer para listar corridas atribuídas ao EcoTaxi
class CorridaEcoTaxiListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            'id',
            'endereco_destino',
            'latitude_destino',
            'longitude_destino',
            'assentos_necessarios',
            'status',
            'expiracao'
        ]
