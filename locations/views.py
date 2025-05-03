# views.py
# Revisão 2025-05-14  –  novo fluxo de assentos
# • NÃO debita assentos na criação (pending)
# • Debita apenas quando o EcoTaxi aceita (accepted)
# • Devolve somente se a corrida estava accepted / started

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.db import transaction, IntegrityError
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Dispositivo, SolicitacaoCorrida
from .serializers import (
    CorridaEcoTaxiListSerializer,
    CorridaPassageiroListSerializer,
    DispositivoSerializer,
    DispositivoUpdateSerializer,
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer,
)
from locations.utils.ecotaxi_matching import (
    escolher_ecotaxi,
    repassar_para_proximo_ecotaxi,
)


# ────────────────────────────────────────────────────────────────
# 1) CRIAR CORRIDA  –  NADA de assentos aqui
# ────────────────────────────────────────────────────────────────
class CriarCorridaView(CreateAPIView):
    """
    POST /api/corrida/nova/
    Se houver EcoTaxi disponível ele já é vinculado,
    mas os assentos só serão debitados quando o motorista aceitar.
    """

    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        eco = escolher_ecotaxi(
            validated["latitude_partida"],
            validated["longitude_partida"],
            validated["assentos_necessarios"],
        )
        if eco is None:
            return Response(
                {"mensagem": "Nenhum EcoTaxi disponível no momento."},
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            corrida = serializer.save()

            taxi = Dispositivo.objects.select_for_update().get(pk=eco.pk)
            taxi.status = "aguardando"  # aguardando resposta
            taxi.save(update_fields=["status"])

            corrida.eco_taxi = taxi
            corrida.expiracao = timezone.now() + timedelta(minutes=5)
            corrida.save(update_fields=["eco_taxi", "expiracao"])

        return Response(
            SolicitacaoCorridaDetailSerializer(corrida).data,
            status=status.HTTP_201_CREATED,
        )


# ────────────────────────────────────────────────────────────────
# 2) DETALHE
# ────────────────────────────────────────────────────────────────
class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()
        if corrida.status == "pending" and timezone.now() > corrida.expiracao:
            repassar_para_proximo_ecotaxi(corrida)
        return corrida


# ────────────────────────────────────────────────────────────────
# 3) ATUALIZAR STATUS (cancelar / concluir / etc.)
# ────────────────────────────────────────────────────────────────
class AtualizarStatusCorridaView(APIView):
    """
    PATCH /api/corrida/<uuid>/status/
    accepted / started  → só atualiza status/eco_taxi
    cancelled / completed → devolve assentos *SE* foi debitado
    rejected → repassa para outro e não devolve (ainda não debitou)
    """

    permission_classes = [AllowAny]

    def patch(self, request, uuid):
        corrida = get_object_or_404(SolicitacaoCorrida, uuid=uuid)
        novo = request.data.get("status")

        if novo not in {"accepted", "started", "rejected", "cancelled", "completed"}:
            return Response({"erro": "Status inválido."}, status=400)

        def _devolver():
            """
            Devolve os assentos ao EcoTaxi. Sempre deve ser chamado quando a corrida for
            cancelada ou concluída, pois os assentos já foram debitados na criação da corrida.
            """
            if corrida.eco_taxi_id:
                Dispositivo.objects.filter(pk=corrida.eco_taxi_id).update(
                    assentos_disponiveis=F("assentos_disponiveis") + corrida.assentos_necessarios,
                    status="aguardando",
                )

        if novo == "rejected":
            with transaction.atomic():
                corrida.eco_taxi = None
                corrida.status = "pending"
                corrida.expiracao = timezone.now() + timedelta(minutes=5)
                corrida.save(update_fields=["eco_taxi", "status", "expiracao"])
                repassar_para_proximo_ecotaxi(corrida)
            return Response({"mensagem": "Corrida recusada e repassada."})

        if novo == "cancelled":
            with transaction.atomic():
                _devolver()
                corrida.eco_taxi = None
                corrida.status = "cancelled"
                corrida.save(update_fields=["eco_taxi", "status"])
            return Response({"mensagem": "Corrida cancelada."})

        if novo == "completed":
            with transaction.atomic():
                _devolver()
                corrida.status = "completed"
                corrida.save(update_fields=["status"])
            return Response({"mensagem": "Corrida concluída."})

        if novo in {"accepted", "started"} and corrida.eco_taxi:
            corrida.eco_taxi.status = (
                "aguardando_resposta" if novo == "accepted" else "transito"
            )
            corrida.eco_taxi.save(update_fields=["status"])

        corrida.status = novo
        corrida.save(update_fields=["status"])
        return Response({"corrida": SolicitacaoCorridaDetailSerializer(corrida).data})


# ────────────────────────────────────────────────────────────────
# 5) CRUD DE DISPOSITIVO
# ────────────────────────────────────────────────────────────────
class DispositivoCreateView(generics.CreateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer


class AtualizarDispositivoView(generics.RetrieveUpdateAPIView):
    queryset = Dispositivo.objects.all()
    lookup_field = "uuid"
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        return (
            DispositivoUpdateSerializer
            if self.request.method.lower() == "patch"
            else DispositivoSerializer
        )

    def patch(self, request, *args, **kwargs):
        dispositivo = self.get_object()
        serializer = self.get_serializer(dispositivo, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "mensagem": "Dispositivo atualizado.",
                "dispositivo": DispositivoSerializer(dispositivo).data,
            }
        )


class AtualizarTipoDispositivoView(APIView):
    def patch(self, request, uuid):
        tipo = request.data.get("tipo")
        if tipo not in ["passageiro", "ecotaxi"]:
            return Response({"erro": "Tipo inválido"}, status=400)
        
        # 🔽 Cria o dispositivo automaticamente se não existir
        disp, _ = Dispositivo.objects.get_or_create(uuid=uuid, defaults={
            "nome": "Novo usuário",  # você pode ajustar isso
            "tipo": tipo,            # ou começar como passageiro
        })

        disp.tipo = tipo
        disp.save()
        return Response({"mensagem": "Tipo atualizado."})


class DeletarDispositivoPorUUIDView(APIView):
    def delete(self, request, uuid):
        disp = Dispositivo.objects.filter(uuid=uuid).first()
        if not disp:
            return Response({"erro": "Não encontrado."}, status=404)
        disp.delete()
        return Response({"mensagem": "Dispositivo excluído."})


class DispositivoRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer
    lookup_field = "uuid"


# ────────────────────────────────────────────────────────────────
# 6) ECO-TAXISTA ACEITA  (único ponto de débito)
# ────────────────────────────────────────────────────────────────
class AceitarCorridaView(APIView):
    """
    POST /api/corrida/<int:pk>/accept/
    Corpo: { "eco_taxi_id": <int> }
    """

    def post(self, request, pk):
        corrida = get_object_or_404(
            SolicitacaoCorrida,
            pk=pk,
            status="pending",
        )
        eco_id = request.data.get("eco_taxi_id")
        if str(corrida.eco_taxi_id) != str(eco_id):
            return Response({"erro": "Esta corrida não é sua."}, status=400)

        taxi = get_object_or_404(Dispositivo, pk=eco_id, tipo="ecotaxi")

        with transaction.atomic():
            # débito único
            if taxi.assentos_disponiveis < corrida.assentos_necessarios:
                return Response({"erro": "Assentos insuficientes."}, status=400)

            taxi.assentos_disponiveis = (
                F("assentos_disponiveis") - corrida.assentos_necessarios
            )
            taxi.status = "aguardando_resposta"
            taxi.save(update_fields=["assentos_disponiveis", "status"])
            taxi.refresh_from_db()  # ← ESSENCIAL para evitar CombinedExpression no serializer

            corrida.status = "accepted"
            corrida.save(update_fields=["status"])

        return Response({"mensagem": "Corrida aceita."})


# ────────────────────────────────────────────────────────────────
# 7) LISTAGEM DE CORRIDAS POR USUÁRIO
# ────────────────────────────────────────────────────────────────
class CorridasView(APIView):
    """
    GET /api/corridas/<uuid:uuid>/
    """

    EXCLUDED = ["rejected", "cancelled", "expired"]
    ECO_ATIVA = ["accepted", "started"]
    ECO_PEND = ["pending"]
    ECO_HIST = ["completed"]
    PASS_ATIVA = ["pending", "accepted", "started"]
    PASS_HIST = ["completed"]

    def get(self, request, uuid):
        disp = get_object_or_404(Dispositivo, uuid=uuid)

        # ——— ECO-TAXI ———
        if disp.tipo == "ecotaxi":
            ativa = (
                SolicitacaoCorrida.objects.filter(
                    eco_taxi=disp, status__in=self.ECO_ATIVA
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")
                .first()
            )
            pend = (
                SolicitacaoCorrida.objects.filter(
                    eco_taxi=disp, status__in=self.ECO_PEND
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("expiracao")
            )
            hist = (
                SolicitacaoCorrida.objects.filter(
                    eco_taxi=disp, status__in=self.ECO_HIST
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")[:10]
            )
            return Response(
                {
                    "tipo": "ecotaxi",
                    "corrida_ativa": (
                        SolicitacaoCorridaDetailSerializer(ativa).data
                        if ativa
                        else None
                    ),
                    "corridas_pendentes": CorridaEcoTaxiListSerializer(
                        pend, many=True
                    ).data,
                    "historico": CorridaEcoTaxiListSerializer(hist, many=True).data,
                    "info_dispositivo": {
                        "nome": disp.nome,
                        "status": disp.status,
                        "assentos_disponiveis": disp.assentos_disponiveis,
                        "cor_ecotaxi": disp.cor_ecotaxi,
                    },
                }
            )

        # ——— PASSAGEIRO ———
        ativa = (
            SolicitacaoCorrida.objects.filter(
                passageiro=disp, status__in=self.PASS_ATIVA
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")
            .first()
        )
        hist = (
            SolicitacaoCorrida.objects.filter(
                passageiro=disp, status__in=self.PASS_HIST
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")[:10]
        )
        return Response(
            {
                "tipo": "passageiro",
                "corrida_ativa": (
                    SolicitacaoCorridaDetailSerializer(ativa).data if ativa else None
                ),
                "historico": CorridaPassageiroListSerializer(hist, many=True).data,
                "info_dispositivo": {"nome": disp.nome},
            }
        )


# ────────────────────────────────────────────────────────────────
# 8) HISTÓRICO COMPLETO POR UUID
# ────────────────────────────────────────────────────────────────
class CorridasPorUUIDView(ListAPIView):
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_queryset(self):
        disp = get_object_or_404(Dispositivo, uuid=self.kwargs["uuid"])
        if disp.tipo == "passageiro":
            return SolicitacaoCorrida.objects.filter(passageiro=disp).order_by(
                "-criada_em"
            )
        return SolicitacaoCorrida.objects.filter(
            eco_taxi=disp, status__in=["accepted", "completed"]
        ).order_by("-criada_em")
