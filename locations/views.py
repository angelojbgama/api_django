import logging
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

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class LocationCreateView(generics.CreateAPIView):
    """
    POST /api/location/
    Recebe JSON com device_id, device_type, latitude, longitude e opcional seats_available.
    Salva DeviceLocation e, se houver rides accepted, também grava RidePosition.
    """
    queryset = DeviceLocation.objects.all()
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        # Loga o que chegou no corpo da requisição
        logger.info(f"[LocationCreate] dados recebidos: {request.data}")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save()
        # Para cada corrida já aceita, grava posição
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


class DriverLocationListView(generics.ListAPIView):
    """
    GET /api/drivers/locations/
    Retorna última localização (incluindo seats_available) de cada driver
    """
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


@method_decorator(csrf_exempt, name='dispatch')
class RideRequestCreateView(generics.CreateAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    permission_classes = [AllowAny]


class RideStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ride_id = request.query_params.get('ride_id')
        ride = get_object_or_404(RideRequest, ride_id=ride_id)
        return Response({
            'ride_id': str(ride.ride_id),
            'status':  ride.status
        }, status=status.HTTP_200_OK)


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
        return Response(serializer.data, status=status.HTTP_200_OK)


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
