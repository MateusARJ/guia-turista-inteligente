# Serviços de integração com APIs externas (Google OAuth, Open-Meteo e OSRM)

import math
import time
import unicodedata
from typing import Any

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
    # TODO (Aluno 1): Implementar a validação do token JWT junto à API do Google OAuth2
    if not isinstance(token, str) or not token.strip() or not GOOGLE_CLIENT_ID.strip():
        return None
    try:
        resposta = client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token.strip()},
            timeout=4.0,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(dados, dict) or dados.get("aud") != GOOGLE_CLIENT_ID:
        return None
    if dados.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    if not isinstance(dados.get("sub"), str) or not dados["sub"].strip():
        return None
    # tokeninfo pode devolver exp como string decimal.
    expiracao = dados.get("exp")
    if isinstance(expiracao, str) and expiracao.isascii() and expiracao.isdecimal():
        try:
            expiracao = int(expiracao)
        except ValueError:
            return None
    exp = _numero_finito(expiracao)
    if exp is None or exp <= time.time():
        return None
    return dados


def _normalizar_nome_local(texto: str) -> str:
    """Compara nomes sem depender de acentos, caixa ou espaços duplicados."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return " ".join(
        "".join(c for c in normalizado if not unicodedata.combining(c)).casefold().split()
    )


def obter_sigla_uf(admin1: str, uf_informada: str = "") -> str:
    """Converte o estado retornado pela API (admin1) para a sigla oficial de 2 letras (ex: 'PI').

    Caso a API retorne um nome completo (ex: 'Piauí'), normaliza para a sigla 'PI'.
    Caso contrário, utiliza a UF informada como fallback se for válida.
    """
    # TODO (Aluno 1): Implementar a conversão e normalização da UF
    nome = _normalizar_nome_local(admin1) if isinstance(admin1, str) else ""
    for sigla, estado in ESTADOS_BRASIL.items():
        if nome in (sigla.casefold(), _normalizar_nome_local(estado)):
            return sigla
    fallback = uf_informada.strip().upper() if isinstance(uf_informada, str) else ""
    return fallback if fallback in ESTADOS_BRASIL else ""


def buscar_coordenadas(
    client: httpx.Client, cidade: str, uf: str = ""
) -> tuple[float, float, str]:
    """Consulta o Open-Meteo Geocoding com filtro Brasil (country_codes=BR) e timeout=4.0s.

    Retorna (latitude, longitude, nome_formatado), preservando o contrato de app.py.
    Em falha, retorna (0.0, 0.0, "Cidade - UF"), com a UF informada validada.
    """
    # TODO (Aluno 1): Implementar a consulta à API de Geocodificação Open-Meteo com filtro Brasil
    nome_cidade = cidade.strip() if isinstance(cidade, str) else ""
    uf_fallback = obter_sigla_uf("", uf)
    nome_fallback = f"{nome_cidade} - {uf_fallback}" if nome_cidade and uf_fallback else nome_cidade
    fallback = (0.0, 0.0, nome_fallback)
    if not isinstance(cidade, str) or not cidade.strip():
        return fallback
    try:
        resposta = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": cidade.strip(), "count": 10, "language": "pt",
                "format": "json", "country_codes": "BR",
            },
            timeout=4.0,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return fallback
    if not isinstance(dados, dict) or not isinstance(dados.get("results"), list):
        return fallback
    # Prioriza o nome exato entre resultados brasileiros válidos, sem filtrar
    # pela UF digitada: ela pode estar errada, como em Teresina / RJ.
    candidatos: list[tuple[bool, float, float, str]] = []
    for local in dados["results"]:
        if not isinstance(local, dict) or local.get("country_code") != "BR":
            continue
        lat = _numero_finito(local.get("latitude"))
        lon = _numero_finito(local.get("longitude"))
        if lat is None or lon is None or not _coordenadas_validas(lat, lon):
            continue
        nome = local.get("name")
        exato = isinstance(nome, str) and _normalizar_nome_local(nome) == _normalizar_nome_local(cidade)
        sigla = obter_sigla_uf(local.get("admin1", ""), uf)
        nome_local = nome.strip() if isinstance(nome, str) and nome.strip() else nome_cidade
        nome_formatado = f"{nome_local} - {sigla}" if sigla else nome_local
        candidatos.append((exato, lat, lon, nome_formatado))
    if not candidatos:
        return fallback
    _, lat, lon, nome_formatado = max(candidatos, key=lambda item: item[0])
    return lat, lon, nome_formatado


# ==============================================================================
# 👤 RESPONSABILIDADE DO ALUNO 2: Telemetria Climática e Roteamento Rodoviário
# ==============================================================================

# ==============================================================================
# RESPONSAVEL: @MailsonSousa88
# ==============================================================================

def _numero_finito(valor: object) -> float | None:
    """Aceita apenas números JSON finitos, sem converter strings ou booleanos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        numero = float(valor)
    except OverflowError:
        return None
    return numero if math.isfinite(numero) else None


