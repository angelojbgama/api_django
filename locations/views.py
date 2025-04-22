from rest_framework import generics, status
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from .models import SolicitacaoCorrida, Dispositivo, default_expiracao
from .serializers import (
    CorridaEcoTaxiListSerializer,
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer,
    DispositivoSerializer
)
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404, ListAPIView, RetrieveAPIView
from geopy.distance import geodesic


def repassar_para_proximo_ecotaxi(corrida):
    ecotaxis_disponiveis = Dispositivo.objects.filter(
        tipo='ecotaxi',
        status='aguardando',
        assentos_disponiveis__gte=corrida.assentos_necessarios
    )
    if corrida.eco_taxi:
        ecotaxis_disponiveis = ecotaxis_disponiveis.exclude(id=corrida.eco_taxi.id)

    if not ecotaxis_disponiveis.exists():
        corrida.status = 'expired'
        corrida.save()
        return

    eco_mais_proximo = sorted(
        ecotaxis_disponiveis,
        key=lambda e: geodesic(
            (corrida.latitude_destino, corrida.longitude_destino),
            (e.latitude, e.longitude)
        ).meters
    )[0]

    corrida.eco_taxi = eco_mais_proximo
    corrida.status = 'pending'
    corrida.expiracao = default_expiracao()
    corrida.save()


def buscar_ecotaxi_proximo(lat, lon, assentos_necessarios=1):
    ecotaxis = Dispositivo.objects.filter(
        tipo='ecotaxi',
        status='aguardando',
        assentos_disponiveis__gte=assentos_necessarios
    )
    if not ecotaxis.exists():
        return None

    ecotaxis_com_distancia = [
        (eco, geodesic((lat, lon), (eco.latitude, eco.longitude)).meters)
        for eco in ecotaxis
    ]
    ecotaxis_ordenados = sorted(ecotaxis_com_distancia, key=lambda x: x[1])
    return ecotaxis_ordenados[0][0] if ecotaxis_ordenados else None


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

        if eco_taxi:
            corrida.eco_taxi = eco_taxi
            corrida.save()

        response_serializer = SolicitacaoCorridaDetailSerializer(corrida)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()
        if corrida.status == 'pending' and timezone.now() > corrida.expiracao:
            repassar_para_proximo_ecotaxi(corrida)
        return corrida


class AtualizarStatusCorridaView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, pk):
        corrida = get_object_or_404(SolicitacaoCorrida, pk=pk)
        novo_status = request.data.get("status")

        status_validos = ['accepted', 'started', 'rejected', 'cancelled', 'completed']
        if novo_status not in status_validos:
            return Response({"erro": "Status inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if novo_status == 'rejected':
            corrida.eco_taxi = None
            corrida.status = 'pending'
            corrida.expiracao = default_expiracao()
            corrida.save()
            repassar_para_proximo_ecotaxi(corrida)
            return Response({"mensagem": "Corrida foi repassada ao próximo EcoTaxi."})

        if novo_status == 'cancelled' and corrida.status != 'completed':
            corrida.status = 'cancelled'
            corrida.save()
            return Response({"mensagem": "Corrida cancelada."})

        corrida.status = novo_status
        corrida.save()
        return Response({"mensagem": f"Status da corrida atualizado para '{novo_status}'"})


class CorridasDoPassageiroView(ListAPIView):
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            passageiro_id=self.kwargs['passageiro_id']
        ).order_by('-criada_em')


class CorridasParaEcoTaxiView(ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            eco_taxi_id=self.kwargs['pk'],
            status='pending',
            expiracao__gte=timezone.now()
        ).order_by('expiracao')


class CorridasEcoTaxiHistoricoView(ListAPIView):
    serializer_class = CorridaEcoTaxiListSerializer

    def get_queryset(self):
        return SolicitacaoCorrida.objects.filter(
            eco_taxi_id=self.kwargs['pk'],
            status__in=['accepted', 'completed']
        ).order_by('-criada_em')


class CorridaAtivaPassageiroView(APIView):
    def get(self, request, passageiro_id):
        corrida = SolicitacaoCorrida.objects.filter(
            passageiro_id=passageiro_id,
            status__in=['pending', 'accepted']
        ).order_by('-criada_em').first()

        if corrida:
            return Response(SolicitacaoCorridaDetailSerializer(corrida).data)
        return Response({'corrida': None})


class DispositivoCreateView(generics.CreateAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer


class AtualizarNomeDispositivoView(APIView):
    def patch(self, request, pk):
        nome = request.data.get("nome")
        if not nome:
            return Response({"erro": "Nome não fornecido."}, status=400)

        dispositivo = get_object_or_404(Dispositivo, pk=pk)
        dispositivo.nome = nome
        dispositivo.save()
        return Response({"mensagem": "Nome atualizado com sucesso."})


class AtualizarTipoDispositivoView(APIView):
    def patch(self, request, pk):
        tipo = request.data.get("tipo")
        if tipo not in ['passageiro', 'ecotaxi']:
            return Response({"erro": "Tipo inválido"}, status=400)

        dispositivo = get_object_or_404(Dispositivo, pk=pk)
        dispositivo.tipo = tipo
        dispositivo.save()
        return Response({"mensagem": "Tipo de conta atualizado com sucesso."})


class DispositivoDetailView(RetrieveAPIView):
    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer


class TipoDispositivoView(APIView):
    def get(self, request, uuid):
        dispositivo = Dispositivo.objects.filter(uuid=uuid).first()
        if not dispositivo:
            return Response({'tipo': None, 'id': None})
        return Response({'tipo': dispositivo.tipo, 'id': dispositivo.id})


class DeletarDispositivoPorUUIDView(APIView):
    def delete(self, request, uuid):
        dispositivo = Dispositivo.objects.filter(uuid=uuid).first()
        if not dispositivo:
            return Response({"erro": "Dispositivo não encontrado."}, status=404)
        dispositivo.delete()
        return Response({"mensagem": "Dispositivo deletado com sucesso."})