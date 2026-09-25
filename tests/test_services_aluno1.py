"""Testes unitários automatizados para as funções da responsabilidade do Aluno 1 em services.py.

Executável diretamente com 'python tests/test_services_aluno1.py' ou via unittest/pytest.
"""

import os
from pathlib import Path
import sys
from unittest.mock import Mock
import unittest

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import GOOGLE_CLIENT_ID
from services import buscar_coordenadas, obter_sigla_uf, verificar_token_google


class TestObterSiglaUf(unittest.TestCase):
    """Testes de normalização e detecção de siglas de estados brasileiros."""

    def test_obter_sigla_uf_nome_com_acento(self) -> None:
        self.assertEqual(obter_sigla_uf("Piauí", "RJ"), "PI")
        self.assertEqual(obter_sigla_uf("São Paulo", "SP"), "SP")
        self.assertEqual(obter_sigla_uf("Ceará", ""), "CE")
        self.assertEqual(obter_sigla_uf("Goiás", "DF"), "GO")
        self.assertEqual(obter_sigla_uf("Pará", ""), "PA")

    def test_obter_sigla_uf_nome_sem_acento(self) -> None:
        self.assertEqual(obter_sigla_uf("Piaui", "RJ"), "PI")
        self.assertEqual(obter_sigla_uf("Sao Paulo", "SP"), "SP")
        self.assertEqual(obter_sigla_uf("Ceara", ""), "CE")
        self.assertEqual(obter_sigla_uf("Goias", "DF"), "GO")
        self.assertEqual(obter_sigla_uf("Rondonia", ""), "RO")

    def test_obter_sigla_uf_ja_em_sigla(self) -> None:
        self.assertEqual(obter_sigla_uf("PI", "RJ"), "PI")
        self.assertEqual(obter_sigla_uf("rj", "SP"), "RJ")
        self.assertEqual(obter_sigla_uf("MG", ""), "MG")

    def test_obter_sigla_uf_fallback_para_informada(self) -> None:
        self.assertEqual(obter_sigla_uf("", "PE"), "PE")
        self.assertEqual(obter_sigla_uf("EstadoDesconhecido", "CE"), "CE")
        self.assertEqual(obter_sigla_uf(None, "BA"), "BA")  # type: ignore[arg-type]

    def test_obter_sigla_uf_entradas_vazias_ou_invalidas(self) -> None:
        self.assertEqual(obter_sigla_uf("", ""), "")
        self.assertEqual(obter_sigla_uf("Desconhecido", "XX"), "XX")
        self.assertEqual(obter_sigla_uf(None, ""), "")  # type: ignore[arg-type]


class TestVerificarTokenGoogle(unittest.TestCase):
    """Testes de validação de token JWT no Google OAuth2 /tokeninfo."""

    def test_verificar_token_google_sucesso(self) -> None:
        payload_google = {
            "iss": "https://accounts.google.com",
            "sub": "10987654321",
            "aud": GOOGLE_CLIENT_ID,
            "email": "turista@exemplo.com",
            "name": "Maria Silva",
            "picture": "https://lh3.googleusercontent.com/avatar.jpg",
            "email_verified": "true",
        }

        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                str(request.url.copy_with(query=None)),
                "https://oauth2.googleapis.com/tokeninfo",
            )
            self.assertEqual(request.url.params["id_token"], "jwt_token_valido_123")
            self.assertTrue(all(v == 4.0 for v in request.extensions["timeout"].values()))
            return httpx.Response(200, json=payload_google)

        with httpx.Client(transport=httpx.MockTransport(responder)) as client:
            resultado = verificar_token_google(client, "jwt_token_valido_123")
            self.assertIsNotNone(resultado)
            assert resultado is not None
            self.assertEqual(resultado["sub"], "10987654321")
            self.assertEqual(resultado["id"], "10987654321")
            self.assertEqual(resultado["email"], "turista@exemplo.com")
            self.assertEqual(resultado["name"], "Maria Silva")
            self.assertEqual(resultado["nome"], "Maria Silva")
            self.assertEqual(resultado["picture"], "https://lh3.googleusercontent.com/avatar.jpg")
            self.assertEqual(resultado["foto"], "https://lh3.googleusercontent.com/avatar.jpg")

    def test_verificar_token_google_aud_invalido(self) -> None:
        payload_outro_app = {
            "sub": "10987654321",
            "aud": "outro_app_id_999999999.apps.googleusercontent.com",
            "email": "hacker@exemplo.com",
            "name": "Usuario Outro App",
        }

        with httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload_outro_app))
        ) as client:
            self.assertIsNone(verificar_token_google(client, "token_de_outro_app"))

    def test_verificar_token_google_token_expirado_ou_invalido(self) -> None:
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    400,
                    json={"error": "invalid_token", "error_description": "Invalid Value"},
                )
            )
        ) as client:
            self.assertIsNone(verificar_token_google(client, "token_falso"))

    def test_verificar_token_google_token_vazio_ou_tipo_incorreto(self) -> None:
        client = Mock(spec=httpx.Client)
        self.assertIsNone(verificar_token_google(client, ""))
        self.assertIsNone(verificar_token_google(client, "   "))
        self.assertIsNone(verificar_token_google(client, None))  # type: ignore[arg-type]
        client.get.assert_not_called()

    def test_verificar_token_google_erros_rede_e_timeout(self) -> None:
        for erro in (
            httpx.ConnectError("Falha de rede"),
            httpx.ReadTimeout("Timeout 4.0s"),
        ):
            client = Mock(spec=httpx.Client)
            client.get.side_effect = erro
            self.assertIsNone(verificar_token_google(client, "token_qualquer"))


