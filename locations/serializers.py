from rest_framework import serializers
from .models import DeviceLocation

class DeviceLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceLocation
        # permitimos ler timestamp, mas ele é gerado pelo servidor
        fields = ('device_id', 'device_type', 'latitude', 'longitude', 'timestamp')
        read_only_fields = ('timestamp',)
