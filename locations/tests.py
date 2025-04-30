# tests.py  –  cobertura total da app «locations»
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
import uuid
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from locations.models import Dispositivo, SolicitacaoCorrida, default_expiracao
from locations.serializers import (
    DispositivoUpdateSerializer,
    SolicitacaoCorridaCreateSerializer,
)
from locations.utils.ecotaxi_matching import (
    escolher_ecotaxi,
    repassar_para_proximo_ecotaxi,
)
from locations.views import (
    AceitarCorridaView,
    AtualizarStatusCorridaView,
    AtualizarTipoDispositivoView,
    CriarCorridaView,
    CorridasView,
)


# ------------------------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------------------------
def criar_passageiro(nome="Passageiro"):
    return Dispositivo.objects.create(uuid=uuid4(), nome=nome, tipo="passageiro")


def criar_ecotaxi(
    nome="Eco", lat=0.0, lon=0.0, assentos=4, status_eco="aguardando"
) -> Dispositivo:
    return Dispositivo.objects.create(
        uuid=uuid4(),
        nome=nome,
        tipo="ecotaxi",
        status=status_eco,
        latitude=lat,
        longitude=lon,
        assentos_disponiveis=assentos,
    )


factory = APIRequestFactory()
api_client = APIClient()


# ------------------------------------------------------------------------------------
# 1) Cobertura utils.ecotaxi_matching.py  (85 → 100 %)
# ------------------------------------------------------------------------------------
class MatchingCoverageTests(TestCase):
    def test_escolher_ecotaxi_nenhum_disponivel(self):
        """Quando não há nenhum EcoTaxi elegível deve retornar None"""
        self.assertIsNone(escolher_ecotaxi(0, 0, assentos_necessarios=1))

    def test_repassar_sem_poder_repassar(self):
        """Se corrida não estiver pending o utilitário não faz nada"""
        eco = criar_ecotaxi()
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=criar_passageiro(),
            eco_taxi=eco,
            status="accepted",  # não-pending
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
            expiracao=timezone.now() - timedelta(minutes=1),
        )
        repassar_para_proximo_ecotaxi(corrida)  # deve ser NO-OP
        corrida.refresh_from_db()
        self.assertEqual(corrida.eco_taxi, eco)  # nada mudou


