from rest_framework import generics, status
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import F
from .models import SolicitacaoCorrida, EcoTaxi
from .serializers import (
    SolicitacaoCorridaCreateSerializer,
    SolicitacaoCorridaDetailSerializer
)
from geopy.distance import geodesic
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404
from .models import Passageiro
from .serializers import PassageiroSerializer


class AtualizarStatusCorridaView(APIView):
    """
    View para aceitar, recusar, cancelar ou finalizar uma corrida
    """
    permission_classes = [AllowAny]

    def put(self, request, pk):
        corrida = get_object_or_404(SolicitacaoCorrida, pk=pk)
        novo_status = request.data.get("status")

        if novo_status not in ['accepted', 'rejected', 'cancelled', 'completed']:
            return Response({"erro": "Status inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # Impede múltiplos updates inválidos
        if corrida.status in ['completed', 'cancelled', 'rejected']:
            return Response({"erro": "Corrida já finalizada ou inválida para atualização."}, status=400)

        corrida.status = novo_status
        corrida.save()
        return Response({"mensagem": f"Status da corrida atualizado para '{novo_status}'."}, status=200)


# Função utilitária: buscar EcoTaxis próximos
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

        if eco_taxi:
            corrida.eco_taxi = eco_taxi
            corrida.save()
        else:
            corrida.status = 'expired'
            corrida.save()

        response_serializer = SolicitacaoCorridaDetailSerializer(corrida)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# View para visualizar uma corrida detalhada
class CorridaDetailView(generics.RetrieveAPIView):
    queryset = SolicitacaoCorrida.objects.all()
    serializer_class = SolicitacaoCorridaDetailSerializer

    def get_object(self):
        corrida = super().get_object()

        # Se estiver pendente e já passou da data de expiração, marca como expirada
        if corrida.status == 'pending' and timezone.now() > corrida.expiracao:
            corrida.status = 'expired'
            corrida.save()

        return corrida

# views.py

class PassageiroCreateView(generics.CreateAPIView):
    queryset = Passageiro.objects.all()
    serializer_class = PassageiroSerializer
