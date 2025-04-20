# locations/models.py

from django.db import models
import uuid

class DeviceLocation(models.Model):
    """
    Já existente: armazena cada atualização de localização
    sem necessidade de cadastro de usuário.
    """
    DEVICE_TYPES = (
        ('user',   'Usuário'),
        ('driver', 'EcoTaxi'),
    )

    device_id   = models.CharField(max_length=100)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    latitude    = models.DecimalField(max_digits=9, decimal_places=6)
    longitude   = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device_type} {self.device_id} @ ({self.latitude}, {self.longitude})"


class RideRequest(models.Model):
    """
    Novo modelo: representa uma solicitação de corrida do passageiro.
    """
    RIDE_STATUS_CHOICES = (
        ('pending',   'Pendente'),
        ('accepted',  'Aceita'),
        ('rejected',  'Recusada'),
        ('completed', 'Concluída'),
    )

    # UUID único de cada corrida (fornecido pelo app ou gerado pelo servidor)
    ride_id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Identificador do passageiro (UUID gerado/armazenado no app)
    user_id         = models.UUIDField()
    # Identificador do motorista (device_id)
    driver_id       = models.CharField(max_length=100)
    # Coordenadas de pick‑up
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_longitude= models.DecimalField(max_digits=9, decimal_places=6)
    # Status da corrida
    status          = models.CharField(
                        max_length=10,
                        choices=RIDE_STATUS_CHOICES,
                        default='pending'
                     )
    # Quando a solicitação foi criada
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ride {self.ride_id} ({self.status})"


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
