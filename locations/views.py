import logging
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from django.db.models import F, Max
from rest_framework.exceptions import ValidationError

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


class RideRequestCreateView(generics.CreateAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        driver_id = serializer.validated_data['driver_id']
        # Impedir múltiplas corridas simultâneas
        conflict = RideRequest.objects.filter(
            driver_id=driver_id,
            status__in=['pending', 'accepted']
        ).exists()
        if conflict:
            raise ValidationError({'driver_id': 'Este EcoTaxi já está em outra corrida.'})
        serializer.save()


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


class RideRespondView(APIView):
    """
    POST /api/ride/respond/
    Body: {
      "ride_id": "<UUID>",
      "status":  "<pending|accepted|rejected|cancelled|completed>",
      "actor_id":"<driver_id ou user_id>"
    }

    - accepted/rejected: só driver_id pode
    - cancelled: só user_id (passageiro) pode
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ride_id  = request.data.get('ride_id')
        status_  = request.data.get('status')
        actor_id = request.data.get('actor_id')

        if not ride_id or not status_ or not actor_id:
            raise ValidationError({
                'detail': 'ride_id, status e actor_id são obrigatórios'
            })

        ride = get_object_or_404(RideRequest, ride_id=ride_id)

        # Se for motorista aceitando ou rejeitando
        if status_ in ('accepted', 'rejected'):
            if actor_id != ride.driver_id:
                raise ValidationError({
                    'actor_id': 'Somente o motorista designado pode aceitar ou rejeitar esta corrida.'
                })

        # Se passageiro cancelando
        if status_ == 'cancelled':
            # ride.user_id é um UUIDField
            if actor_id != str(ride.user_id):
                raise ValidationError({
                    'actor_id': 'Somente o passageiro dono pode cancelar esta corrida.'
                })

        # (Opcional) impedir aceitação se já houver outra aceita
        if status_ == 'accepted':
            conflict = RideRequest.objects.filter(
                driver_id=ride.driver_id,
                status='accepted'
            ).exclude(ride_id=ride.ride_id).exists()
            if conflict:
                raise ValidationError({
                    'status': 'Este EcoTaxi já possui outra corrida aceita.'
                })

        # Atualiza o status
        ride.status = status_
        ride.save()

        return Response({
            'ride_id': str(ride.ride_id),
            'status':  ride.status
        }, status=status.HTTP_200_OK)


class NearestDriverView(APIView):
    """
    GET /api/drivers/nearest/?lat=<>&lon=<>[&seats=<int>]
    Retorna o motorista mais próximo das coordenadas (lat,lon)
    que tenha seats_available >= seats (default 1).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            lat = float(request.query_params['lat'])
            lon = float(request.query_params['lon'])
        except (KeyError, ValueError):
            return Response({'error': 'lat e lon obrigatórios e numéricos'}, status=400)
        seats = int(request.query_params.get('seats', 1))

        # pega as últimas localizações de cada driver
        latest_ids = (
            DeviceLocation.objects
            .filter(device_type='driver', seats_available__gte=seats)
            .values('device_id')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        qs = DeviceLocation.objects.filter(id__in=latest_ids)

        # anota distância quadrática e ordena
        qs = qs.annotate(
            dx=(F('latitude') - lat) * (F('latitude') - lat),
            dy=(F('longitude') - lon) * (F('longitude') - lon),
        ).order_by('dx', 'dy')

        driver = qs.first()
        if not driver:
            return Response({'error': 'Nenhum motorista disponível'}, status=404)

        data = DeviceLocationSerializer(driver).data
        return Response(data, status=status.HTTP_200_OK)


class CurrentRideStatusView(APIView):
    """
    GET /api/ride/current/?user_id=<uuid>
    Retorna a corrida pendente ou aceita mais recente para esse usuário,
    com status e, se aceita, a última localização do motorista.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # busca corrida pendente ou aceita mais recente
        ride = (
            RideRequest.objects
            .filter(user_id=user_id, status__in=['pending', 'accepted'])
            .order_by('-created_at')
            .first()
        )
        if not ride:
            return Response(
                {'ride': None, 'message': 'Nenhuma corrida em andamento'},
                status=status.HTTP_200_OK
            )

        data = RideRequestSerializer(ride).data

        # se a corrida já foi aceita, anexa última posição do motorista
        if ride.status == 'accepted':
            driver_loc = (
                DeviceLocation.objects
                .filter(device_type='driver', device_id=ride.driver_id)
                .order_by('-timestamp')
                .first()
            )
            data['driver_location'] = (
                DeviceLocationSerializer(driver_loc).data
                if driver_loc else None
            )

        return Response(data, status=status.HTTP_200_OK)
