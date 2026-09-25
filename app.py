"""Aplicação Flask Principal - Guia do Turista Inteligente (API Gateway em Python)."""

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import (
    DATA_DIR,
    ESTADOS_BRASIL,
    GOOGLE_CLIENT_ID,
    PORT,
    VIAGENS_FILE,
)
from planejamento import obter_guia_destino_com_diagnostico
from services import (
    buscar_coordenadas,
    obter_clima,
    obter_percurso,
    verificar_token_google,
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
    """
    Higieniza entradas de texto removendo:
    - Tags HTML
    - Caracteres de controle
    - Espaços extras
    - Conteúdo acima do tamanho máximo permitido
    """

    # Remove tags HTML, como <script>, <b>, <div>, etc.
    # A expressão <[^>]*> identifica qualquer conteúdo entre < e >.
    texto = re.sub(r"<[^>]*>", "", texto)

    # Remove caracteres de controle que podem causar problemas
    # ou deixar caracteres invisíveis na entrada.
    texto = re.sub(r"[\x00-\x1F\x7F]", "", texto)

    # Substitui vários espaços, tabulações ou quebras de linha
    # por apenas um espaço e remove espaços das extremidades.
    texto = re.sub(r"\s+", " ", texto).strip()

    # Limita o texto ao tamanho máximo definido.
    # Por padrão, nenhuma entrada terá mais de 80 caracteres.
    return texto[:max_len]

    # Aluno 4


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

    # Aluno 4


def carregar_dados_viagens_json() -> dict[str, Any]:
    """Lê a base completa de viagens de static/data/viagens.json de forma thread-safe com lock_arquivo_json."""
    with lock_arquivo_json:
        if not VIAGENS_FILE.exists():
            dados = criar_estrutura_padrao_viagens()
            with open(VIAGENS_FILE, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, indent=2, ensure_ascii=False)
            return dados

        with open(VIAGENS_FILE, "r", encoding="utf-8") as arquivo:
            try:
                dados = json.load(arquivo)
            except (json.JSONDecodeError, OSError):
                dados = criar_estrutura_padrao_viagens()
    return dados

    # Aluno 4


def salvar_dados_viagens_json(dados_completos: dict[str, Any]) -> None:
    """Persiste a base hierárquica em static/data/viagens.json com lock_arquivo_json e indentação de 2 espaços."""
    with lock_arquivo_json, open(VIAGENS_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(
            dados_completos,
            arquivo,
            indent=2,
            ensure_ascii=False,
        )

    # Aluno 4


def obter_viagens_usuario(user_id: str) -> list[dict[str, Any]]:
    """Recupera a lista de roteiros: da memória para visitantes ou do arquivo JSON para logados."""

    # Verifica primeiro se o usuário é um visitante.
    # Visitantes não têm seus dados persistidos no JSON.
    if user_id in viagens_visitante_memoria:
        # Retorna os roteiros armazenados temporariamente
        # na memória para esse visitante.
        return viagens_visitante_memoria[user_id]

    # Para usuários logados, carregamos os dados persistidos
    # no arquivo viagens.json.
    dados = carregar_dados_viagens_json()

    # Procura o usuário dentro da estrutura "usuarios".
    usuario = dados.get("usuarios", {}).get(user_id)

    # Se o usuário ainda não possuir cadastro ou roteiros,
    # retornamos uma lista vazia.
    if not usuario:
        return []

    # Retorna somente a lista de roteiros desse usuário.
    return usuario.get("roteiros", [])

    # Aluno 4


def adicionar_viagem_usuario(
    user_id: str,
    item: dict[str, Any],
    perfil_usuario: dict[str, Any] | None = None,
) -> None:
    """Adiciona um novo roteiro: na memória para visitante ou grava no JSON para usuário logado."""
    # Visitantes não possuem persistência no arquivo JSON.
    # Seus roteiros ficam armazenados somente em memória.
    if (
        user_id in viagens_visitante_memoria
        or (perfil_usuario and perfil_usuario.get("tipo") == "visitante")
        or user_id.startswith("visitante_")
    ):
        viagens_visitante_memoria.setdefault(user_id, []).insert(0, item)
        return

    # Para usuários logados, primeiro carregamos a estrutura
    # persistida no arquivo viagens.json.
    dados = carregar_dados_viagens_json()

    # Recupera a estrutura de usuários.
    usuarios = dados.setdefault("usuarios", {})

    # Verifica se o usuário já existe no arquivo JSON.
    if user_id not in usuarios:
        # Se ainda não existir, cria o cadastro do usuário.
        usuarios[user_id] = {
            "perfil": perfil_usuario or {},
            "roteiros": [],
        }

        # Atualiza a quantidade total de usuários cadastrados.
        dados["total_usuarios"] = len(usuarios)

    # Recupera a lista de roteiros do usuário.
    roteiros = usuarios[user_id].setdefault("roteiros", [])

    # Adiciona o novo roteiro à lista no início (mais recente primeiro).
    roteiros.insert(0, item)

    # Atualiza a quantidade total de roteiros armazenados.
    dados["total_roteiros"] = sum(
        len(usuario.get("roteiros", [])) for usuario in usuarios.values()
    )

    # Registra o momento da última alteração na base.
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()

    # Persiste as alterações no arquivo JSON.
    salvar_dados_viagens_json(dados)

    # Aluno 4


def remover_viagem_usuario(user_id: str, viagem_id: str) -> None:
    """Remove um roteiro específico pelo ID."""
    # Visitantes possuem os roteiros armazenados somente em memória.
    if user_id in viagens_visitante_memoria or user_id.startswith("visitante_"):
        viagens_visitante_memoria[user_id] = [
            viagem
            for viagem in viagens_visitante_memoria.get(user_id, [])
            if viagem.get("id") != viagem_id
        ]
        return

    # Para usuários logados, carregamos os dados persistidos.
    dados = carregar_dados_viagens_json()

    # Recupera a estrutura de usuários.
    usuarios = dados.get("usuarios", {})

    # Procura o usuário pelo ID.
    usuario = usuarios.get(user_id)

    # Se o usuário não existir, não há nada para remover.
    if not usuario:
        return

    # Recupera os roteiros cadastrados para o usuário.
    roteiros = usuario.get("roteiros", [])

    # Mantém somente os roteiros que possuem ID diferente
    # daquele que queremos remover.
    usuario["roteiros"] = [
        viagem for viagem in roteiros if viagem.get("id") != viagem_id
    ]

    # Recalcula a quantidade total de roteiros existentes
    # em todos os usuários.
    dados["total_roteiros"] = sum(
        len(usuario_item.get("roteiros", [])) for usuario_item in usuarios.values()
    )

    # Atualiza a data da última alteração da base.
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()

    # Salva a estrutura atualizada no arquivo JSON.
    salvar_dados_viagens_json(dados)


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 3: Backend Gateway, Sessões, Rotas & Idempotência
# ==============================================================================


@app.route("/", methods=["GET"])
def index():
    """Renderiza a página principal (SSR com Jinja2)."""
    usuario = session.get("usuario")
    viagens: list[dict[str, Any]] = []

    if usuario and isinstance(usuario, dict) and "id" in usuario:
        user_id = str(usuario["id"])
        roteiros = obter_viagens_usuario(user_id)
        if roteiros is not None:
            viagens = roteiros
        else:
            viagens = viagens_visitante_memoria.get(user_id, [])

    ufs = sorted(ESTADOS_BRASIL.keys())
    return render_template(
        "index.html",
        usuario=usuario,
        viagens=viagens,
        ufs=ufs,
        client_id=GOOGLE_CLIENT_ID,
    )


@app.route("/auth/google/callback", methods=["GET", "POST"])
def google_callback():
    """Recebe a credencial JWT do Google e valida 100% no Python."""
    if request.method == "POST":
        token = request.form.get("credential", "").strip()
        if token:
            try:
                # ----------------------------------------------------------------------
                # 💡 GUIA DE INTEGRAÇÃO COM ALUNO 1 (services.verificar_token_google):
                # - Eixo 3 (Resiliência & Connection Pooling):
                #   Injetamos o client com pool de conexões (Keep-Alive ativo).
                # - Eixo 4 (Autenticação, Tokens JWT & Google OAuth):
                #   Em services.py, o Aluno 1 deve consultar o endpoint oficial:
                #   'https://oauth2.googleapis.com/tokeninfo?id_token={token}'
                #   verificar status HTTP 200 e certificar que 'aud' == GOOGLE_CLIENT_ID.
                # - Contrato do Payload retornado:
                #   Deve retornar dict com dados do Google: 'sub' (ID único), 'name',
                #   'email', 'picture' (ou None se inválido/expirado).
                #   Tratamos com fallback para 'id', 'nome' e 'foto' para evitar quebra.
                # ----------------------------------------------------------------------
                pool_limits = httpx.Limits(
                    max_keepalive_connections=5, max_connections=10
                )
                with httpx.Client(limits=pool_limits, timeout=10.0) as client:
                    payload = verificar_token_google(client, token)

                if payload and isinstance(payload, dict):
                    user_id = str(payload.get("sub") or payload.get("id") or "").strip()
                    if user_id:
                        session["usuario"] = {
                            "id": user_id,
                            "nome": payload.get("name")
                            or payload.get("nome", "Usuário Google"),
                            "email": payload.get("email", ""),
                            "foto": payload.get("picture") or payload.get("foto", ""),
                            "tipo": "google",
                        }
            except Exception as err:  # noqa: BLE001 - barreira defensiva para falhas de rede/API
                app.logger.warning("Falha na validação de credencial Google: %s", err)

    return redirect(url_for("index"))


@app.route("/auth/demo", methods=["GET", "POST"])
def login_demo():
    """Modo Visitante para desenvolvimento e testes locais."""
    visitor_uuid = uuid.uuid4().hex[:8]
    visitor_id = f"visitante_{visitor_uuid}"

    session["usuario"] = {
        "id": visitor_id,
        "nome": "Viajante Convidado",
        "email": "visitante@local.dev",
        "foto": "https://lh3.googleusercontent.com/a/default-user=s96-c",
        "tipo": "visitante",
    }
    viagens_visitante_memoria.setdefault(visitor_id, [])

    return redirect(url_for("index"))


@app.route("/auth/logout", methods=["GET", "POST"])
def logout():
    """Encerra a sessão e descarta a memória de visitante."""
    usuario = session.get("usuario")
    if usuario and isinstance(usuario, dict):
        user_id = str(usuario.get("id", ""))
        if usuario.get("tipo") == "visitante":
            viagens_visitante_memoria.pop(user_id, None)

    session.clear()
    return redirect(url_for("index"))


@app.route("/viagens/criar", methods=["GET", "POST"])
def criar_viagem():
    """Processa o formulário de criação com deduplicação (locks) e orquestração de APIs."""
    # Defesa contra acesso direto via GET (Padrão PRG)
    if request.method != "POST":
        return redirect(url_for("index"))

    usuario = session.get("usuario")
    if not usuario or not isinstance(usuario, dict) or "id" not in usuario:
        return redirect(url_for("index"))

    user_id = str(usuario["id"])

    # Extração de campos
    origem_cidade_raw = request.form.get("origem_cidade", "")
    origem_uf_raw = request.form.get("origem_uf", "")
    destino_cidade_raw = request.form.get("destino_cidade", "")
    destino_uf_raw = request.form.get("destino_uf", "")

    # Higienização defensiva (Aluno 4 com fallback)
    origem_cidade = (sanitizar_entrada(origem_cidade_raw) or origem_cidade_raw).strip()
    origem_uf = origem_uf_raw.strip().upper()
    destino_cidade = (
        sanitizar_entrada(destino_cidade_raw) or destino_cidade_raw
    ).strip()
    destino_uf = destino_uf_raw.strip().upper()

    if not origem_cidade or not destino_cidade:
        return redirect(url_for("index"))

    # Chave canônica de idempotência
    chave_idempotencia = f"{user_id}:{origem_cidade.lower()}:{origem_uf}:{destino_cidade.lower()}:{destino_uf}"
    agora = time.time()

    # Controle de concorrência e deduplicação via Locks
    with lock_requisicoes:
        # 1. Bloqueio in-flight (requisição em processamento)
        if chave_idempotencia in requisicoes_ativas:
            return redirect(url_for("index"))

        # 2. Bloqueio temporal de cooldown (4 segundos)
        if (
            chave_idempotencia in requisicoes_recentes
            and (agora - requisicoes_recentes[chave_idempotencia]) < 4.0
        ):
            return redirect(url_for("index"))

        # Limpeza de chaves antigas (> 60 segundos)
        chaves_antigas = [
            k for k, ts in requisicoes_recentes.items() if agora - ts > 60.0
        ]
        for k in chaves_antigas:
            requisicoes_recentes.pop(k, None)

        requisicoes_ativas.add(chave_idempotencia)
        requisicoes_recentes[chave_idempotencia] = agora

    # Orquestração externa com garantia de liberação do lock no finally
    try:
        nome_origem = f"{origem_cidade} - {origem_uf}" if origem_uf else origem_cidade
        nome_destino = (
            f"{destino_cidade} - {destino_uf}" if destino_uf else destino_cidade
        )
        clima = {"temperatura": "N/D", "umidade": "N/D", "vento": "N/D"}
        percurso = {"distancia": "N/D", "tempo": "N/D"}
        guia_texto = "Roteiro em processamento."
        diagnostico: dict[str, Any] = {}

        # ----------------------------------------------------------------------
        # 💡 GUIA DE INTEGRAÇÃO & RESILIÊNCIA (ALUNOS 1 E 2 via services.py):
        # - Eixo 3 (Connection Pooling & Timeouts):
        #   Configuramos explicitamente limites de pool HTTPX (Keep-Alive) que é
        #   reaproveitado de ponta a ponta nas 4 chamadas externas consecutivas:
        #     1) buscar_coordenadas(origem)  -> Aluno 1 (Open-Meteo Geocoding)
        #     2) buscar_coordenadas(destino) -> Aluno 1 (Open-Meteo Geocoding)
        #     3) obter_clima(destino)        -> Aluno 2 (Open-Meteo Weather)
        #     4) obter_percurso(o -> d)      -> Aluno 2 (OSRM Routing)
        #   NOTA CRÍTICA DE TIMEOUT: O timeout=15.0s do client abaixo é o teto
        #   máximo de tolerância do Gateway (Aluno 3).
        #   Em services.py:
        #     - Aluno 1 DEVE definir timeout=4.0s na chamada de geocodificação:
        #       client.get(url, timeout=4.0)
        #     - Aluno 2 DEVE definir timeout=4.0s no clima e timeout=6.0s no percurso.
        # - Eixo 1 / Geocodificação (Aluno 1):
        #   `buscar_coordenadas` deve consultar Open-Meteo com 'country_codes=BR',
        #   tratar o campo 'admin1' com `obter_sigla_uf(admin1, uf)` para obter a
        #   sigla de 2 letras e retornar tupla no formato: (lat, lon, "Cidade - UF").
        # ----------------------------------------------------------------------
        pool_limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        with httpx.Client(limits=pool_limits, timeout=15.0) as client:
            # 1. Geocodificação de origem e destino (Aluno 1)
            coord_o = buscar_coordenadas(client, origem_cidade, origem_uf)
            if coord_o and len(coord_o) == 3:
                lat_o, lon_o, nome_o = coord_o
                if nome_o:
                    nome_origem = nome_o
            else:
                lat_o, lon_o = 0.0, 0.0

            coord_d = buscar_coordenadas(client, destino_cidade, destino_uf)
            if coord_d and len(coord_d) == 3:
                lat_d, lon_d, nome_d = coord_d
                if nome_d:
                    nome_destino = nome_d
            else:
                lat_d, lon_d = 0.0, 0.0

            # 2. Telemetria Climática e Percurso (Aluno 2)
            clima_res = obter_clima(client, lat_d, lon_d)
            if clima_res:
                clima = clima_res

            percurso_res = obter_percurso(client, lat_o, lon_o, lat_d, lon_d)
            if percurso_res:
                percurso = percurso_res

        # 3. Inteligência Artificial Gemini (Aluno 2)
        ia_res = obter_guia_destino_com_diagnostico(nome_destino)
        if ia_res and len(ia_res) == 2:
            guia_texto, diagnostico = ia_res

        # Montagem do registro da viagem
        viagem = {
            "id": str(uuid.uuid4()),
            "criado_em": datetime.now(timezone.utc).isoformat(),
            "origem": nome_origem,
            "destino": nome_destino,
            "clima": clima,
            "percurso": percurso,
            "dicas_destino": guia_texto,
            "diagnostico_ia": diagnostico,
        }

        # Persistência via função do Aluno 4 (memória para visitante ou base JSON para usuário logado)
        adicionar_viagem_usuario(user_id, viagem, usuario)

        # Feedback defensivo via Toast se o Gemini falhar por tempo limite (timeout)
        if diagnostico and (
            diagnostico.get("motivo") == "timeout"
            or "timeout" in str(diagnostico.get("motivo", "")).lower()
        ):
            flash(
                "O serviço Gemini excedeu o tempo limite da requisição. Um guia de contingência foi gerado.",
                "erro",
            )

    except Exception as err:  # noqa: BLE001 - barreira defensiva para falhas de orquestração externa
        app.logger.error("Falha ao orquestrar serviços de viagem: %s", err)
        if "timeout" in str(err).lower():
            flash(
                "O serviço Gemini excedeu o tempo limite da requisição. Um guia de contingência foi gerado.",
                "erro",
            )
    finally:
        with lock_requisicoes:
            requisicoes_ativas.discard(chave_idempotencia)

    # Padrão PRG: Redireciona sempre para index
    return redirect(url_for("index"))


@app.route("/viagens/deletar/<string:viagem_id>", methods=["GET", "POST"])
def deletar_viagem(viagem_id: str):
    """Exclui um roteiro da lista do usuário."""
    usuario = session.get("usuario")
    if usuario and isinstance(usuario, dict) and "id" in usuario:
        user_id = str(usuario["id"])
        remover_viagem_usuario(user_id, viagem_id)

    # Padrão PRG
    return redirect(url_for("index"))


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 4: Endpoint REST e Error Handlers Globais
# ==============================================================================


@app.route("/viagens/json", methods=["GET"])
@app.route("/api/viagens/json", methods=["GET"])
@app.route("/api/viagens", methods=["GET"])
def ver_viagens_json():
    """Retorna a base consolidada de static/data/viagens.json com suporte dinâmico a visitantes."""

    # Aluno 4
    # Carrega a estrutura persistida no arquivo JSON.
    dados = carregar_dados_viagens_json()

    # Retorna os dados no formato JSON através do Flask.
    # jsonify também define automaticamente o Content-Type
    # apropriado para uma resposta JSON.
    return jsonify(dados)


@app.errorhandler(405)
def metodo_nao_permitido(error):
    """Fallback para acessos GET em rotas POST (ex: digitar /viagens/criar na barra de endereços)."""

    # Aluno 4
    # O erro 405 acontece quando a rota existe,
    # mas o método HTTP utilizado não é permitido.
    # Exemplo: enviar POST para uma rota que aceita apenas GET.

    # Redireciona o usuário para a página inicial
    # em vez de apresentar uma página de erro.
    return redirect(url_for("index"))


@app.errorhandler(404)
def pagina_nao_encontrada(error):
    """Fallback para rotas inexistentes redirecionando suavemente para a página principal."""
    # O erro 404 acontece quando a rota solicitada não existe.

    # Redireciona o usuário para a página inicial
    # em vez de apresentar uma página de erro.
    return redirect(url_for("index"))


if __name__ == "__main__":
    print(f"🌍 Servidor Flask Guia do Turista rodando em http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
