from rest_framework import serializers
from .models import DeviceLocation, RideRequest, RidePosition

class DeviceLocationSerializer(serializers.ModelSerializer):
    # Torna seats_available opcional, default 0
    seats_available = serializers.IntegerField(required=False, default=0)

    class Meta:
        model = DeviceLocation
        fields = (  
            'device_id',
            'device_type',
            'latitude',
            'longitude',
            'seats_available',
            'timestamp',
        )
        read_only_fields = ('timestamp',)


class RideRequestSerializer(serializers.ModelSerializer):
    passenger_name = serializers.CharField(required=False, allow_blank=True)
    driver_name    = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = RideRequest
        fields = (
            'ride_id',
            'user_id',
            'passenger_name',
            'driver_id',
            'driver_name',
            'pickup_latitude',
            'pickup_longitude',
            'status',
            'created_at',
        )
        read_only_fields = ('created_at','status')


class RidePositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RidePosition
        fields = ('latitude', 'longitude', 'timestamp')
        read_only_fields = ('timestamp',)
