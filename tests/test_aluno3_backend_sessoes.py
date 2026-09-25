"""Testes automatizados para o escopo do Aluno 3 (Backend & Sessões).

Valida rotas principais, ciclo de vida HTTP (GET/POST), Padrão PRG,
sessões Flask (Google vs Visitante) e deduplicação com Locks.
"""

import unittest
from unittest.mock import patch

from app import (
    app,
    lock_requisicoes,
    requisicoes_ativas,
    requisicoes_recentes,
    viagens_visitante_memoria,
)


class TestAluno3BackendSessoes(unittest.TestCase):
    """Suíte de testes das rotas e regras do Aluno 3."""

    def setUp(self):
        """Configuração do cliente de testes Flask e limpeza de estados em memória."""
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key-aluno-3"
        self.client = app.test_client()

        # Limpeza thread-safe das estruturas de concorrência e memória
        with lock_requisicoes:
            requisicoes_ativas.clear()
            requisicoes_recentes.clear()
        viagens_visitante_memoria.clear()

    def tearDown(self):
        """Limpeza após cada teste."""
        with lock_requisicoes:
            requisicoes_ativas.clear()
            requisicoes_recentes.clear()
        viagens_visitante_memoria.clear()

    def test_01_index_anonimo(self):
        """Valida que GET / sem autenticação exibe a tela de login (SSR)."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        conteudo = response.data.decode("utf-8")
        self.assertIn("Autenticação Necessária", conteudo)
        self.assertIn("Entrar como Visitante", conteudo)

    def test_02_modo_visitante_prg(self):
        """Valida login no Modo Visitante com Padrão PRG (302 Redirect)."""
        response = self.client.get("/auth/demo")
        # Padrão PRG: deve responder com status de redirecionamento
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        # Verifica sessão criada
        with self.client.session_transaction() as sess:
            usuario = sess.get("usuario")
            self.assertIsNotNone(usuario)
            self.assertEqual(usuario["tipo"], "visitante")
            self.assertEqual(usuario["nome"], "Viajante Convidado")

        # Segue o redirecionamento (GET /)
        follow_response = self.client.get("/")
        self.assertEqual(follow_response.status_code, 200)
        html = follow_response.data.decode("utf-8")
        self.assertIn("Viajante Convidado", html)
        self.assertIn("Planejar Novo Roteiro", html)

    def test_03_logout_prg(self):
        """Valida que logout encerra a sessão e limpa memória volátil com PRG."""
        # Primeiro, faz login como visitante
        self.client.get("/auth/demo")

        with self.client.session_transaction() as sess:
            user_id = sess["usuario"]["id"]
            viagens_visitante_memoria[user_id] = [
                {"id": "v1", "origem": "A", "destino": "B"}
            ]

        # Executa logout
        logout_response = self.client.get("/auth/logout")
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers["Location"], "/")

        # Valida que sessão e memória foram descartadas
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("usuario"))
        self.assertNotIn(user_id, viagens_visitante_memoria)

    @patch("app.verificar_token_google")
    def test_04_google_callback_sucesso_prg(self, mock_verificar):
        """Valida recepção de token Google JWT com mock de autenticação e PRG."""
        mock_verificar.return_value = {
            "sub": "google-user-999",
            "name": "Turista Teste",
            "email": "turista@gmail.com",
            "picture": "https://exemplo.com/avatar.jpg",
        }

        response = self.client.post(
            "/auth/google/callback",
            data={"credential": "mock_jwt_token_valido"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        with self.client.session_transaction() as sess:
            usuario = sess.get("usuario")
            self.assertIsNotNone(usuario)
            self.assertEqual(usuario["id"], "google-user-999")
            self.assertEqual(usuario["nome"], "Turista Teste")
            self.assertEqual(usuario["tipo"], "google")

    def test_05_criar_viagem_get_bloqueado(self):
        """Valida que acesso direto via GET a /viagens/criar é bloqueado e redireciona (PRG)."""
        response = self.client.get("/viagens/criar")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_06_criar_viagem_sem_autenticacao(self):
        """Valida que POST /viagens/criar sem usuário autenticado redireciona para index."""
        response = self.client.post(
            "/viagens/criar",
            data={
                "origem_cidade": "Recife",
                "origem_uf": "PE",
                "destino_cidade": "Natal",
                "destino_uf": "RN",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    @patch("app.buscar_coordenadas")
    @patch("app.obter_clima")
    @patch("app.obter_percurso")
    @patch("app.obter_guia_destino_com_diagnostico")
    def test_07_criar_viagem_sucesso_prg(
        self,
        mock_guia,
        mock_percurso,
        mock_clima,
        mock_coord,
    ):
        """Valida ciclo completo de criação de viagem com mocks de serviços e Padrão PRG."""
        # Configuração dos mocks dos Alunos 1 e 2
        mock_coord.side_effect = [
            (-8.0476, -34.8770, "Recife - PE"),
            (-12.9714, -38.5014, "Salvador - BA"),
        ]
        mock_clima.return_value = {
            "temperatura": "28 °C",
            "umidade": "75 %",
            "vento": "18 km/h",
        }
        mock_percurso.return_value = {
            "distancia": "800.5 km",
            "tempo": "11h 30min",
        }
        mock_guia.return_value = (
            "🏛️ Pelourinho e Mercado Modelo 🍽️ Moqueca Baiana",
            {"status": "ok", "modelo": "gemini-3.6-flash"},
        )

        # Autentica como visitante
        self.client.get("/auth/demo")

        with self.client.session_transaction() as sess:
            user_id = sess["usuario"]["id"]

        # Envia formulário via POST
        response = self.client.post(
            "/viagens/criar",
            data={
                "origem_cidade": "Recife",
                "origem_uf": "PE",
                "destino_cidade": "Salvador",
                "destino_uf": "BA",
            },
        )
        # Resposta deve ser obrigatoriamente 302 (Padrão PRG)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        # Valida que o roteiro foi salvo na memória do visitante
        viagens = viagens_visitante_memoria.get(user_id, [])
        self.assertEqual(len(viagens), 1)
        self.assertEqual(viagens[0]["origem"], "Recife - PE")
        self.assertEqual(viagens[0]["destino"], "Salvador - BA")
        self.assertEqual(viagens[0]["clima"]["temperatura"], "28 °C")
        self.assertEqual(viagens[0]["percurso"]["distancia"], "800.5 km")
        self.assertIn("Pelourinho", viagens[0]["dicas_destino"])

        # Segue o redirecionamento (GET /) e verifica renderização no HTML
        follow_response = self.client.get("/")
        self.assertEqual(follow_response.status_code, 200)
        html = follow_response.data.decode("utf-8")
        self.assertIn("Recife - PE", html)
        self.assertIn("Salvador - BA", html)
        self.assertIn("28 °C", html)

    @patch("app.buscar_coordenadas")
    @patch("app.obter_clima")
    @patch("app.obter_percurso")
    @patch("app.obter_guia_destino_com_diagnostico")
    def test_08_idempotencia_duplo_clique_cooldown(
        self,
        mock_guia,
        mock_percurso,
        mock_clima,
        mock_coord,
    ):
        """Valida que cliques duplicados em sequência rápida são interceptados pelo cooldown."""
        mock_coord.return_value = (-8.0, -34.0, "Cidade - UF")
        mock_clima.return_value = {
            "temperatura": "25 °C",
            "umidade": "60 %",
            "vento": "10 km/h",
        }
        mock_percurso.return_value = {"distancia": "100 km", "tempo": "1h 30m"}
        mock_guia.return_value = ("Dicas de viagem", {})

        self.client.get("/auth/demo")

        payload = {
            "origem_cidade": "Fortaleza",
            "origem_uf": "CE",
            "destino_cidade": "Natal",
            "destino_uf": "RN",
        }

        # Primeira requisição: processa normalmente
        resp1 = self.client.post("/viagens/criar", data=payload)
        self.assertEqual(resp1.status_code, 302)

        # Segunda requisição idêntica imediata: interceptada pelo lock/cooldown
        resp2 = self.client.post("/viagens/criar", data=payload)
        self.assertEqual(resp2.status_code, 302)

        # Valida que as APIs externas NÃO foram acionadas duas vezes para a mesma rota
        with self.client.session_transaction() as sess:
            user_id = sess["usuario"]["id"]
        viagens = viagens_visitante_memoria.get(user_id, [])
        # Deve conter apenas 1 viagem criada, e não 2
        self.assertEqual(len(viagens), 1)

    def test_09_deletar_viagem_prg(self):
        """Valida remoção de viagem com Padrão PRG (302 Redirect)."""
        self.client.get("/auth/demo")

        with self.client.session_transaction() as sess:
            user_id = sess["usuario"]["id"]

        viagens_visitante_memoria[user_id] = [
            {"id": "del-123", "origem": "A", "destino": "B"},
            {"id": "keep-456", "origem": "C", "destino": "D"},
        ]

        # Deleta a viagem 'del-123'
        resp = self.client.post("/viagens/deletar/del-123")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "/")

        # Valida remoção
        viagens = viagens_visitante_memoria.get(user_id, [])
        self.assertEqual(len(viagens), 1)
        self.assertEqual(viagens[0]["id"], "keep-456")


if __name__ == "__main__":
    unittest.main()