# ------------------------------------------------------------------------------------
# 2) Cobertura serializers.py  (79 → 100 %)
# ------------------------------------------------------------------------------------
class SerializersCoverageTests(TestCase):
    def setUp(self):
        self.passag = criar_passageiro()
        self.eco = criar_ecotaxi()

    # –– validate: dispositivo errado ––
    def test_passageiro_tipo_invalido(self):
        data = {
            "passageiro": str(self.eco.uuid),
            "latitude_partida": 0,
            "longitude_partida": 0,
            "latitude_destino": 1,
            "longitude_destino": 1,
            "endereco_partida": "A",
            "endereco_destino": "B",
            "assentos_necessarios": 1,
        }
        s = SolicitacaoCorridaCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("não é um passageiro", str(s.errors))

    # –– validate: corrida em aberto ––
    def test_passageiro_com_corrida_em_aberto(self):
        SolicitacaoCorrida.objects.create(
            passageiro=self.passag,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
            status="pending",
        )
        s = SolicitacaoCorridaCreateSerializer(
            data={
                "passageiro": str(self.passag.uuid),
                "latitude_partida": 0,
                "longitude_partida": 0,
                "latitude_destino": 1,
                "longitude_destino": 1,
                "endereco_partida": "X",
                "endereco_destino": "Y",
                "assentos_necessarios": 1,
            }
        )
        with self.assertRaises(ValidationError):
            s.is_valid(raise_exception=True)

    # –– create: expiração futura ––
    def test_expiracao_automatica(self):
        s = SolicitacaoCorridaCreateSerializer(
            data={
                "passageiro": str(self.passag.uuid),
                "latitude_partida": 0,
                "longitude_partida": 0,
                "latitude_destino": 1,
                "longitude_destino": 1,
                "endereco_partida": "A",
                "endereco_destino": "B",
                "assentos_necessarios": 1,
            }
        )
        s.is_valid(raise_exception=True)
        corrida = s.save()
        self.assertGreater(corrida.expiracao, timezone.now())

    # –– DispositivoUpdateSerializer ––
    def test_assentos_fora_do_intervalo(self):
        ser = DispositivoUpdateSerializer(
            instance=self.eco, data={"assentos_disponiveis": 6}, partial=True
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("Valor deve estar entre 1 e 5", str(ser.errors))

    def test_passageiro_nao_pode_editar_assentos(self):
        ser = DispositivoUpdateSerializer(
            instance=self.passag,
            data={"cor_ecotaxi": "verde", "assentos_disponiveis": 4},
            partial=True,
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("Somente EcoTaxi", str(ser.errors))


# ------------------------------------------------------------------------------------
# 3) Cobertura views.py  (65 → 100 %)
# ------------------------------------------------------------------------------------
class ViewsCoverageTests(TestCase):
    def setUp(self):
        self.passag = criar_passageiro()
        self.eco = criar_ecotaxi()

    # ---- CriarCorridaView sem EcoTaxi disponível ----
    def test_criar_corrida_sem_disponibilidade(self):
        factory = APIRequestFactory()
        request = factory.post(
            "/api/corrida/nova/",
            {
                "passageiro": str(self.passag.uuid),
                "latitude_partida": 0,
                "longitude_partida": 0,
                "latitude_destino": 1,
                "longitude_destino": 1,
                "assentos_necessarios": 5,  # > assentos de qualquer EcoTaxi
            },
            format="json",
        )
        response = CriarCorridaView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nenhum EcoTaxi disponível", response.data["mensagem"])

    # ---- AceitarCorridaView erro: assentos insuficientes ----
    def test_aceitar_corrida_assentos_insuficientes(self):
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passag,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=5,
            expiracao=timezone.now() + timedelta(minutes=5),
            status="pending",
        )
        request = factory.post(
            f"/api/corrida/{corrida.pk}/accept/",
            {"eco_taxi_id": str(self.eco.pk)},
            format="json",
        )
        response = AceitarCorridaView.as_view()(request, pk=corrida.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Assentos insuficientes", response.data["erro"])

    # ---- AtualizarStatusCorridaView: rejected -> repasse ----
    @patch("locations.views.repassar_para_proximo_ecotaxi")
    def test_status_rejected_repassa(self, mock_repasse):
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passag,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
            status="pending",
            expiracao=timezone.now() + timedelta(minutes=5),
        )
        request = factory.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "rejected"},
            format="json",
        )
        resp = AtualizarStatusCorridaView.as_view()(request, uuid=str(corrida.uuid))
        self.assertEqual(resp.status_code, 200)
        mock_repasse.assert_called_once()

    # ---- AtualizarStatusCorridaView: completed devolve assentos ----
    def test_status_completed_devolve_assentos(self):
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passag,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=2,
            status="accepted",
            expiracao=timezone.now() + timedelta(minutes=5),
        )
        # simula assentos já debitados
        self.eco.assentos_disponiveis = 2
        self.eco.save(update_fields=["assentos_disponiveis"])

        request = factory.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "completed"},
            format="json",
        )
        resp = AtualizarStatusCorridaView.as_view()(request, uuid=str(corrida.uuid))
        self.assertEqual(resp.status_code, 200)
        self.eco.refresh_from_db()
        self.assertEqual(self.eco.assentos_disponiveis, 4)  # devolveu

    # ---- AtualizarTipoDispositivoView tipo inválido ----
    def test_atualizar_tipo_invalido(self):
        request = factory.patch(
            f"/api/dispositivo/{self.eco.uuid}/tipo/",
            {"tipo": "alien"},
            format="json",
        )
        resp = AtualizarTipoDispositivoView.as_view()(request, uuid=str(self.eco.uuid))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Tipo inválido", resp.data["erro"])

    # ---- CorridasView estrutura para passageiro e ecotaxi ----
    def test_corridas_view_estrutura(self):
        # passageiro sem histórico
        resp_pass = CorridasView.as_view()(
            factory.get(f"/api/corridas/{self.passag.uuid}/"),
            uuid=str(self.passag.uuid),
        )
        self.assertEqual(resp_pass.status_code, 200)
        self.assertEqual(resp_pass.data["tipo"], "passageiro")

        # ecotaxi com pendente
        SolicitacaoCorrida.objects.create(
            passageiro=self.passag,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
            status="pending",
        )
        resp_eco = CorridasView.as_view()(
            factory.get(f"/api/corridas/{self.eco.uuid}/"),
            uuid=str(self.eco.uuid),
        )
        self.assertEqual(resp_eco.status_code, 200)
        self.assertEqual(resp_eco.data["tipo"], "ecotaxi")


