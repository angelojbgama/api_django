# locations/models.py

from django.db import models
import uuid

class DeviceLocation(models.Model):
    DEVICE_TYPES = (
        ('user',   'Usuário'),
        ('driver', 'EcoTaxi'),
    )

    device_id        = models.CharField(max_length=100)
    device_type      = models.CharField(max_length=10, choices=DEVICE_TYPES)
    latitude         = models.DecimalField(max_digits=9, decimal_places=6)
    longitude        = models.DecimalField(max_digits=9, decimal_places=6)
    seats_available  = models.IntegerField(default=1)   # <<< novo campo
    timestamp        = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device_type} {self.device_id} @ ({self.latitude}, {self.longitude}) - Lugares: {self.seats_available}"


class RideRequest(models.Model):
    RIDE_STATUS_CHOICES = (
        ('pending',   'Pendente'),
        ('accepted',  'Aceita'),
        ('rejected',  'Recusada'),
        ('cancelled', 'Cancelada'),
        ('completed', 'Concluída'),
    )

    ride_id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id          = models.UUIDField()
    passenger_name   = models.CharField("Nome do passageiro", max_length=100, blank=True, null=True)
    driver_id        = models.CharField(max_length=100)
    driver_name      = models.CharField("Nome do motorista", max_length=100, blank=True, null=True)
    pickup_latitude  = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    status           = models.CharField(max_length=10, choices=RIDE_STATUS_CHOICES, default='pending')
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ride {self.ride_id} ({self.status})"
    
    @classmethod
    def driver_busy(cls, driver_id):
        return cls.objects.filter(driver_id=driver_id, status__in=['pending','accepted']).exists()


class RidePosition(models.Model):
    """
    Novo modelo: armazena histórico de posições
    do motorista durante uma corrida aceita.
    """
    ride      = models.ForeignKey(
                  RideRequest,
                  on_delete=models.CASCADE,
                  related_name='positions'
                )
    latitude  = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Posição em {self.timestamp} para corrida {self.ride.ride_id}"
