from rest_framework import generics, status
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import F
from .models import SolicitacaoCorrida, EcoTaxi, default_expiracao
from .serializers import (
    CorridaEcoTaxiListSerializer,
    EcoTaxiSerializer,
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer
)
from geopy.distance import geodesic
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404
from .models import Passageiro
from .serializers import PassageiroSerializer
from rest_framework.generics import ListAPIView



def repassar_para_proximo_ecotaxi(corrida):
    if corrida.eco_taxi:
        # Exclui o atual para não reenviar
        ecotaxis_disponiveis = EcoTaxi.objects.filter(
            status='aguardando',
            assentos_disponiveis__gte=corrida.assentos_necessarios
        ).exclude(id=corrida.eco_taxi.id)
    else:
        ecotaxis_disponiveis = EcoTaxi.objects.filter(
            status='aguardando',
            assentos_disponiveis__gte=corrida.assentos_necessarios
        )

    if not ecotaxis_disponiveis.exists():
        corrida.status = 'expired'
        corrida.save()
        return

    from geopy.distance import geodesic
    eco_mais_proximo = sorted(
        ecotaxis_disponiveis,
        key=lambda e: geodesic(
            (corrida.latitude_destino, corrida.longitude_destino),
            (e.latitude, e.longitude)
        ).meters
    )[0]

    corrida.eco_taxi = eco_mais_proximo
    corrida.status = 'pending'
    corrida.expiracao = timezone.now() + timezone.timedelta(minutes=5)
    corrida.save()


def buscar_ecotaxi_proximo(lat, lon, assentos_necessarios=1):
    ecotaxis = EcoTaxi.objects.filter(status='aguardando', assentos_disponiveis__gte=assentos_necessarios)
    if not ecotaxis.exists():
        return None

    ecotaxis_com_distancia = [
        (ecotaxi, geodesic((lat, lon), (ecotaxi.latitude, ecotaxi.longitude)).meters)
        for ecotaxi in ecotaxis
    ]
    ecotaxis_ordenados = sorted(ecotaxis_com_distancia, key=lambda x: x[1])
    return ecotaxis_ordenados[0][0] if ecotaxis_ordenados else None

class AtualizarStatusCorridaView(APIView):
    """
    View para aceitar, iniciar, recusar, cancelar ou finalizar uma corrida.
    Aceita PUT e PATCH.
    """
    permission_classes = [AllowAny]

    def put(self, request, pk):
        corrida = get_object_or_404(SolicitacaoCorrida, pk=pk)
        novo_status = request.data.get("status")

        status_validos = ['accepted', 'started', 'rejected', 'cancelled', 'completed']
        if novo_status not in status_validos:
            return Response({"erro": "Status inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # 🔁 Rejeitada: repassa para outro EcoTaxi
        if novo_status == 'rejected':
            corrida.eco_taxi = None
            corrida.status = 'pending'
            corrida.expiracao = default_expiracao()
            corrida.save()
            repassar_para_proximo_ecotaxi(corrida)
            return Response({"mensagem": "Corrida foi repassada ao próximo EcoTaxi."}, status=200)

        # ✅ Cancelada: marca como cancelada se ainda não estiver completada
        if novo_status == 'cancelled':
            if corrida.status != 'completed':
                corrida.status = 'cancelled'
                corrida.save()
            return Response({"mensagem": "Corrida cancelada com sucesso."}, status=200)

        # ✅ Atualiza status normalmente, mesmo que já esteja cancelada
        corrida.status = novo_status
        corrida.save()
        return Response({"mensagem": f"Status da corrida atualizado para '{novo_status}'."}, status=200)

    def patch(self, request, pk):
        return self.put(request, pk)

# Função utilitária: buscar EcoTaxis próximos


# View para criar solicitação de corrida
# View para criar solicitação de corrida
class CriarCorridaView(generics.CreateAPIView):
    serializer_class = SolicitacaoCorridaCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        corrida = serializer.save()

        eco_taxi = buscar_ecotaxi_proximo(
            corrida.latitude_destino,
            corrida.longitude_destino,
            corrida.assentos_necessarios
        )

        # ✔️ Apenas vincula o eco_taxi se existir
        if eco_taxi:
            corrida.eco_taxi = eco_taxi
            corrida.save()

        # ✔️ Não marca como 'expired' aqui!
        # A expiração será tratada depois no CorridaDetailView

        response_serializer = SolicitacaoCorridaDetailSerializer(corrida)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# View para visualizar uma corrida detalhada
class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()

        if corrida.status == 'pending' and timezone.now() > corrida.expiracao:
            repassar_para_proximo_ecotaxi(corrida)

        return corrida


class PassageiroCreateView(generics.CreateAPIView):
    queryset = Passageiro.objects.all()
    serializer_class = PassageiroSerializer





# views.py
class CorridasParaEcoTaxiView(generics.ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        eco_taxi_id = self.kwargs['pk']
        agora = timezone.now()

        return SolicitacaoCorrida.objects.filter(
            eco_taxi__id=eco_taxi_id,
            status='pending',
            expiracao__gte=agora  # ainda válidas
        ).order_by('expiracao')


class EcoTaxiCreateView(generics.CreateAPIView):
    queryset = EcoTaxi.objects.all()
    serializer_class = EcoTaxiSerializer
    permission_classes = [AllowAny]


class EcoTaxiUpdateView(generics.UpdateAPIView):
    queryset = EcoTaxi.objects.all()
    serializer_class = EcoTaxiSerializer
    permission_classes = [AllowAny]


class CorridasEcoTaxiHistoricoView(generics.ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        eco_taxi_id = self.kwargs['pk']
        return SolicitacaoCorrida.objects.filter(
            eco_taxi__id=eco_taxi_id,
            status__in=['accepted', 'completed']
        ).order_by('-criada_em')

class CorridaAtivaPassageiroView(APIView):
    def get(self, request, passageiro_id):
        corrida = SolicitacaoCorrida.objects.filter(
            passageiro_id=passageiro_id,
            status__in=['pending', 'accepted']
        ).order_by('-criada_em').first()

        if corrida:
            serializer = SolicitacaoCorridaDetailSerializer(corrida)
            return Response(serializer.data)
        return Response({'corrida': None})
    

class CorridasDoPassageiroView(ListAPIView):
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_queryset(self):
        passageiro_id = self.kwargs['passageiro_id']
        return SolicitacaoCorrida.objects.filter(passageiro_id=passageiro_id).order_by('-criada_em')


class AtualizarNomeView(APIView):
    def patch(self, request, pk):
        passageiro = get_object_or_404(Passageiro, pk=pk)
        novo_nome = request.data.get("nome")
        if not novo_nome:
            return Response({"erro": "Nome não fornecido."}, status=400)

        passageiro.nome = novo_nome
        passageiro.save()
        return Response(PassageiroSerializer(passageiro).data)
