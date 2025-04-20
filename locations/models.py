from django.db import models

class DeviceLocation(models.Model):
    """
    Armazena cada atualização de localização.

    Sem cadastro: usamos `device_id` gerado pelo app (UUID) para identificar
    cada aparelho, e `device_type` para diferenciar usuário de motorista.
    """
    DEVICE_TYPES = (
        ('user',   'Usuário'),
        ('driver', 'EcoTaxi'),
    )

    device_id   = models.CharField(max_length=100)           # UUID único do app
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    latitude    = models.DecimalField(max_digits=9, decimal_places=6)
    longitude   = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp   = models.DateTimeField(auto_now_add=True)    # registra quando veio a atualização

    def __str__(self):
        return f"{self.device_type} {self.device_id} @ ({self.latitude}, {self.longitude})"