# ------------------------------------------------------------------------------------
# 4) Cobertura models.py & funções auxiliares (já estavam 100 %)
# ------------------------------------------------------------------------------------
class ModelHelpersCoverage(TestCase):
    def test_default_expiracao_realmente_futuro(self):
        self.assertGreater(default_expiracao(), timezone.now())


class UrlSmokeTest(TestCase):
    def test_urls_resolvem(self):
        ok = self.client.get  # atalho
        # sem criar objetos – só verifica 404/405 ≠ 500
        paths = [
            "/api/corrida/nova/",
            "/api/dispositivo/",
            "/api/dispositivo/fake-uuid/deletar/",
        ]
        for p in paths:
            resp = ok(p)
            self.assertLess(resp.status_code, 500)


class ViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.passg = criar_passageiro()
        self.eco = criar_ecotaxi()

    # -------- criação de corrida ------------------------------------
    @patch("locations.utils.ecotaxi_matching.geodesic")
    def test_criar_corrida_endpoint(self, fake_geo):
        fake_geo.return_value.meters = 5  # garante eco mais próximo
        r = self.client.post(
            "/api/corrida/nova/",
            {
                "passageiro": str(self.passg.uuid),
                "latitude_partida": 0,
                "longitude_partida": 0,
                "latitude_destino": 1,
                "longitude_destino": 1,
                "assentos_necessarios": 1,
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SolicitacaoCorrida.objects.count(), 1)

    # -------- aceitar e cancelar ------------------------------------
    def _criar_corrida(self, status_="pending", assentos=1):
        return SolicitacaoCorrida.objects.create(
            passageiro=self.passg,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=assentos,
            status=status_,
            expiracao=timezone.now() + timedelta(minutes=5),
        )

    def test_aceitar_corrida_view(self):
        corrida = self._criar_corrida(assentos=2)
        # agora enviamos o eco_taxi_id para que o endpoint aceite a corrida
        payload = {"eco_taxi_id": self.eco.pk}
        r = self.client.post(
            f"/api/corrida/{corrida.pk}/accept/",
            {"eco_taxi_id": str(self.eco.pk)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        self.eco.refresh_from_db()
        self.assertEqual(self.eco.assentos_disponiveis, 2)

    def test_cancelar_corrida_view(self):
        corrida = self._criar_corrida(status_="accepted")
        self.eco.assentos_disponiveis = 3
        self.eco.save(update_fields=["assentos_disponiveis"])

        r = self.client.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.eco.refresh_from_db()
        self.assertEqual(self.eco.assentos_disponiveis, 4)

    # -------- listagens e delete ------------------------------------
    def test_corridas_por_uuid_view(self):
        self._criar_corrida()
        r = self.client.get(f"/api/corrida/uuid/{self.passg.uuid}/")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data), 0)

    def test_delete_dispositivo(self):
        r = self.client.delete(f"/api/dispositivo/{self.passg.uuid}/deletar/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Dispositivo.objects.filter(uuid=self.passg.uuid).exists())


class UtilsAndModelTests(TestCase):
    def setUp(self):
        self.passageiro = criar_passageiro()
        self.eco1 = criar_ecotaxi("Eco-1", 0, 0)
        self.eco2 = criar_ecotaxi("Eco-2", 0, 1)

    def test_escolher_ecotaxi_proximo(self):
        eco = escolher_ecotaxi(0, 0, 1)
        self.assertEqual(eco.uuid, self.eco1.uuid)
        eco.refresh_from_db()
        self.assertEqual(eco.status, "aguardando_resposta")
        self.assertEqual(eco.assentos_disponiveis, 3)

    def test_repassar_para_proximo_ecotaxi(self):
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passg,
            eco_taxi=self.eco1,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=0.5,
            longitude_destino=0.5,
            assentos_necessarios=1,
            expiracao=timezone.now() - timedelta(seconds=1),
        )
        repassar_para_proximo_ecotaxi(corrida)
        corrida.refresh_from_db()
        self.assertEqual(corrida.eco_taxi.uuid, self.eco2.uuid)

    def test_repassar_quando_nao_ha_novo(self):
        # Criando só dois, mas vamos “inativar” o eco2:
        self.eco2.status = "fora"
        self.eco2.save(update_fields=["status"])

        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            latitude_partida=0.0,
            longitude_partida=0.0,
            latitude_destino=1.0,
            longitude_destino=1.0,
            assentos_necessarios=1,
            eco_taxi=self.eco1,
            expiracao=timezone.now() - timedelta(minutes=1),
        )

        # Chama o repasse direto (como o detalhe faria):
        repassar_para_proximo_ecotaxi(corrida)
        corrida.refresh_from_db()

        # Como não há outro elegível, mantém o mesmo:
        self.assertEqual(corrida.eco_taxi.uuid, self.eco1.uuid)

    def test_default_expiracao(self):
        self.assertGreater(default_expiracao(), timezone.now())

    def test_model_strs(self):
        self.assertEqual(str(self.passg), f"{self.passg.nome} (passageiro)")
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passg,
            eco_taxi=self.eco1,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
        )
        self.assertIn("Corrida de", str(corrida))

    def setUp(self):
        # cria um passageiro para usar nos testes de repasse
        self.passageiro = criar_passageiro()
        import uuid

        self.eco1 = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            nome="Eco A",
            tipo="ecotaxi",
            status="aguardando",
            latitude=0,
            longitude=0,
            assentos_disponiveis=2,
        )
        self.eco2 = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            nome="Eco B",
            tipo="ecotaxi",
            status="aguardando",
            latitude=1,
            longitude=1,
            assentos_disponiveis=2,
        )

    def test_repassar_com_novo_disponivel(self):
        # eco2 continua com status “aguardando”
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=1,
            longitude_destino=1,
            assentos_necessarios=1,
            eco_taxi=self.eco1,
            expiracao=timezone.now() - timedelta(minutes=1),
        )
        repassar_para_proximo_ecotaxi(corrida)
        corrida.refresh_from_db()
        self.assertEqual(corrida.eco_taxi.uuid, self.eco2.uuid)

    def test_escolher_ecotaxi_excluindo_um(self):
        # Exclui o eco1, deve escolher eco2
        escolhido = escolher_ecotaxi(
            0,
            0,
            assentos_necessarios=1,
            excluir_uuid=str(self.eco1.uuid),
        )
        self.assertEqual(escolhido.uuid, self.eco2.uuid)

    def test_repassar_quando_nao_ha_novo(self):
        # cria corrida expirada apenas com eco1
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.p,
            eco_taxi=self.eco1,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=0,
            longitude_destino=0,
            assentos_necessarios=1,
            expiracao=timezone.now() - timedelta(minutes=1),
        )
        # chama repassar, não há outro ecotaxi que satisfaça (os dois estão no mesmo ponto, mas excluir_uuid filtraria eco1)
        repassar_para_proximo_ecotaxi(corrida)
        corrida.refresh_from_db()
        # continua no mesmo eco1 e expiracao não foi estendida
        self.assertEqual(corrida.eco_taxi.uuid, self.eco1.uuid)
        self.assertTrue(corrida.expiracao < timezone.now())


class ViewsExtraTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.p = Dispositivo.objects.create(
            uuid=uuid.uuid4(), nome="P", tipo="passageiro"
        )
        self.eco = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            nome="E",
            tipo="ecotaxi",
            status="aguardando",
            latitude=0,
            longitude=0,
            assentos_disponiveis=2,
        )

    def _criar_corrida(self, assentos=1, expire_offset=5):
        return SolicitacaoCorrida.objects.create(
            passageiro=self.p,
            eco_taxi=self.eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=0,
            longitude_destino=0,
            assentos_necessarios=assentos,
            expiracao=timezone.now() + timedelta(minutes=expire_offset),
        )

    def test_criar_corrida_sem_ecotaxi(self):
        # todos ecotaxis fora de serviço
        self.eco.status = "fora"
        self.eco.save()
        payload = {
            "passageiro": str(self.p.uuid),
            "latitude_partida": 0,
            "longitude_partida": 0,
            "latitude_destino": 0,
            "longitude_destino": 0,
            "assentos_necessarios": 1,
        }
        r = self.client.post("/api/corrida/nova/", payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("Nenhum EcoTaxi disponível", r.data["mensagem"])

    def test_corrida_detail_sem_expirar(self):
        c = self._criar_corrida()
        r = self.client.get(f"/api/corrida/{c.pk}/")
        self.assertEqual(r.status_code, 200)
        # eco_taxi vem como dict completo
        self.assertIsInstance(r.data["eco_taxi"], dict)
        self.assertEqual(r.data["eco_taxi"]["uuid"], str(self.eco.uuid))

    def test_atualizar_status_cancelled(self):
        c = self._criar_corrida(assentos=1)
        # simula que já debitou 1 assento quando aceitou
        self.eco.assentos_disponiveis = 1
        self.eco.save()
        c.status = "accepted"
        c.save()

        r = self.client.patch(
            f"/api/corrida/{c.uuid}/status/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        self.eco.refresh_from_db()
        # devolveu o assento
        self.assertEqual(self.eco.assentos_disponiveis, 2)

        c.refresh_from_db()
        self.assertEqual(c.status, "cancelled")
        self.assertIsNone(c.eco_taxi)

    def test_atualizar_status_completed(self):
        c = self._criar_corrida(assentos=1)
        self.eco.assentos_disponiveis = 1
        self.eco.save()
        c.status = "accepted"
        c.save()

        r = self.client.patch(
            f"/api/corrida/{c.uuid}/status/", {"status": "completed"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        self.eco.refresh_from_db()
        self.assertEqual(self.eco.assentos_disponiveis, 2)
        c.refresh_from_db()
        self.assertEqual(c.status, "completed")

    def test_atualizar_status_started(self):
        c = self._criar_corrida()
        r = self.client.patch(
            f"/api/corrida/{c.uuid}/status/", {"status": "started"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        c.refresh_from_db()
        self.assertEqual(c.status, "started")

    def test_aceitar_corrida_wrong_taxi(self):
        c = self._criar_corrida()
        other = Dispositivo.objects.create(
            uuid=uuid.uuid4(), nome="X", tipo="ecotaxi", assentos_disponiveis=5
        )
        r = self.client.post(
            f"/api/corrida/{c.pk}/accept/", {"eco_taxi_id": other.pk}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Esta corrida não é sua", r.data["erro"])

    def test_aceitar_corrida_insuficiente(self):
        c = self._criar_corrida(assentos=10)
        r = self.client.post(
            f"/api/corrida/{c.pk}/accept/", {"eco_taxi_id": self.eco.pk}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Assentos insuficientes", r.data["erro"])

    def test_deletar_dispositivo(self):
        d = Dispositivo.objects.create(uuid=uuid.uuid4(), nome="Y", tipo="ecotaxi")
        r = self.client.delete(f"/api/dispositivo/{d.uuid}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(Dispositivo.objects.filter(uuid=d.uuid).exists())
        # agora deve dar 404
        r2 = self.client.delete(f"/api/dispositivo/{d.uuid}/")
        self.assertEqual(r2.status_code, 404)

    def test_atualizar_tipo_dispositivo(self):
        d = Dispositivo.objects.create(uuid=uuid.uuid4(), nome="Z", tipo="passageiro")
        # tipo válido
        r = self.client.patch(
            f"/api/dispositivo/{d.uuid}/tipo/", {"tipo": "ecotaxi"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(Dispositivo.objects.get(uuid=d.uuid).tipo, "ecotaxi")
        # tipo inválido
        r2 = self.client.patch(
            f"/api/dispositivo/{d.uuid}/tipo/", {"tipo": "foo"}, format="json"
        )
        self.assertEqual(r2.status_code, 400)


class ViewsExtraTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.passageiro = Dispositivo.objects.create(
            uuid=uuid.uuid4(), nome="Pas", tipo="passageiro"
        )
        # nenhum ecotaxi disponível
        self.eco = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            nome="Eco",
            tipo="ecotaxi",
            status="aguardando",
            assentos_disponiveis=0,
            latitude=0,
            longitude=0,
        )

    def _criar_payload(self):
        return {
            "passageiro": str(self.passageiro.uuid),
            "latitude_partida": 0.0,
            "longitude_partida": 0.0,
            "latitude_destino": 1.0,
            "longitude_destino": 1.0,
            "assentos_necessarios": 1,
        }

    def test_criar_corrida_sem_ecotaxi(self):
        """POST /api/corrida/nova/ quando não há EcoTaxi disponível"""
        r = self.client.post("/api/corrida/nova/", self._criar_payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["mensagem"], "Nenhum EcoTaxi disponível no momento.")

    def test_corrida_detail_sem_expirar(self):
        eco = Dispositivo.objects.create(
            uuid=uuid4(),
            nome="Taxi Teste",
            tipo="ecotaxi",
            status="aguardando",
            latitude=0.0,
            longitude=0.0,
            assentos_disponiveis=1,
        )
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            eco_taxi=eco,
            assentos_necessarios=1,
            expiracao=timezone.now() + timedelta(minutes=5),
        )

        r = self.client.get(f"/api/corrida/{corrida.pk}/")
        self.assertEqual(r.status_code, 200)

        # r.data["eco_taxi"] é um dict
        self.assertIsInstance(r.data["eco_taxi"], dict)
        self.assertEqual(r.data["eco_taxi"]["uuid"], str(eco.uuid))

    def test_atualizar_status_accepted(self):
        # cria corrida pending ligada ao ecotaxi com 3 assentos
        eco = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            nome="Taxi Teste",
            tipo="ecotaxi",
            status="aguardando",
            assentos_disponiveis=3,
        )
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            eco_taxi=eco,
            latitude_partida=0.0,
            longitude_partida=0.0,
            latitude_destino=1.0,
            longitude_destino=1.0,
            assentos_necessarios=2,
            status="pending",
            expiracao=timezone.now() + timedelta(minutes=5),
        )

        r = self.client.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "accepted"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        eco.refresh_from_db()
        # NÃO debitou assentos aqui
        self.assertEqual(eco.assentos_disponiveis, 3)

        corrida.refresh_from_db()
        self.assertEqual(corrida.status, "accepted")

    def test_atualizar_status_started(self):
        """PATCH para started altera status sem devolver assentos"""
        eco = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            tipo="ecotaxi",
            status="aguardando",
            assentos_disponiveis=2,
            latitude=0,
            longitude=0,
        )
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            eco_taxi=eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=0,
            longitude_destino=0,
            assentos_necessarios=1,
            status="accepted",
            expiracao=timezone.now() + timedelta(minutes=5),
        )
        r = self.client.patch(
            f"/api/corrida/{corrida.uuid}/status/", {"status": "started"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        eco.refresh_from_db()
        self.assertEqual(eco.assentos_disponiveis, 2)
        corrida.refresh_from_db()
        self.assertEqual(corrida.status, "started")

    def test_atualizar_status_completed(self):
        """PATCH para completed devolve assentos se já foram debitados"""
        eco = Dispositivo.objects.create(
            uuid=uuid.uuid4(),
            tipo="ecotaxi",
            status="aguardando",
            assentos_disponiveis=2,
            latitude=0,
            longitude=0,
        )
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            eco_taxi=eco,
            latitude_partida=0,
            longitude_partida=0,
            latitude_destino=0,
            longitude_destino=0,
            assentos_necessarios=1,
            status="started",
            expiracao=timezone.now() + timedelta(minutes=5),
        )
        # simula debitar 1 assento no accept
        eco.assentos_disponiveis = 1
        eco.save()
        r = self.client.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        eco.refresh_from_db()
        self.assertEqual(eco.assentos_disponiveis, 2)
        corrida.refresh_from_db()
        self.assertEqual(corrida.status, "completed")

    def test_atualizar_status_rejected(self):
        eco1 = Dispositivo.objects.create(..., assentos_disponiveis=2)
        eco2 = Dispositivo.objects.create(..., assentos_disponiveis=2)
        corrida = SolicitacaoCorrida.objects.create(
            passageiro=self.passageiro,
            eco_taxi=eco1,
            assentos_necessarios=1,
            status="pending",
            expiracao=timezone.now() + timedelta(minutes=5),
        )

        r = self.client.patch(
            f"/api/corrida/{corrida.uuid}/status/",
            {"status": "rejected"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        eco1.refresh_from_db()
        # eco1 continua inalterado
        self.assertEqual(eco1.assentos_disponiveis, 2)

        corrida.refresh_from_db()
        # passou para eco2
        self.assertEqual(corrida.eco_taxi.uuid, eco2.uuid)
        self.assertEqual(corrida.status, "rejected")
