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
# 1) POST /api/location/
#    Recebe latitude, longitude, device_id, device_type e seats_available
#    Salva DeviceLocation e, se o driver tiver rides aceitas, grava RidePosition
# --------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class LocationCreateView(generics.CreateAPIView):
    queryset = DeviceLocation.objects.all()
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        # 1) Salva nova localização
        instance = serializer.save()
        # 2) Para cada corrida já aceita deste motorista, salva posição
        accepted = RideRequest.objects.filter(
            driver_id=instance.device_id,
            status='accepted'
        )
        for ride in accepted:
            RidePosition.objects.create(
                ride=ride,
                latitude=instance.latitude,
                longitude=instance.longitude
            )


# --------------------------------------------------
# 2) GET /api/drivers/locations/
#    Retorna última localização de cada motorista (inclui seats_available)
# --------------------------------------------------
class DriverLocationListView(generics.ListAPIView):
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Agrupa por device_id e pega o id máximo de cada grupo
        latest_ids = (
            DeviceLocation.objects
            .filter(device_type='driver')
            .values('device_id')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        return DeviceLocation.objects.filter(id__in=latest_ids)


# --------------------------------------------------
# 3) POST /api/ride/request/
#    Cria uma nova solicitação de corrida (pending)
# --------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class RideRequestCreateView(generics.CreateAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    permission_classes = [AllowAny]


# --------------------------------------------------
# 4) GET /api/ride/status/?ride_id=<uuid>
#    Retorna status atual da corrida
# --------------------------------------------------
class RideStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ride_id = request.query_params.get('ride_id')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        return Response({
            'ride_id': str(ride.ride_id),
            'status':  ride.status
        }, status=status.HTTP_200_OK)


# --------------------------------------------------
# 5) GET /api/ride/route/?ride_id=<uuid>
#    Retorna histórico de posições para desenhar a rota
# --------------------------------------------------
class RideRouteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ride_id = request.query_params.get('ride_id')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        positions = ride.positions.order_by('timestamp')
        serializer = RidePositionSerializer(positions, many=True)
        return Response({
            'ride_id': str(ride.ride_id),
            'route':   serializer.data
        }, status=status.HTTP_200_OK)


# --------------------------------------------------
# 6) GET /api/ride/pending/?driver_id=<id>
#    Lista todas as solicitações pendentes para este motorista
# --------------------------------------------------
class RidePendingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        driver_id = request.query_params.get('driver_id')
        if not driver_id:
            return Response({"error": "driver_id é obrigatório"}, status=400)

        pendings = RideRequest.objects.filter(
            driver_id=driver_id,
            status='pending'
        ).order_by('created_at')

        serializer = RideRequestSerializer(pendings, many=True)
        return Response(serializer.data, status=200)


# --------------------------------------------------
# 7) POST /api/ride/respond/
#    Recebe ride_id e status ('accepted' ou 'rejected'), atualiza a RideRequest
# --------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class RideRespondView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ride_id = request.data.get('ride_id')
        status_ = request.data.get('status')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        ride.status = status_
        ride.save()
        return Response({
            'ride_id': str(ride.ride_id),
            'status':  ride.status
        }, status=status.HTTP_200_OK)


