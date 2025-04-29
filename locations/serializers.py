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
        passageiro = data.get('passageiro')
        # 1) continua garantindo que é passageiro
        if passageiro.tipo != 'passageiro':
            raise serializers.ValidationError("Dispositivo informado não é um passageiro.")

        # 2) checa se já existe corrida aberta
        aberto = SolicitacaoCorrida.objects.filter(
            passageiro=passageiro,
            status__in=['pending', 'accepted', 'started']
        ).exists()
        if aberto:
            raise serializers.ValidationError("Você já tem uma corrida em andamento.")

        return data

    def create(self, validated_data):
        # fixa expiracao em 5 minutos a partir de agora
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
