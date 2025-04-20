# locations/serializers.py

from rest_framework import serializers
from .models import DeviceLocation, RideRequest, RidePosition

class DeviceLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceLocation
        fields = ('device_id', 'device_type', 'latitude', 'longitude', 'timestamp')
        read_only_fields = ('timestamp',)


class RideRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideRequest
        # permitimos que o cliente envie ride_id ou que o servidor gere
        fields = (
          'ride_id',
          'user_id',
          'driver_id',
          'pickup_latitude',
          'pickup_longitude',
          'status',
          'created_at',
        )
        read_only_fields = ('created_at',)


class RidePositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RidePosition
        fields = ('latitude', 'longitude', 'timestamp')
        read_only_fields = ('timestamp',)
