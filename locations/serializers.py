from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Dispositivo, SolicitacaoCorrida


class DispositivoSerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(required=True)

    class Meta:
        model = Dispositivo
        fields = "__all__"


class SolicitacaoCorridaCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            "passageiro",
            "latitude_partida",
            "longitude_partida",
            "endereco_partida",
            "latitude_destino",
            "longitude_destino",
            "endereco_destino",
            "assentos_necessarios",
        ]

    def validate(self, data):
        passageiro = data.get("passageiro")
        if passageiro.tipo != "passageiro":
            raise serializers.ValidationError("Dispositivo informado não é um passageiro.")

        aberto = SolicitacaoCorrida.objects.filter(
            passageiro=passageiro,
            status__in=["pending", "accepted", "started"],
        ).exists()
        if aberto:
            raise serializers.ValidationError("Você já tem uma corrida em andamento.")

        return data

    def create(self, validated_data):
        # fixa expiração 5 minutos à frente
        validated_data["expiracao"] = timezone.now() + timedelta(minutes=5)
        return super().create(validated_data)


class SolicitacaoCorridaDetailSerializer(serializers.ModelSerializer):
    passageiro = DispositivoSerializer()
    eco_taxi   = DispositivoSerializer()

    class Meta:
        model = SolicitacaoCorrida
        fields = "__all__"


class CorridaEcoTaxiListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoCorrida
        fields = [
            "id",
            "uuid",
            "endereco_partida",
            "endereco_destino",
            "latitude_partida",
            "longitude_partida",
            "latitude_destino",
            "longitude_destino",
            "assentos_necessarios",
            "status",
            "expiracao",
        ]
