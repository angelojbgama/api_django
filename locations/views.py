# locations/views.py

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.db.models import Max

from .models import DeviceLocation, RideRequest, RidePosition
from .serializers import (
    DeviceLocationSerializer,
    RideRequestSerializer,
    RidePositionSerializer,
)

# --------------------------------------------------
# 1) Endpoint para receber atualizações de posição
#    - Continua salvando DeviceLocation
#    - Se o motorista tiver rides 'accepted', salva também RidePosition
# --------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class LocationCreateView(generics.CreateAPIView):
    queryset = DeviceLocation.objects.all()
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        # 1. Salva a nova localização do device
        instance = serializer.save()
        # 2. Para cada corrida já aceita deste motorista, armazena a posição
        accepted_rides = RideRequest.objects.filter(
            driver_id=instance.device_id,
            status='accepted'
        )
        for ride in accepted_rides:
            RidePosition.objects.create(
                ride=ride,
                latitude=instance.latitude,
                longitude=instance.longitude
            )

# --------------------------------------------------
# 2) Endpoint para listar a última localização de cada EcoTaxi
# --------------------------------------------------
class DriverLocationListView(generics.ListAPIView):
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        latest_ids = (
            DeviceLocation.objects
            .filter(device_type='driver')
            .values('device_id')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        return DeviceLocation.objects.filter(id__in=latest_ids)

# --------------------------------------------------
# 3) Endpoint para criar uma nova solicitação de corrida
#    Recebe: ride_id, user_id, driver_id, pickup_latitude, pickup_longitude
# --------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class RideRequestCreateView(generics.CreateAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    permission_classes = [AllowAny]

# --------------------------------------------------
# 4) Endpoint para consultar o status da corrida
#    GET /api/ride/status/?ride_id=<uuid>
#    Retorna: { ride_id, status }
# --------------------------------------------------
class RideStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ride_id = request.query_params.get('ride_id')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        return Response({
            'ride_id': str(ride.ride_id),
            'status': ride.status
        }, status=status.HTTP_200_OK)

# --------------------------------------------------
# 5) Endpoint para obter o histórico de posições da corrida
#    GET /api/ride/route/?ride_id=<uuid>
#    Retorna: { ride_id, route: [ {latitude, longitude, timestamp}, … ] }
# --------------------------------------------------
class RideRouteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ride_id = request.query_params.get('ride_id')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        # Serializa todas as posições em ordem cronológica
        positions = ride.positions.order_by('timestamp')
        serializer = RidePositionSerializer(positions, many=True)
        return Response({
            'ride_id': str(ride.ride_id),
            'route': serializer.data
        }, status=status.HTTP_200_OK)
