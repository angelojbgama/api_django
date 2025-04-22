import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta

def default_expiracao():
        return timezone.now() + timedelta(minutes=5)

# Modelo base com UUID para identificar dispositivos (sem login)
class DispositivoBase(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nome = models.CharField(max_length=100)

    class Meta:
        abstract = True

    def __str__(self):
        return self.nome

# Passageiro herda o identificador do dispositivo
class Passageiro(DispositivoBase):
    criado_em = models.DateTimeField(auto_now_add=True)


# EcoTaxi com localização, status e assentos disponíveis
class EcoTaxi(DispositivoBase):
    STATUS_CHOICES = [
        ('aguardando', 'Aguardando Corrida'),
        ('transito', 'Em Trânsito'),
        ('fora', 'Fora de Serviço'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='fora')
    latitude = models.FloatField()
    longitude = models.FloatField()
    assentos_disponiveis = models.PositiveIntegerField(default=4)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.nome} ({self.get_status_display()})'


# Solicitação de corrida com todos os estados possíveis
class SolicitacaoCorrida(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pendente'),    # Solicitação feita
        ('accepted',  'Aceita'),      # EcoTaxi aceitou
        ('rejected',  'Recusada'),    # EcoTaxi recusou
        ('cancelled', 'Cancelada'),   # Passageiro cancelou
        ('completed', 'Concluída'),   # Corrida finalizada
        ('expired',   'Expirada'),    # EcoTaxi não respondeu a tempo
    ]

    passageiro = models.ForeignKey(Passageiro, on_delete=models.CASCADE, related_name='corridas')
    eco_taxi = models.ForeignKey(EcoTaxi, on_delete=models.SET_NULL, null=True, blank=True, related_name='corridas')

    latitude_destino = models.FloatField()
    longitude_destino = models.FloatField()
    endereco_destino = models.CharField(max_length=255, blank=True)

    assentos_necessarios = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    criada_em = models.DateTimeField(auto_now_add=True)
    
    expiracao = models.DateTimeField(default=default_expiracao)

    def __str__(self):
        return f"Corrida de {self.passageiro.nome} para {self.endereco_destino or 'Destino'} ({self.get_status_display()})"
