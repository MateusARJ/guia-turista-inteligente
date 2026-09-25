"""Autenticação e geocodificação com provedores simulados."""

from unittest.mock import Mock

import httpx
import pytest

import services


@pytest.fixture
def token_valido(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(services, "GOOGLE_CLIENT_ID", "cliente-teste")
    monkeypatch.setattr(services.time, "time", lambda: 1000.0)
    return {
        "aud": "cliente-teste",
        "iss": "https://accounts.google.com",
        "exp": "2000",
        "sub": "123",
        "name": "Pessoa Teste",
    }


def test_token_valido_e_contrato_http(token_valido: dict[str, object]) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "oauth2.googleapis.com"
        assert request.url.path == "/tokeninfo"
        assert request.url.params["id_token"] == "token-teste"
        assert all(v == 4.0 for v in request.extensions["timeout"].values())
        return httpx.Response(200, json=token_valido)

    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        assert services.verificar_token_google(client, "token-teste") == token_valido
        assert not client.is_closed


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("aud", "outro-cliente"),
        ("aud", None),
        ("iss", "https://falso.test"),
        ("iss", None),
        ("sub", ""),
        ("sub", None),
        ("sub", 123),
        ("exp", "999"),
        ("exp", 1000),
        ("exp", None),
        ("exp", True),
        ("exp", "NaN"),
        ("exp", float("inf")),
        ("exp", []),
        ("exp", "invalido"),
    ],
)
def test_token_claims_invalidas(
    token_valido: dict[str, object], campo: str, valor: object
) -> None:
    client = Mock(spec=httpx.Client)
    client.get.return_value.json.return_value = {**token_valido, campo: valor}
    assert services.verificar_token_google(client, "token-teste") is None


@pytest.mark.parametrize("payload", [None, [], "texto", {}, {"aud": "cliente-teste"}])
def test_token_payload_incompleto(
    token_valido: dict[str, object], payload: object
) -> None:
    client = Mock(spec=httpx.Client)
    client.get.return_value.json.return_value = payload
    assert services.verificar_token_google(client, "token-teste") is None


@pytest.mark.parametrize("token", ["", "  "])
def test_token_vazio_nao_consulta(token: str) -> None:
    client = Mock(spec=httpx.Client)
    assert services.verificar_token_google(client, token) is None
    client.get.assert_not_called()


@pytest.mark.parametrize(
    "admin1,informada,esperada",
    [
        ("Piauí", "RJ", "PI"),
        (" PIAUI ", "RJ", "PI"),
        ("sao   paulo", "", "SP"),
        ("pi", "RJ", "PI"),
        ("Distrito Federal", "", "DF"),
        ("", " rj ", "RJ"),
        ("Desconhecido", "ZZ", ""),
        ("", "", ""),
    ],
)
def test_sigla_uf(admin1: str, informada: str, esperada: str) -> None:
    assert services.obter_sigla_uf(admin1, informada) == esperada


@pytest.mark.parametrize("sigla,nome", list(services.ESTADOS_BRASIL.items()))
def test_catalogo_completo(sigla: str, nome: str) -> None:
    assert services.obter_sigla_uf(nome) == sigla


LOCAL = {
    "name": "Teresina",
    "country_code": "BR",
    "latitude": -5.09,
    "longitude": -42.8,
    "admin1": "Piauí",
}


def test_teresina_corrige_uf_e_contrato_http() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "geocoding-api.open-meteo.com"
        assert request.url.path == "/v1/search"
        assert dict(request.url.params) == {
            "name": "Teresina",
            "count": "10",
            "language": "pt",
            "format": "json",
            "country_codes": "BR",
        }
        assert all(v == 4.0 for v in request.extensions["timeout"].values())
        return httpx.Response(200, json={"results": [LOCAL]})

    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        assert services.buscar_coordenadas(client, "Teresina", "RJ") == (
            -5.09,
            -42.8,
            "Teresina - PI",
        )
        assert not client.is_closed


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"results": None},
        {"results": []},
        {"results": {}},
        {"results": [None, {}]},
    ],
)
def test_geocoding_payload_inadequado(payload: object) -> None:
    client = Mock(spec=httpx.Client)
    client.get.return_value.json.return_value = payload
    assert services.buscar_coordenadas(client, "Inexistente", "RJ") == (0.0, 0.0, "Inexistente - RJ")


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("latitude", None),
        ("latitude", True),
        ("latitude", "-5.09"),
        ("latitude", float("nan")),
        ("latitude", 91),
        ("longitude", 181),
        ("country_code", "US"),
        ("country_code", None),
    ],
)
def test_geocoding_rejeita_local_invalido(campo: str, valor: object) -> None:
    client = Mock(spec=httpx.Client)
    client.get.return_value.json.return_value = {"results": [{**LOCAL, campo: valor}]}
    assert services.buscar_coordenadas(client, "Teresina", "ZZ") == (0.0, 0.0, "Teresina")


def test_geocoding_sem_admin1_usa_uf_informada() -> None:
    local = {k: v for k, v in LOCAL.items() if k != "admin1"}
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"results": [local]})
        )
    ) as client:
        assert services.buscar_coordenadas(client, "Teresina", "pi") == (
            -5.09,
            -42.8,
            "Teresina - PI",
        )


def test_geocoding_prioriza_nome_exato_e_ignora_resultado_estrangeiro() -> None:
    resultados = [
        {**LOCAL, "country_code": "US"},
        {**LOCAL, "name": "Teresina de Goiás", "admin1": "Goiás"},
        LOCAL,
    ]
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"results": resultados})
        )
    ) as client:
        assert services.buscar_coordenadas(client, " teresina ", "RJ") == (
            -5.09,
            -42.8,
            "Teresina - PI",
        )


def test_cidade_vazia_nao_consulta() -> None:
    client = Mock(spec=httpx.Client)
    assert services.buscar_coordenadas(client, "  ", "PI") == (0.0, 0.0, "")
    client.get.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_falhas_http(status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json={}))
    ) as client:
        assert services.verificar_token_google(client, "token-teste") is None
        assert services.buscar_coordenadas(client, "Teresina", "PI") == (0.0, 0.0, "Teresina - PI")


def test_json_invalido() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="nao-json"))
    ) as client:
        assert services.verificar_token_google(client, "token-teste") is None
        assert services.buscar_coordenadas(client, "Teresina", "PI") == (0.0, 0.0, "Teresina - PI")


@pytest.mark.parametrize(
    "erro", [httpx.ConnectError("rede"), httpx.ReadTimeout("timeout")]
)
def test_rede_e_timeout(erro: httpx.HTTPError) -> None:
    client = Mock(spec=httpx.Client)
    client.get.side_effect = erro
    assert services.verificar_token_google(client, "token-teste") is None
    assert services.buscar_coordenadas(client, "Teresina", "PI") == (0.0, 0.0, "Teresina - PI")


def test_nao_oculta_erro_de_programacao() -> None:
    client = Mock(spec=httpx.Client)
    client.get.side_effect = RuntimeError("bug")
    with pytest.raises(RuntimeError):
        services.verificar_token_google(client, "token-teste")
    with pytest.raises(RuntimeError):
        services.buscar_coordenadas(client, "Teresina", "PI")
