# 🚕 EcoTaxi API (Django + DRF)

API desenvolvida em Django REST Framework para conectar passageiros a motoristas EcoTaxi, com chamadas baseadas em localização geográfica, sistema de UUID para identificação sem login, e gerenciamento de estado das corridas.

---

## 🧩 Funcionalidades

- Registro automático de passageiros e motoristas (via UUID do dispositivo).
- EcoTaxis possuem estados: aguardando, em trânsito ou fora de serviço.
- Solicitação de corrida baseada na geolocalização e número de assentos disponíveis.
- Distribuição automática da corrida para o EcoTaxi mais próximo.
- Corridas possuem status automáticos: `pending`, `accepted`, `rejected`, `cancelled`, `completed`, `expired`.
- Expiração automática de solicitação após 1 minuto sem resposta.
- Sem autenticação: identificação é feita por UUID único por dispositivo.
- Endereço pode ser informado manualmente.

---

## 🗂️ Modelos principais

### `Passageiro`
- `uuid`: identificador do dispositivo (gerado automaticamente).
- `nome`: nome do passageiro.

### `EcoTaxi`
- `uuid`: identificador do dispositivo.
- `nome`: nome do motorista.
- `latitude`, `longitude`: localização atual.
- `status`: `aguardando`, `transito`, `fora`.
- `assentos_disponiveis`: total de assentos no veículo.

### `SolicitacaoCorrida`
- `passageiro`: referência ao passageiro.
- `eco_taxi`: EcoTaxi que aceitou a corrida (pode estar vazio).
- `latitude_destino`, `longitude_destino`, `endereco_destino`
- `assentos_necessarios`
- `status`: `pending`, `accepted`, `rejected`, `cancelled`, `completed`, `expired`.
- `expiracao`: 1 minuto após criação.

---

## 🚀 Endpoints REST

| Método | Endpoint                      | Descrição                          |
|--------|-------------------------------|------------------------------------|
| POST   | `/corrida/nova/`              | Cria nova corrida e busca EcoTaxi |
| GET    | `/corrida/<id>/`              | Retorna detalhes da corrida       |
| PUT    | `/corrida/<id>/status/`       | Atualiza status da corrida        |

---

## 📦 Exemplo de criação de corrida

### Requisição
```http
POST /corrida/nova/
Content-Type: application/json

{
  "passageiro": 1,
  "latitude_destino": -22.767,
  "longitude_destino": -43.108,
  "endereco_destino": "Rua das Flores, 123",
  "assentos_necessarios": 2
}
