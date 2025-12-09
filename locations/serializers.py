from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Dispositivo, SolicitacaoCorrida


class DispositivoSerializer(serializers.ModelSerializer):
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
            raise serializers.ValidationError(
                "Dispositivo informado não é um passageiro."
            )

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
    eco_taxi = DispositivoSerializer()

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


class CorridaPassageiroListSerializer(serializers.ModelSerializer):
    """
    Serializer enxuto para histórico de corridas de um passageiro,
    incluindo o nome do ecotaxi (se houver).
    """

    ecotaxi_nome = serializers.CharField(
        source="eco_taxi.nome",
        read_only=True,
        default=None,
        help_text="Nome do EcoTaxi que atendeu a corrida (ou null)",
    )

    class Meta:
        model = SolicitacaoCorrida
        fields = [
            "uuid",
            "criada_em",
            "status",
            "assentos_necessarios",
            "endereco_partida",
            "endereco_destino",
            "ecotaxi_nome",
        ]
        read_only_fields = fields


class DispositivoUpdateSerializer(serializers.ModelSerializer):
    """
    Campos opcionais; validados conforme o tipo do dispositivo.
    """

    class Meta:
        model = Dispositivo
        fields = ["nome", "cor_ecotaxi", "assentos_disponiveis"]

        # todos opcionais → partial=True
        extra_kwargs = {f: {"required": False} for f in fields}

    def validate(self, attrs):
        dispositivo: Dispositivo = self.instance  # já carregado na view

        if dispositivo.tipo == "passageiro" and "cor_ecotaxi" in attrs:
            raise serializers.ValidationError(
                {"cor_ecotaxi": "Somente EcoTaxi pode alterar este campo."}
            )

        return attrs
