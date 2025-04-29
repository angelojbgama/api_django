from __future__ import annotations

from datetime import timedelta

from django.db import transaction,IntegrityError
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
class CriarCorridaView(CreateAPIView):
    """
    POST /api/corrida/nova/
    Cria uma nova solicitação de corrida, faz o matching de ecotaxi,
    decrementa assentos e retorna JSON ou captura IntegrityError em JSON.
    """
    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                # Validação dos dados de entrada
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                corrida = serializer.save()

                # Escolhe ecotaxi disponível
                ecotaxi = escolher_ecotaxi(
                    corrida.latitude_partida,
                    corrida.longitude_partida,
                    corrida.assentos_necessarios
                )
                if ecotaxi:
                    # Lock e decremento de assentos
                    ecotaxi = Dispositivo.objects.select_for_update().get(pk=ecotaxi.pk)
                    ecotaxi.assentos_disponiveis -= corrida.assentos_necessarios
                    ecotaxi.status = 'aguardando'
                    ecotaxi.save(update_fields=['assentos_disponiveis', 'status'])

                    # Atribui ecotaxi e define expiração
                    corrida.eco_taxi = ecotaxi
                    corrida.expiracao = timezone.now() + timedelta(minutes=5)
                    corrida.save(update_fields=['eco_taxi', 'expiracao'])

        except IntegrityError as e:
            # Retorna o erro de integridade em JSON para facilitar debug
            return Response(
                {"erro": "IntegrityError", "detalhes": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Serializa e retorna a corrida criada
        data = SolicitacaoCorridaDetailSerializer(corrida).data
        return Response(data, status=status.HTTP_201_CREATED)


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
    """
    PATCH /api/corrida/<uuid:uuid>/status/
    - rejected: devolve assentos, desvincula ecotaxi, repassa para próximo.
    - cancelled: devolve assentos e cancela definitivamente.
    - completed: devolve assentos e finaliza.
    - accepted/started: apenas atualiza status do ecotaxi e da corrida.
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

        # REJEITAR → devolver assentos, desvincular, voltar a pending, repassar
        if novo_status == 'rejected':
            with transaction.atomic():
                _devolver_assentos()
                corrida.eco_taxi = None
                corrida.status = 'pending'
                corrida.expiracao = timezone.now() + timedelta(minutes=5)
                corrida.save(update_fields=['eco_taxi', 'status', 'expiracao'])
                repassar_para_proximo_ecotaxi(corrida)
            return Response({'mensagem': 'Corrida recusada e repassada.'})

        # CANCELAR → devolver assentos, cancelar
        if novo_status == 'cancelled' and corrida.status != 'completed':
            with transaction.atomic():
                _devolver_assentos()
                corrida.status = 'cancelled'
                corrida.save(update_fields=['status'])
            return Response({'mensagem': 'Corrida cancelada.'})

        # COMPLETAR → devolver assentos, concluir
        if novo_status == 'completed':
            with transaction.atomic():
                _devolver_assentos()
                corrida.status = 'completed'
                corrida.save(update_fields=['status'])
            return Response({'mensagem': 'Corrida concluída.'})

        # ACCEPTED / STARTED → atualiza apenas status do ecotaxi e da corrida
        if novo_status in {'accepted', 'started'} and corrida.eco_taxi:
            corrida.eco_taxi.status = 'aguardando_resposta' if novo_status == 'accepted' else 'transito'
            corrida.eco_taxi.save(update_fields=['status'])

        corrida.status = novo_status
        corrida.save(update_fields=['status'])
        detalhe = SolicitacaoCorridaDetailSerializer(corrida).data
        return Response({'mensagem': f'Status → {novo_status}', 'corrida': detalhe})

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


class AtualizarCorEcoTaxiView(APIView):
    def patch(self, request, uuid):
        cor = request.data.get("cor_ecotaxi")
        if not cor:
            return Response({"erro": "Cor não fornecida."}, status=400)

        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response({"erro": "Apenas ecotaxis podem ter cor."}, status=400)

        dispositivo.cor_ecotaxi = cor
        dispositivo.save()
        return Response({"mensagem": "Cor do EcoTaxi atualizada."})

class AtualizarAssentosEcoTaxiView(APIView):
    """
    PATCH /api/dispositivo/<uuid>/atualizar_assentos_ecotaxi/
    { "assentos_disponiveis": <int> }
    """
    def patch(self, request, uuid):
        # 1) obtém e valida o valor
        assentos = request.data.get("assentos_disponiveis")
        if assentos is None:
            return Response(
                {"erro": "Insira 'assentos_disponiveis' no corpo da requisição."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            assentos = int(assentos)
        except (ValueError, TypeError):
            return Response(
                {"erro": "Valor de assentos inválido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) busca o dispositivo
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)
        if dispositivo.tipo != "ecotaxi":
            return Response(
                {"erro": "Apenas dispositivos do tipo 'ecotaxi' podem ter assentos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) salva e retorna sucesso
        dispositivo.assentos_disponiveis = assentos
        dispositivo.save(update_fields=["assentos_disponiveis"])
        return Response(
            {"mensagem": "Assentos atualizados com sucesso!"},
            status=status.HTTP_200_OK
        )


class CorridasDisponiveisParaEcoTaxiView(APIView):
    def get(self, request, uuid):
        try:
            dispositivo = Dispositivo.objects.get(uuid=uuid)
            if dispositivo.tipo != 'ecotaxi':
                return Response(
                    {"erro": "Dispositivo não é um EcoTaxi."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            corridas = SolicitacaoCorrida.objects.filter(
                status="pending",
                expiracao__gte=timezone.now(),
                eco_taxi__isnull=True  # Corridas que ainda não têm eco_taxi atribuído
            ).order_by('expiracao')

            return Response(
                CorridaEcoTaxiListSerializer(corridas, many=True).data
            )
        except Dispositivo.DoesNotExist:
            return Response(
                {"erro": "Dispositivo não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

class AceitarCorridaView(APIView):
    """
    POST /api/corrida/<int:pk>/accept/
    Corpo: { "eco_taxi_id": <int> }
    Só aceita se ainda for pending e assentos disponíveis.
    """
    def post(self, request, pk):
        corrida = get_object_or_404(
            SolicitacaoCorrida,
            pk=pk,
            status='pending',
            eco_taxi__isnull=True
        )
        ecotaxi_id = request.data.get("eco_taxi_id")
        ecotaxi = get_object_or_404(Dispositivo, pk=ecotaxi_id, tipo='ecotaxi')

        if ecotaxi.assentos_disponiveis < corrida.assentos_necessarios:
            return Response(
                {"erro": "Assentos insuficientes."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # decrementa assentos
            ecotaxi.assentos_disponiveis = F('assentos_disponiveis') - corrida.assentos_necessarios
            ecotaxi.status = 'aguardando_resposta'  # ou 'transito' se preferir
            ecotaxi.save(update_fields=['assentos_disponiveis', 'status'])

            corrida.eco_taxi = ecotaxi
            corrida.status = 'accepted'
            corrida.save(update_fields=['eco_taxi', 'status'])

        return Response({"mensagem": "Corrida aceita."})

class CorridaAtivaEcoTaxiView(APIView):
    def get(self, request, uuid):
        try:
            dispositivo = Dispositivo.objects.get(uuid=uuid)
            if dispositivo.tipo != 'ecotaxi':
                return Response(
                    {"erro": "Dispositivo não é um EcoTaxi."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            corrida = SolicitacaoCorrida.objects.filter(
                eco_taxi=dispositivo,
                status__in=["accepted", "started"]
            ).order_by('-criada_em').first()

            if corrida:
                return Response({
                    "corrida": SolicitacaoCorridaDetailSerializer(corrida).data
                })
            return Response({"corrida": None})
        except Dispositivo.DoesNotExist:
            return Response(
                {"erro": "Dispositivo não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

class CorridasView(APIView):
    """
    Retorna informações de corridas para um dispositivo (ecotaxi ou passageiro),
    excluindo sempre os status: rejected, cancelled, expired.

    - Para EcoTaxi:
      * corrida_ativa (accepted, started)
      * corridas_pendentes (pending e não expiradas)
      * historico (completed)
      * info_ecotaxi
    - Para Passageiro:
      * corrida_ativa (pending, accepted, in_transit)
      * historico (completed)
      * info_passageiro
    """

    # statuses que sempre excluímos
    EXCLUDED_STATUSES = ["rejected", "cancelled", "expired"]

    # quais são “ativas” para cada tipo
    ECO_STATUS_ATIVA = ["accepted", "started"]
    ECO_STATUS_PENDENTES = ["pending"]
    ECO_STATUS_HISTORICO = ["completed"]

    PASS_STATUS_ATIVA = ["pending", "accepted", "in_transit"]
    PASS_STATUS_HISTORICO = ["completed"]

    def get(self, request, uuid):
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid)

        # ECO TAXI
        if dispositivo.tipo == "ecotaxi":
            # corrida em andamento
            corrida_ativa = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_STATUS_ATIVA
                )
                .exclude(status__in=self.EXCLUDED_STATUSES)
                .order_by("-criada_em")
                .first()
            )

            # pendentes (ainda dentro do prazo)
            corridas_pendentes = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_STATUS_PENDENTES,
                    expiracao__gte=timezone.now()
                )
                .exclude(status__in=self.EXCLUDED_STATUSES)
                .order_by("expiracao")
            )

            # histórico (já finalizadas)
            historico = (
                SolicitacaoCorrida.objects
                .filter(
                    eco_taxi=dispositivo,
                    status__in=self.ECO_STATUS_HISTORICO
                )
                .exclude(status__in=self.EXCLUDED_STATUSES)
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

        # PASSAGEIRO
        elif dispositivo.tipo == "passageiro":
            # corrida em andamento (única)
            corrida_ativa = (
                SolicitacaoCorrida.objects
                .filter(
                    passageiro=dispositivo,
                    status__in=self.PASS_STATUS_ATIVA
                )
                .exclude(status__in=self.EXCLUDED_STATUSES)
                .order_by("-criada_em")
                .first()
            )

            # histórico de corridas finalizadas
            historico = (
                SolicitacaoCorrida.objects
                .filter(
                    passageiro=dispositivo,
                    status__in=self.PASS_STATUS_HISTORICO
                )
                .exclude(status__in=self.EXCLUDED_STATUSES)
                .order_by("-criada_em")[:10]
            )

            return Response({
                "tipo": "passageiro",
                "corrida_ativa": SolicitacaoCorridaDetailSerializer(corrida_ativa).data if corrida_ativa else None,
                "historico": CorridaPassageiroListSerializer(historico, many=True).data,
                "info_dispositivo": {
                    "nome": dispositivo.nome,
                    # adicione aqui outros campos de info_passageiro se quiser
                }
            })

        # TIPO INVÁLIDO
        else:
            return Response(
                {"erro": "Tipo de dispositivo inválido."},
                status=status.HTTP_400_BAD_REQUEST
            )


class PassageiroCorridaAtivaView(APIView):
    """
    GET /api/corrida/passageiro/<uuid:uuid>/ativa/
    Retorna:
      {
        "ativa": <bool>,
        "corrida": { ...todos os campos de SolicitacaoCorrida... } | null
      }
    """
    def get(self, request, uuid):
        # valida dispositivo do tipo passageiro
        dispositivo = get_object_or_404(Dispositivo, uuid=uuid, tipo='passageiro')

        # busca a última corrida em pending, accepted ou started
        corrida = (
            SolicitacaoCorrida.objects
                .filter(
                    passageiro=dispositivo,
                    status__in=['pending', 'accepted', 'started']
                )
                .order_by('-criada_em')
                .first()
        )

        if corrida:
            serializer = SolicitacaoCorridaDetailSerializer(corrida)
            return Response({
                'ativa': True,
                'corrida': serializer.data
            })
        else:
            return Response({
                'ativa': False,
                'corrida': None
            })