def _coordenadas_validas(lat: float, lon: float) -> bool:
    latitude, longitude = _numero_finito(lat), _numero_finito(lon)
    return (
        latitude is not None and longitude is not None
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
        and (latitude, longitude) != (0.0, 0.0)
    )


def obter_clima(client: httpx.Client, lat: float, lon: float) -> dict[str, str]:
    """Consulta o Open-Meteo Forecast e retorna temperatura (°C), umidade (%) e vento (km/h).

    Caso coordenadas sejam inválidas (0.0, 0.0) ou ocorra timeout (4.0s),
    retorna dicionário de contingência com valores 'N/D'.
    """
    # TODO (Aluno 2): Implementar a consulta à API Open-Meteo Forecast com timeout e fallback
    pass  # noqa: PIE790 - estrutura original preservada; implementação abaixo.
    contingencia = {"temperatura": "N/D", "umidade": "N/D", "vento": "N/D"}
    if not _coordenadas_validas(lat, lon):
        return contingencia
    try:
        resposta = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "temperature_unit": "celsius", "wind_speed_unit": "kmh",
            },
            timeout=4.0,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return contingencia
    if not isinstance(dados, dict) or not isinstance(dados.get("current"), dict):
        return contingencia
    atual = dados["current"]
    temperatura = _numero_finito(atual.get("temperature_2m"))
    umidade = _numero_finito(atual.get("relative_humidity_2m"))
    vento = _numero_finito(atual.get("wind_speed_10m"))
    if (
        temperatura is None or umidade is None or vento is None
        or not 0 <= umidade <= 100 or vento < 0
    ):
        return contingencia
    return {
        "temperatura": f"{temperatura} °C",
        "umidade": f"{umidade:g}%",
        "vento": f"{vento} km/h",
    }


def obter_percurso(
    client: httpx.Client, lat_o: float, lon_o: float, lat_d: float, lon_d: float
) -> dict[str, str]:
    """Consulta o OSRM e calcula distância em km e duração de viagem de carro.

    Em caso de trajetos sem estradas (ex: ilhas) ou timeout (6.0s),
    retorna dicionário com fallback descritivo ('Sem rota direta' / 'Considere voos ou barcos').
    """
    # TODO (Aluno 2): Implementar o cálculo de rota e distância via OSRM com conversão de unidades
    pass  # noqa: PIE790 - estrutura original preservada; implementação abaixo.
    contingencia = {
        "distancia": "Sem rota direta",
        "tempo": "Considere voos ou barcos",
        "modal": "alternativo",
    }
    if not (_coordenadas_validas(lat_o, lon_o) and _coordenadas_validas(lat_d, lon_d)):
        return contingencia
    try:
        resposta = client.get(
            f"https://router.project-osrm.org/route/v1/driving/{lon_o},{lat_o};{lon_d},{lat_d}",
            # Evita que um ponto insular seja deslocado para uma estrada distante.
            params={"overview": "false", "radiuses": "1000;1000"},
            timeout=6.0,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return contingencia
    if not isinstance(dados, dict) or dados.get("code") != "Ok":
        return contingencia
    rotas = dados.get("routes")
    if not isinstance(rotas, list) or not rotas or not isinstance(rotas[0], dict):
        return contingencia
    distancia = _numero_finito(rotas[0].get("distance"))
    duracao = _numero_finito(rotas[0].get("duration"))
    if distancia is None or duracao is None or distancia < 0 or duracao < 0:
        return contingencia
    # Arredonda os minutos totais antes de separar horas, evitando "1h 60min".
    minutos_totais = math.floor(duracao / 60 + 0.5)
    horas, minutos = divmod(minutos_totais, 60)
    return {
        "distancia": f"{round(distancia / 1000, 1)} km",
        "tempo": f"{horas}h {minutos}min de carro",
        "modal": "carro",
    }
