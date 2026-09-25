# Serviços de integração com APIs externas (Google OAuth, Open-Meteo e OSRM)

import re
from typing import Any
import unicodedata

import httpx

from config import ESTADOS_BRASIL, GOOGLE_CLIENT_ID

# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 1: APIs REST, Autenticação JWT e Geocodificação
# ==============================================================================


def verificar_token_google(client: httpx.Client, token: str) -> dict[str, Any] | None:
    """Valida o token JWT no endpoint oficial 'https://oauth2.googleapis.com/tokeninfo'.

    Verifica se o token foi emitido para o GOOGLE_CLIENT_ID configurado no projeto
    e retorna o payload do usuário (sub, name, email, picture) ou None se for inválido.
    """
    if not token or not isinstance(token, str) or not token.strip():
        return None

    try:
        resposta = client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token.strip()},
            timeout=4.0,
        )
        if resposta.status_code != 200:
            return None

        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not isinstance(dados, dict):
        return None

    # Validação do Audience (aud) contra o GOOGLE_CLIENT_ID do projeto
    if dados.get("aud") != GOOGLE_CLIENT_ID:
        return None

    # Validação da presença do subject (identificador único do usuário no Google)
    if not dados.get("sub"):
        return None

    payload: dict[str, Any] = dict(dados)
    payload.setdefault("id", payload.get("sub", ""))
    payload.setdefault("nome", payload.get("name", ""))
    payload.setdefault("foto", payload.get("picture", ""))

    return payload


def _normalizar_texto(texto: str) -> str:
    """Remove acentos, espaços extras e converte para minúsculas para comparação fonética."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def obter_sigla_uf(admin1: str, uf_informada: str = "") -> str:
    """Converte o estado retornado pela API (admin1) para a sigla oficial de 2 letras (ex: 'PI').

    Caso a API retorne um nome completo (ex: 'Piauí'), normaliza para a sigla 'PI'.
    Caso contrário, utiliza a UF informada como fallback se for válida.
    """
    admin1_limpo = (admin1 or "").strip()
    uf_limpa = (uf_informada or "").strip().upper()

    # 1. Verifica se admin1 já é uma sigla válida de 2 letras
    admin1_upper = admin1_limpo.upper()
    if admin1_upper in ESTADOS_BRASIL:
        return admin1_upper

    # 2. Compara o nome completo normalizado (sem acentos) com o catálogo oficial
    admin1_norm = _normalizar_texto(admin1_limpo)
    if admin1_norm:
        for sigla, nome in ESTADOS_BRASIL.items():
            if _normalizar_texto(nome) == admin1_norm:
                return sigla

    # 3. Fallback: se a API não retornou estado reconhecido, utiliza a UF informada se for válida
    if uf_limpa in ESTADOS_BRASIL:
        return uf_limpa

    return uf_limpa


def buscar_coordenadas(
    client: httpx.Client, cidade: str, uf: str = ""
) -> tuple[float, float, str]:
    """Consulta o Open-Meteo Geocoding com filtro Brasil (country_codes=BR) e timeout=4.0s.

    Retorna a tupla (latitude, longitude, nome_formatado). Caso a busca falhe,
    aplica fallback seguro retornando (0.0, 0.0, "Cidade - UF").
    """
    cidade_limpa = (cidade or "").strip()
    uf_limpa = (uf or "").strip().upper()
    fallback_nome = (
        f"{cidade_limpa} - {uf_limpa}".strip(" -")
        if cidade_limpa
        else (uf_limpa or "")
    )

    if not cidade_limpa:
        return (0.0, 0.0, fallback_nome)

    try:
        resposta = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": cidade_limpa,
                "count": 10,
                "language": "pt",
                "format": "json",
                "country_codes": "BR",
            },
            timeout=4.0,
        )
        if resposta.status_code != 200:
            return (0.0, 0.0, fallback_nome)

        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return (0.0, 0.0, fallback_nome)

    if not isinstance(dados, dict):
        return (0.0, 0.0, fallback_nome)

    resultados = dados.get("results")
    if not isinstance(resultados, list) or not resultados:
        return (0.0, 0.0, fallback_nome)

    # Filtro estrito para o território brasileiro (country_code == 'BR')
    resultados_brasil = [
        item for item in resultados
        if isinstance(item, dict) and str(item.get("country_code", "")).upper() == "BR"
    ]
    lista_candidatos = resultados_brasil if resultados_brasil else [
        item for item in resultados if isinstance(item, dict)
    ]
    if not lista_candidatos:
        return (0.0, 0.0, fallback_nome)

    # Desambiguação: prioriza resultado cujo admin1 pertença à UF informada
    item_escolhido = lista_candidatos[0]
    if uf_limpa in ESTADOS_BRASIL:
        for item in lista_candidatos:
            # Consulta sem fallback para não validar regiões fora da UF
            if obter_sigla_uf(str(item.get("admin1", ""))) == uf_limpa:
                item_escolhido = item
                break

    try:
        lat = float(item_escolhido.get("latitude", 0.0))
        lon = float(item_escolhido.get("longitude", 0.0))
    except (TypeError, ValueError):
        return (0.0, 0.0, fallback_nome)

    # Detecção da UF oficial real a partir do campo admin1 (com fallback para uf_limpa se admin1 for genérico)
    admin1_api = str(item_escolhido.get("admin1", ""))
    uf_detectada = obter_sigla_uf(admin1_api, uf_limpa)

    nome_cidade = str(item_escolhido.get("name", cidade_limpa))
    nome_formatado = f"{nome_cidade} - {uf_detectada}" if uf_detectada else nome_cidade

    return (lat, lon, nome_formatado)


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 2: Telemetria Climática e Roteamento Rodoviário
# ==============================================================================


def obter_clima(client: httpx.Client, lat: float, lon: float) -> dict[str, str]:
    """Consulta o Open-Meteo Forecast e retorna temperatura (°C), umidade (%) e vento (km/h).

    Caso coordenadas sejam inválidas (0.0, 0.0) ou ocorra timeout (4.0s),
    retorna dicionário de contingência com valores 'N/D'.
    """
    # TODO (Aluno 2): Implementar a consulta à API Open-Meteo Forecast com timeout e fallback
    pass


def obter_percurso(
    client: httpx.Client, lat_o: float, lon_o: float, lat_d: float, lon_d: float
) -> dict[str, str]:
    """Consulta o OSRM e calcula distância em km e duração de viagem de carro.

    Em caso de trajetos sem estradas (ex: ilhas) ou timeout (6.0s),
    retorna dicionário com fallback descritivo ('Sem rota direta' / 'Considere voos ou barcos').
    """
    # TODO (Aluno 2): Implementar o cálculo de rota e distância via OSRM com conversão de unidades
    pass
