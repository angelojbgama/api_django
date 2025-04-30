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
    DispositivoUpdateSerializer,
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
    Se não houver EcoTaxi disponível, retorna mensagem sugerindo tentar mais tarde.
    Caso contrário, cria a solicitação, reserva assentos e retorna os dados.
    """
    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        # 1) valida os dados (mas ainda não salva nada)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # 2) tenta achar um EcoTaxi compatível antes de criar a corrida
        ecotaxi = escolher_ecotaxi(
            validated['latitude_partida'],
            validated['longitude_partida'],
            validated['assentos_necessarios']
        )
        if ecotaxi is None:
            return Response(
                {"mensagem": "Nenhum EcoTaxi disponível no momento. Por favor, tente novamente mais tarde."},
                status=status.HTTP_200_OK
            )

        # 3) create + reserva de assentos em transação
        try:
            with transaction.atomic():
                # 3.1) salva a solicitação
                corrida = serializer.save()

                # 3.2) lock e decremento de assentos
                taxi = Dispositivo.objects.select_for_update().get(pk=ecotaxi.pk)
                if taxi.assentos_disponiveis < corrida.assentos_necessarios:
                    # checagem extra por via das dúvidas
                    raise IntegrityError("Assentos insuficientes no momento da reserva.")

                taxi.assentos_disponiveis -= corrida.assentos_necessarios
                taxi.status = 'aguardando'
                taxi.save(update_fields=['assentos_disponiveis', 'status'])

                # 3.3) vincula e define expiração
                corrida.eco_taxi = taxi
                corrida.expiracao = timezone.now() + timedelta(minutes=5)
                corrida.save(update_fields=['eco_taxi', 'expiracao'])

        except IntegrityError as e:
            return Response(
                {"erro": "IntegrityError", "detalhes": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4) retorna os dados da corrida criada
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
            """
            Devolve assentos usando UPDATE direto no banco
            (evita sobrescrever dados sujos da instância em memória).
            """
            if corrida.eco_taxi_id is None:
                return

            Dispositivo.objects.filter(pk=corrida.eco_taxi_id).update(
                assentos_disponiveis=F('assentos_disponiveis') + corrida.assentos_necessarios,
                status='aguardando'
            )

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
                _devolver_assentos()  # ← devolve os assentos!
                corrida.eco_taxi = None
                corrida.status = 'cancelled'
                corrida.save(update_fields=['eco_taxi', 'status'])
            return Response({'mensagem': 'Corrida cancelada e assentos devolvidos.'})

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


class CorridasParaEcoTaxiView(ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            eco_taxi_id=self.kwargs["pk"],
            status="pending",
            expiracao__gte=timezone.now(),
        ).order_by("expiracao")



# ------------------------------------------------------------------
# 5) CRUD DE DISPOSITIVO
# ------------------------------------------------------------------
class DispositivoCreateView(generics.CreateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer

class AtualizarDispositivoView(generics.RetrieveUpdateAPIView):
    """
    GET    /api/dispositivo/<uuid>/atualizar/   – retorna dados completos
    PATCH  /api/dispositivo/<uuid>/atualizar/   – atualiza nome / cor / assentos
    """
    queryset = Dispositivo.objects.all()
    lookup_field = "uuid"
    permission_classes = [AllowAny]

    # — para GET usamos o serializer completo, para PATCH o parcial —
    def get_serializer_class(self):
        return (DispositivoUpdateSerializer
                if self.request.method.lower() == "patch"
                else DispositivoSerializer)

    def patch(self, request, *args, **kwargs):
        dispositivo = self.get_object()
        # partial=True permite enviar só o que precisa
        serializer = self.get_serializer(
            dispositivo, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"mensagem": "Dispositivo atualizado com sucesso!",
             "dispositivo": DispositivoSerializer(dispositivo).data},
            status=status.HTTP_200_OK,
        )



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




class CorridasView(APIView):
    """
    GET /api/corridas/<uuid:uuid>/

    Retorna corridas para ecotaxi ou passageiro.

    – EcoTaxi:
        • corrida_ativa       (accepted, started)
        • corridas_pendentes  (pending)
        • historico           (completed)
    – Passageiro:
        • corrida_ativa       (pending, accepted, started)
        • historico           (completed)
    """
    EXCLUDED   = ["rejected", "cancelled", "expired"]

    ECO_ATIVA  = ["accepted", "started"]
    ECO_PEND   = ["pending"]               # ← apenas o value salvo no banco
    ECO_HIST   = ["completed"]

    PASS_ATIVA = ["pending", "accepted", "started"]
    PASS_HIST  = ["completed"]

    def get(self, request, uuid):
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)

        # ————————————————————————————— ECO-TAXI ————————————————————————————
        if dispositivo.tipo == "ecotaxi":
            corrida_ativa = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_ATIVA,
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")
                .first()
            )

            # ———  pendentes  ———
            corridas_pendentes_qs = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_PEND,
                    #  REMOVIDO para testar fuso/expiração
                    #  expiracao__gte=timezone.now(),
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("expiracao")
            )

            #  LOG de debug  ➜  veja no runserver
            print(
                "DEBUG pendentes =>",
                list(
                    corridas_pendentes_qs.values("id", "status", "expiracao")
                )
            )

            historico = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_HIST,
                )
                .exclude(status__in=self.EXCLUDED)
                .order_by("-criada_em")[:10]
            )

            return Response({
                "tipo":               "ecotaxi",
                "corrida_ativa":      SolicitacaoCorridaDetailSerializer(corrida_ativa).data if corrida_ativa else None,
                "corridas_pendentes": CorridaEcoTaxiListSerializer(corridas_pendentes_qs, many=True).data,
                "historico":          CorridaEcoTaxiListSerializer(historico, many=True).data,
                "info_dispositivo": {
                    "nome":                 dispositivo.nome,
                    "status":               dispositivo.status,
                    "assentos_disponiveis": dispositivo.assentos_disponiveis,
                    "cor_ecotaxi":          dispositivo.cor_ecotaxi,
                }
            })

        # ————————————————————————— PASSAGEIRO ————————————————————————————
        corrida_ativa = (
            SolicitacaoCorrida.objects
            .filter(
                passageiro=dispositivo,
                status__in=self.PASS_ATIVA,
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")
            .first()
        )

        historico = (
            SolicitacaoCorrida.objects
            .filter(
                passageiro=dispositivo,
                status__in=self.PASS_HIST,
            )
            .exclude(status__in=self.EXCLUDED)
            .order_by("-criada_em")[:10]
        )

        return Response({
            "tipo":          "passageiro",
            "corrida_ativa": SolicitacaoCorridaDetailSerializer(corrida_ativa).data if corrida_ativa else None,
            "historico":     CorridaPassageiroListSerializer(historico, many=True).data,
            "info_dispositivo": {
                "nome": dispositivo.nome,
            }
        })
