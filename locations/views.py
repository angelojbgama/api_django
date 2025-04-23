from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.generics import get_object_or_404, ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Dispositivo, SolicitacaoCorrida
from .serializers import (
    CorridaEcoTaxiListSerializer,
    DispositivoSerializer,
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer,
)
# 🔗 Lógica central de matching / repasse
from locations.utils.ecotaxi_matching import escolher_ecotaxi, repassar_para_proximo_ecotaxi


# ------------------------------------------------------------------
# 1) CRIAR CORRIDA – atribui EcoTaxi + reserva assentos de forma
#    transacional para evitar race-condition.
# ------------------------------------------------------------------
class CriarCorridaView(generics.CreateAPIView):
    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            corrida = serializer.save()  # Salva pendente, sem eco_taxi ainda.

            eco_taxi = escolher_ecotaxi(
                corrida.latitude_destino,
                corrida.longitude_destino,
                corrida.assentos_necessarios,
            )

            if eco_taxi:
                corrida.eco_taxi = eco_taxi
                corrida.save(update_fields=["eco_taxi"])

        return Response(
            SolicitacaoCorridaDetailSerializer(corrida).data,
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------
# 2) DETALHE DA CORRIDA – repassa se expirou.
# ------------------------------------------------------------------
class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()
        if corrida.status == "pending" and timezone.now() > corrida.expiracao:
            repassar_para_proximo_ecotaxi(corrida)
        return corrida


# ------------------------------------------------------------------
# 3) ATUALIZAR STATUS – devolve assentos em cancel/reject/complete,
#    atualiza status do motorista, repassa se precisar.
# ------------------------------------------------------------------
class AtualizarStatusCorridaView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, pk):
        corrida = get_object_or_404(SolicitacaoCorrida, pk=pk)
        novo_status = request.data.get("status")

        status_validos = {
            "accepted",
            "started",
            "rejected",
            "cancelled",
            "completed",
        }
        if novo_status not in status_validos:
            return Response(
                {"erro": "Status inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ──────────────────────────────────────────────────────────
        #  Função auxiliar: devolve assentos e libera motorista.
        # ──────────────────────────────────────────────────────────
        def _liberar_assentos():
            if corrida.eco_taxi:
                corrida.eco_taxi.assentos_disponiveis = (
                    F("assentos_disponiveis") + corrida.assentos_necessarios
                )
                corrida.eco_taxi.status = "aguardando"
                corrida.eco_taxi.save(
                    update_fields=["assentos_disponiveis", "status"]
                )

        # -------------------- REJECTED ---------------------------
        if novo_status == "rejected":
            with transaction.atomic():
                _liberar_assentos()
                corrida.eco_taxi = None
                corrida.status = "pending"
                corrida.expiracao = timezone.now() + timedelta(minutes=5)
                corrida.save(
                    update_fields=["eco_taxi", "status", "expiracao"]
                )
                repassar_para_proximo_ecotaxi(corrida)
            return Response(
                {"mensagem": "Corrida repassada para outro EcoTaxi."}
            )

        # -------------------- CANCELLED --------------------------
        if novo_status == "cancelled" and corrida.status != "completed":
            with transaction.atomic():
                _liberar_assentos()
                corrida.status = "cancelled"
                corrida.save(update_fields=["status"])
            return Response({"mensagem": "Corrida cancelada."})

        # -------------------- COMPLETED --------------------------
        if novo_status == "completed":
            with transaction.atomic():
                _liberar_assentos()
                corrida.status = "completed"
                corrida.save(update_fields=["status"])
            return Response({"mensagem": "Corrida concluída."})

        # -------------------- ACCEPTED / STARTED -----------------
        if novo_status == "accepted" and corrida.eco_taxi:
            corrida.eco_taxi.status = "aguardando_resposta"
            corrida.eco_taxi.save(update_fields=["status"])

        if novo_status == "started" and corrida.eco_taxi:
            corrida.eco_taxi.status = "transito"
            corrida.eco_taxi.save(update_fields=["status"])

        corrida.status = novo_status
        corrida.save(update_fields=["status"])
        return Response({"mensagem": f"Status → {novo_status}"})


# ------------------------------------------------------------------
# 4) LISTAGENS E OUTRAS VIEWS  (sem alterações na lógica)
# ------------------------------------------------------------------
class CorridasDoPassageiroView(ListAPIView):
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            passageiro_id=self.kwargs["passageiro_id"]
        ).order_by("-criada_em")


class CorridasParaEcoTaxiView(ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            eco_taxi_id=self.kwargs["pk"],
            status="pending",
            expiracao__gte=timezone.now(),
        ).order_by("expiracao")


class CorridasEcoTaxiHistoricoView(ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            eco_taxi_id=self.kwargs["pk"],
            status__in=["accepted", "completed"],
        ).order_by("-criada_em")


class CorridaAtivaPassageiroView(APIView):
    def get(self, request, passageiro_id):
        corrida = (
            SolicitacaoCorrida.objects.filter(
                passageiro_id=passageiro_id,
                status__in=["pending", "accepted"],
            )
            .order_by("-criada_em")
            .first()
        )
        if corrida:
            return Response(SolicitacaoCorridaDetailSerializer(corrida).data)
        return Response({"corrida": None})


# ------------------------------------------------------------------
# 5) CRUD DE DISPOSITIVO  (inalterado – apenas imports lá em cima)
# ------------------------------------------------------------------
class DispositivoCreateView(generics.CreateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer


class AtualizarNomeDispositivoView(APIView):
    def patch(self, request, uuid):
        nome = request.data.get("nome")
        if not nome:
            return Response({"erro": "Nome não fornecido."}, status=400)

        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        dispositivo.nome = nome
        dispositivo.save()
        return Response({"mensagem": "Nome atualizado."})


class AtualizarTipoDispositivoView(APIView):
    def patch(self, request, uuid):
        tipo = request.data.get("tipo")
        if tipo not in ["passageiro", "ecotaxi"]:
            return Response({"erro": "Tipo inválido"}, status=400)

        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        dispositivo.tipo = tipo
        dispositivo.save()
        return Response({"mensagem": "Tipo atualizado."})


class TipoDispositivoView(APIView):
    def get(self, request, uuid):
        dispositivo = Dispositivo.objects.filter(uuid=uuid).first()
        if not dispositivo:
            return Response({"tipo": None, "id": None})
        return Response({"tipo": dispositivo.tipo, "id": dispositivo.id})


class DeletarDispositivoPorUUIDView(APIView):
    def delete(self, request, uuid):
        dispositivo = Dispositivo.objects.filter(uuid=uuid).first()
        if not dispositivo:
            return Response({"erro": "Não encontrado."}, status=404)
        dispositivo.delete()
        return Response({"mensagem": "Dispositivo excluído."})


class DispositivoRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer
    lookup_field = "uuid"


# ------------------------------------------------------------------
# 6) HISTÓRICO COMPLETO POR UUID
# ------------------------------------------------------------------
class CorridasPorUUIDView(ListAPIView):
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_queryset(self):
        dispositivo = get_object_or_404(Dispositivo, uuid=self.kwargs["uuid"])

        if dispositivo.tipo == "passageiro":
            return SolicitacaoCorrida.objects.filter(
                passageiro=dispositivo
            ).order_by("-criada_em")

        # EcoTaxi
        return SolicitacaoCorrida.objects.filter(
            eco_taxi=dispositivo, status__in=["accepted", "completed"]
        ).order_by("-criada_em")
