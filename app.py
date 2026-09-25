"""Aplicação Flask Principal - Guia do Turista Inteligente (API Gateway em Python)."""

import os
import threading
from datetime import datetime, timezone
from typing import Any

from flask import Flask

from config import (
    DATA_DIR,
    PORT,
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "guia-turista-secret-key-2026-python")

# Controle de concorrência para leitura e escrita segura no arquivo JSON
DATA_DIR.mkdir(parents=True, exist_ok=True)
lock_arquivo_json = threading.Lock()

# Armazenamento volátil de roteiros em memória para sessões de visitantes
viagens_visitante_memoria: dict[str, list[dict[str, Any]]] = {}

# Controle de concorrência e idempotência contra cliques duplicados
requisicoes_ativas: set[str] = set()
requisicoes_recentes: dict[str, float] = {}
lock_requisicoes = threading.Lock()


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 4: Persistência JSON, Sanitização e Manipulação
# ==============================================================================


def sanitizar_entrada(texto: str, max_len: int = 80) -> str:
    """Higieniza entradas de texto removendo tags HTML, caracteres de controle e espaços extras."""
    # TODO (Aluno 4): Implementar a sanitização de texto via regex r'<[^>]*>'


def criar_estrutura_padrao_viagens() -> dict[str, Any]:
    """Retorna a estrutura inicial do payload JSON de viagens com metadados e provedores."""
    return {
        "versao_schema": "1.0",
        "descricao": "Base consolidada de roteiros turísticos e telemetria por usuário",
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "total_usuarios": 0,
        "total_roteiros": 0,
        "provedores": {
            "geocoding": "Open-Meteo Geocoding API",
            "previsao_tempo": "Open-Meteo Forecast API",
            "roteamento": "OSRM Routing Engine",
            "inteligencia_artificial": "Google Gemini (gemini-3.6-flash)",
        },
        "usuarios": {},
    }


def carregar_dados_viagens_json() -> dict[str, Any]:
    """Lê a base completa de viagens de static/data/viagens.json de forma thread-safe com lock_arquivo_json."""
    # TODO (Aluno 4): Implementar leitura segura do JSON com lock_arquivo_json


def salvar_dados_viagens_json(dados_completos: dict[str, Any]) -> None:
    """Persiste a base hierárquica em static/data/viagens.json com lock_arquivo_json e indentação de 2 espaços."""
    # TODO (Aluno 4): Implementar escrita segura no arquivo JSON com lock_arquivo_json


def obter_viagens_usuario(user_id: str) -> list[dict[str, Any]]:
    """Recupera a lista de roteiros: da memória para visitantes ou do arquivo JSON para logados."""
    # TODO (Aluno 4): Implementar recuperação de roteiros por usuário (memória vs JSON)


def adicionar_viagem_usuario(
    user_id: str,
    item: dict[str, Any],
    perfil_usuario: dict[str, Any] | None = None,
) -> None:
    """Adiciona um novo roteiro: na memória para visitante ou grava no JSON para usuário logado."""
    # TODO (Aluno 4): Implementar inserção de novo roteiro na estrutura de dados


def remover_viagem_usuario(user_id: str, viagem_id: str) -> None:
    """Remove um roteiro específico pelo ID."""
    # TODO (Aluno 4): Implementar remoção de roteiro pelo ID


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 3: Backend Gateway, Sessões, Rotas & Idempotência
# ==============================================================================


@app.route("/", methods=["GET"])
def index():
    """Renderiza a página principal (SSR com Jinja2)."""
    # TODO (Aluno 3): Recuperar usuário da sessão, buscar viagens e renderizar index.html


@app.route("/auth/google/callback", methods=["GET", "POST"])
def google_callback():
    """Recebe a credencial JWT do Google e valida 100% no Python."""
    # TODO (Aluno 3): Receber token JWT do formulário, validar via services.py e salvar session['usuario']


@app.route("/auth/demo", methods=["GET", "POST"])
def login_demo():
    """Modo Visitante para desenvolvimento e testes locais."""
    # TODO (Aluno 3): Criar sessão volátil em memória para 'Viajante Convidado'


@app.route("/auth/logout", methods=["GET", "POST"])
def logout():
    """Encerra a sessão e descarta a memória de visitante."""
    # TODO (Aluno 3): Limpar session e descartar viagens temporárias do visitante


@app.route("/viagens/criar", methods=["GET", "POST"])
def criar_viagem():
    """Processa o formulário de criação com deduplicação (locks) e orquestração de APIs."""
    # TODO (Aluno 3): Implementar lock_requisicoes, orquestração com services/planejamento e Padrão PRG


@app.route("/viagens/deletar/<string:viagem_id>", methods=["GET", "POST"])
def deletar_viagem(viagem_id: str):
    """Exclui um roteiro da lista do usuário."""
    # TODO (Aluno 3): Validar sessão e chamar remover_viagem_usuario


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 4: Endpoint REST e Error Handlers Globais
# ==============================================================================


@app.route("/viagens/json", methods=["GET"])
@app.route("/api/viagens/json", methods=["GET"])
@app.route("/api/viagens", methods=["GET"])
def ver_viagens_json():
    """Retorna a base consolidada de static/data/viagens.json com suporte dinâmico a visitantes."""
    # TODO (Aluno 4): Retornar jsonify() da árvore consolidada de viagens


@app.errorhandler(405)
def metodo_nao_permitido(error):
    """Fallback para acessos GET em rotas POST (ex: digitar /viagens/criar na barra de endereços)."""
    # TODO (Aluno 4): Interceptar erro 405 e redirecionar suavemente para url_for('index')


@app.errorhandler(404)
def pagina_nao_encontrada(error):
    """Fallback para rotas inexistentes redirecionando suavemente para a página principal."""
    # TODO (Aluno 4): Interceptar erro 404 e redirecionar suavemente para url_for('index')


if __name__ == "__main__":
    print(f"🌍 Servidor Flask Guia do Turista rodando em http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
