# views.py

from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
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
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer,
)
from locations.utils.ecotaxi_matching import escolher_ecotaxi, repassar_para_proximo_ecotaxi


# ------------------------------------------------------------------
# 1) CRIAR CORRIDA
# ------------------------------------------------------------------
class CriarCorridaView(CreateAPIView):
    """
    POST /api/corrida/nova/
    Cria uma nova solicitação de corrida, faz o matching de ecotaxi,
    decrementa assentos (se houver) e retorna JSON.
    """
    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                # 1) valida e salva a solicitação
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                corrida = serializer.save()

                # 2) tenta escolher um ecotaxi com capacidade
                ecotaxi = escolher_ecotaxi(
                    corrida.latitude_partida,
                    corrida.longitude_partida,
                    corrida.assentos_necessarios
                )
                if ecotaxi:
                    # 3) re-busca o objeto sob lock para evitar race-conditions
                    ecotaxi = Dispositivo.objects.select_for_update().get(pk=ecotaxi.pk)

                    # 4) decrementa apenas se houver assentos suficientes
                    if ecotaxi.assentos_disponiveis >= corrida.assentos_necessarios:
                        ecotaxi.assentos_disponiveis -= corrida.assentos_necessarios
                        ecotaxi.status = 'aguardando'
                        ecotaxi.save(update_fields=['assentos_disponiveis', 'status'])

                        # 5) vincula o ecotaxi e define expiração
                        corrida.eco_taxi = ecotaxi
                        corrida.expiracao = timezone.now() + timedelta(minutes=5)
                        corrida.save(update_fields=['eco_taxi', 'expiracao'])
                    # se não tiver, deixa pendente sem motorista
        except IntegrityError as e:
            return Response(
                {"erro": "IntegrityError", "detalhes": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = SolicitacaoCorridaDetailSerializer(corrida).data
        return Response(data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------
# 2) DETALHE DA CORRIDA
# ------------------------------------------------------------------
class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()
        # repassa se expirou
        if corrida.status == "pending" and timezone.now() > corrida.expiracao:
            repassar_para_proximo_ecotaxi(corrida)
        return corrida


# ------------------------------------------------------------------
# 3) ATUALIZAR STATUS
# ------------------------------------------------------------------
class AtualizarStatusCorridaView(APIView):
    """
    PATCH /api/corrida/<uuid:uuid>/status/
    - rejected: devolve assentos, desvincula ecotaxi, repassa.
    - cancelled: devolve assentos e cancela.
    - completed: devolve assentos e conclui.
    - accepted/started: atualiza status do ecotaxi e da corrida.
    """
    permission_classes = [AllowAny]

    def patch(self, request, uuid):
        corrida = get_object_or_404(SolicitacaoCorrida, uuid=uuid)
        novo_status = request.data.get('status')

        validos = {'accepted', 'started', 'rejected', 'cancelled', 'completed'}
        if novo_status not in validos:
            return Response({'erro': 'Status inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        def _devolver_assentos():
            ecotaxi = corrida.eco_taxi
            if ecotaxi:
                ecotaxi.assentos_disponiveis = F('assentos_disponiveis') + corrida.assentos_necessarios
                ecotaxi.status = 'aguardando'
                ecotaxi.save(update_fields=['assentos_disponiveis', 'status'])

        # REJEITAR
        if novo_status == 'rejected':
            with transaction.atomic():
                _devolver_assentos()
                corrida.eco_taxi = None
                corrida.status = 'pending'
                corrida.expiracao = timezone.now() + timedelta(minutes=5)
                corrida.save(update_fields=['eco_taxi', 'status', 'expiracao'])
                repassar_para_proximo_ecotaxi(corrida)
            return Response({'mensagem': 'Corrida recusada e repassada.'})

        # CANCELAR
        if novo_status == 'cancelled' and corrida.status != 'completed':
            with transaction.atomic():
                _devolver_assentos()
                corrida.status = 'cancelled'
                corrida.save(update_fields=['status'])
            return Response({'mensagem': 'Corrida cancelada.'})

        # COMPLETAR
        if novo_status == 'completed':
            with transaction.atomic():
                _devolver_assentos()
                corrida.status = 'completed'
                corrida.save(update_fields=['status'])
            return Response({'mensagem': 'Corrida concluída.'})

        # ACCEPTED / STARTED
        if novo_status in {'accepted', 'started'} and corrida.eco_taxi:
            corrida.eco_taxi.status = (
                'aguardando_resposta' if novo_status == 'accepted' else 'transito'
            )
            corrida.eco_taxi.save(update_fields=['status'])

        corrida.status = novo_status
        corrida.save(update_fields=['status'])
        detalhe = SolicitacaoCorridaDetailSerializer(corrida).data
        return Response({'mensagem': f'Status → {novo_status}', 'corrida': detalhe})


# ------------------------------------------------------------------
# 4) LISTAGENS E OUTRAS VIEWS
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
    """
    GET /api/corrida/passageiro/<id>/ativa/
    Retorna a corrida ativa (pendente, aceita ou em trânsito).
    """
    def get(self, request, passageiro_id):
        corrida = (
            SolicitacaoCorrida.objects.filter(
                passageiro_id=passageiro_id,
                status__in=["pending", "accepted", "started"],
            )
            .order_by("-criada_em")
            .first()
        )
        if corrida:
            return Response(SolicitacaoCorridaDetailSerializer(corrida).data)
        return Response({"corrida": None})


# ------------------------------------------------------------------
# 5) CRUD DE DISPOSITIVO
# ------------------------------------------------------------------
class DispositivoCreateView(generics.CreateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer


class AtualizarNomeDispositivoView(APIView):
    def patch(self, request, uuid):
        nome = request.data.get("nome")
        if not nome:
            return Response({"erro": "Nome não fornecido."}, status=status.HTTP_400_BAD_REQUEST)
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        dispositivo.nome = nome
        dispositivo.save()
        return Response({"mensagem": "Nome atualizado."})


class AtualizarTipoDispositivoView(APIView):
    def patch(self, request, uuid):
        tipo = request.data.get("tipo")
        if tipo not in ["passageiro", "ecotaxi"]:
            return Response({"erro": "Tipo inválido"}, status=status.HTTP_400_BAD_REQUEST)
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        dispositivo.tipo = tipo
        dispositivo.save()
        return Response({"mensagem": "Tipo atualizado."})


class DeletarDispositivoPorUUIDView(APIView):
    def delete(self, request, uuid):
        dispositivo = Dispositivo.objects.filter(uuid=uuid).first()
        if not dispositivo:
            return Response({"erro": "Não encontrado."}, status=status.HTTP_404_NOT_FOUND)
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
        return SolicitacaoCorrida.objects.filter(
            eco_taxi=dispositivo, status__in=["accepted", "completed"]
        ).order_by("-criada_em")


class AtualizarCorEcoTaxiView(APIView):
    def patch(self, request, uuid):
        cor = request.data.get("cor_ecotaxi")
        if not cor:
            return Response({"erro": "Cor não fornecida."}, status=status.HTTP_400_BAD_REQUEST)
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response({"erro": "Apenas ecotaxis podem ter cor."}, status=status.HTTP_400_BAD_REQUEST)
        dispositivo.cor_ecotaxi = cor
        dispositivo.save()
        return Response({"mensagem": "Cor do EcoTaxi atualizada."})


class AtualizarAssentosEcoTaxiView(APIView):
    """
    PATCH /api/dispositivo/<uuid>/atualizar_assentos_ecotaxi/
    { "assentos_disponiveis": <int> }
    """
    def patch(self, request, uuid):
        assentos = request.data.get("assentos_disponiveis")
        if assentos is None:
            return Response({"erro": "Insira 'assentos_disponiveis' no corpo da requisição."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            assentos = int(assentos)
        except (ValueError, TypeError):
            return Response({"erro": "Valor de assentos inválido."}, status=status.HTTP_400_BAD_REQUEST)
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response({"erro": "Apenas ecotaxis podem ter assentos."},
                            status=status.HTTP_400_BAD_REQUEST)
        dispositivo.assentos_disponiveis = assentos
        dispositivo.save(update_fields=["assentos_disponiveis"])
        return Response({"mensagem": "Assentos atualizados com sucesso!"}, status=status.HTTP_200_OK)


class CorridasDisponiveisParaEcoTaxiView(APIView):
    def get(self, request, uuid):
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response({"erro": "Dispositivo não é um EcoTaxi."}, status=status.HTTP_400_BAD_REQUEST)
        corridas = SolicitacaoCorrida.objects.filter(
            status="pending",
            expiracao__gte=timezone.now(),
            eco_taxi__isnull=True
        ).order_by("expiracao")
        return Response(CorridaEcoTaxiListSerializer(corridas, many=True).data)


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
            eco_taxi__isnull=True
        )
        ecotaxi_id = request.data.get("eco_taxi_id")
        ecotaxi = get_object_or_404(Dispositivo, pk=ecotaxi_id, tipo="ecotaxi")
        if ecotaxi.assentos_disponiveis < corrida.assentos_necessarios:
            return Response({"erro": "Assentos insuficientes."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            ecotaxi.assentos_disponiveis = F("assentos_disponiveis") - corrida.assentos_necessarios
            ecotaxi.status = "aguardando_resposta"
            ecotaxi.save(update_fields=["assentos_disponiveis", "status"])
            corrida.eco_taxi = ecotaxi
            corrida.status = "accepted"
            corrida.save(update_fields=["eco_taxi", "status"])
        return Response({"mensagem": "Corrida aceita."})


class CorridaAtivaEcoTaxiView(APIView):
    def get(self, request, uuid):
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response({"erro": "Dispositivo não é um EcoTaxi."}, status=status.HTTP_400_BAD_REQUEST)
        corrida = SolicitacaoCorrida.objects.filter(
            eco_taxi=dispositivo,
            status__in=["accepted", "started"]
        ).order_by("-criada_em").first()
        if corrida:
            return Response({"corrida": SolicitacaoCorridaDetailSerializer(corrida).data})
        return Response({"corrida": None})


class CorridasView(APIView):
    """
    GET /api/corridas/<uuid:uuid>/
    Retorna corridas para ecotaxi ou passageiro, excluindo sempre
    rejected, cancelled, expired.
    - EcoTaxi:
      * corrida_ativa (accepted, started)
      * corridas_pendentes (pending ainda não expiradas)
      * historico (completed)
    - Passageiro:
      * corrida_ativa (pending, accepted, started)
      * historico (completed)
    """
    EXCLUDED   = ["rejected", "cancelled", "expired"]
    ECO_ATIVA  = ["accepted", "started"]
    ECO_PEND   = ["pending"]
    ECO_HIST   = ["completed"]
    PASS_ATIVA = ["pending", "accepted", "started"]  # inclui 'started'
    PASS_HIST  = ["completed"]

    def get(self, request, uuid):
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)

        # ——— EcoTaxi ———
        if dispositivo.tipo == "ecotaxi":
            # Corrida ativa (accepted ou started)
            corrida_ativa = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_ATIVA
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")
                .first()
            )

            # Corridas pendentes (pending não expiradas)
            corridas_pendentes = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_PEND,
                    expiracao__gte=timezone.now()
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("expiracao")
            )

            # Histórico (completed)
            historico = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_HIST
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")[:10]
            )

            return Response({
                "tipo": "ecotaxi",
                "corrida_ativa": SolicitacaoCorridaDetailSerializer(corrida_ativa).data if corrida_ativa else None,
                "corridas_pendentes": CorridaEcoTaxiListSerializer(corridas_pendentes, many=True).data,
                "historico": CorridaEcoTaxiListSerializer(historico, many=True).data,
                "info_dispositivo": {
                    "nome": dispositivo.nome,
                    "status": dispositivo.status,
                    "assentos_disponiveis": dispositivo.assentos_disponiveis,
                    "cor_ecotaxi": dispositivo.cor_ecotaxi,
                }
            })

        # ——— Passageiro ———
        corrida_ativa = (
            SolicitacaoCorrida.objects
            .filter(
                passageiro=dispositivo,
                status__in=self.PASS_ATIVA
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")
            .first()
        )

        historico = (
            SolicitacaoCorrida.objects
            .filter(
                passageiro=dispositivo,
                status__in=self.PASS_HIST
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")[:10]
        )

        return Response({
            "tipo": "passageiro",
            "corrida_ativa": SolicitacaoCorridaDetailSerializer(corrida_ativa).data if corrida_ativa else None,
            "historico": CorridaPassageiroListSerializer(historico, many=True).data,
            "info_dispositivo": {
                "nome": dispositivo.nome,
            }
        })