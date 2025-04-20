from rest_framework import generics
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Max

from .models import DeviceLocation
from .serializers import DeviceLocationSerializer

@method_decorator(csrf_exempt, name='dispatch')
class LocationCreateView(generics.CreateAPIView):
    """
    POST /api/location/
    Recebe JSON com:
      - device_id: string (UUID gerado no app)
      - device_type: 'driver' ou 'user'
      - latitude, longitude: floats
    Salva no banco com timestamp automático.
    """
    queryset = DeviceLocation.objects.all()
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]


class DriverLocationListView(generics.ListAPIView):
    """
    GET /api/drivers/locations/
    Retorna a última localização de cada EcoTaxi (device_type='driver').
    """
    serializer_class = DeviceLocationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # 1) filtra só 'driver'
        # 2) agrupa por device_id e pega o id máximo (último registro)
        latest_ids = (
            DeviceLocation.objects
            .filter(device_type='driver')
            .values('device_id')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        # 3) busca apenas esses registros
        return DeviceLocation.objects.filter(id__in=latest_ids)