class TestBuscarCoordenadas(unittest.TestCase):
    """Testes de geocodificação no Open-Meteo com filtro Brasil e correção de UF."""

    def test_buscar_coordenadas_sucesso_com_correcao_uf_teste5(self) -> None:
        """Valida o Teste 5 oficial: Origem Teresina / RJ -> corrigida para Teresina - PI via admin1."""
        resposta_api = {
            "results": [
                {
                    "id": 1,
                    "name": "Teresina",
                    "latitude": -5.08917,
                    "longitude": -42.80194,
                    "country": "Brazil",
                    "admin1": "Piauí",
                }
            ]
        }

        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                str(request.url.copy_with(query=None)),
                "https://geocoding-api.open-meteo.com/v1/search",
            )
            self.assertEqual(request.url.params["name"], "Teresina")
            self.assertEqual(request.url.params["country_codes"], "BR")
            self.assertTrue(all(v == 4.0 for v in request.extensions["timeout"].values()))
            return httpx.Response(200, json=resposta_api)

        with httpx.Client(transport=httpx.MockTransport(responder)) as client:
            lat, lon, nome = buscar_coordenadas(client, "Teresina", "RJ")
            self.assertEqual(lat, -5.08917)
            self.assertEqual(lon, -42.80194)
            self.assertEqual(nome, "Teresina - PI")

    def test_buscar_coordenadas_cidade_inexistente(self) -> None:
        resposta_vazia = {"generationtime_ms": 0.12}

        with httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=resposta_vazia))
        ) as client:
            lat, lon, nome = buscar_coordenadas(client, "CidadeFantasmaXYZ", "SP")
            self.assertEqual((lat, lon), (0.0, 0.0))
            self.assertEqual(nome, "CidadeFantasmaXYZ - SP")

    def test_buscar_coordenadas_erros_http_e_timeout(self) -> None:
        for status in (400, 500, 503):
            with httpx.Client(
                transport=httpx.MockTransport(lambda r, s=status: httpx.Response(s, json={}))
            ) as client:
                lat, lon, nome = buscar_coordenadas(client, "Recife", "PE")
                self.assertEqual((lat, lon), (0.0, 0.0))
                self.assertEqual(nome, "Recife - PE")

        client = Mock(spec=httpx.Client)
        client.get.side_effect = httpx.ReadTimeout("Timeout 4.0s")
        lat, lon, nome = buscar_coordenadas(client, "Salvador", "BA")
        self.assertEqual((lat, lon), (0.0, 0.0))
        self.assertEqual(nome, "Salvador - BA")

    def test_buscar_coordenadas_cidade_vazia(self) -> None:
        client = Mock(spec=httpx.Client)
        self.assertEqual(buscar_coordenadas(client, "", "PE"), (0.0, 0.0, "PE"))
        self.assertEqual(buscar_coordenadas(client, ""), (0.0, 0.0, ""))
        client.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
