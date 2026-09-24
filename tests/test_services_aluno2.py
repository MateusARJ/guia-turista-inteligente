"""Contratos de clima e percurso, sem acesso às APIs públicas."""

from unittest.mock import Mock

import httpx
import pytest

from services import obter_clima, obter_percurso

CLIMA_ND = {"temperatura": "N/D", "umidade": "N/D", "vento": "N/D"}
SEM_ROTA = {
    "distancia": "Sem rota direta",
    "tempo": "Considere voos ou barcos",
    "modal": "alternativo",
}
CLIMA = {
    "current": {
        "temperature_2m": 28.5,
        "relative_humidity_2m": 35,
        "wind_speed_10m": 12.0,
    }
}


def test_clima_sucesso_e_requisicao() -> None:

    def responder(request: httpx.Request) -> httpx.Response:
        assert (
            str(request.url.copy_with(query=None))
            == "https://api.open-meteo.com/v1/forecast"
        )
        assert request.url.params["latitude"] == "-8.05"
        assert request.url.params["longitude"] == "-34.9"
        assert (
            request.url.params["current"]
            == "temperature_2m,relative_humidity_2m,wind_speed_10m"
        )
        assert request.url.params["temperature_unit"] == "celsius"
        assert request.url.params["wind_speed_unit"] == "kmh"
        assert all(v == 4.0 for v in request.extensions["timeout"].values())
        return httpx.Response(200, json=CLIMA)

    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        assert obter_clima(client, -8.05, -34.9) == {
            "temperatura": "28.5 °C",
            "umidade": "35%",
            "vento": "12.0 km/h",
        }
        assert not client.is_closed


@pytest.mark.parametrize(
    "lat,lon",
    (
        (0, 0),
        (91, 1),
        (1, 181),
        (-91, 1),
        (1, -181),
        (float("nan"), 1),
        (1, float("inf")),
        (True, 1),
    ),
)
def test_coordenadas_invalidas_nao_consultam(lat: float, lon: float) -> None:
    client = Mock(spec=httpx.Client)
    assert obter_clima(client, lat, lon) == CLIMA_ND
    assert obter_percurso(client, lat, lon, -8, -34) == SEM_ROTA
    assert obter_percurso(client, -8, -34, lat, lon) == SEM_ROTA
    client.get.assert_not_called()


def test_clima_payload_inadequado() -> None:
    payloads: list[object] = [None, [], {}, {"current": []}, {"current": {}}]
    valor: object
    for campo in CLIMA["current"]:
        for valor in (None, "12", True, [], {}, float("nan"), float("inf")):
            payloads.append({"current": {**CLIMA["current"], campo: valor}})
        incompleto = dict(CLIMA["current"])
        incompleto.pop(campo)
        payloads.append({"current": incompleto})
    payloads.extend(
        [
            {"current": {**CLIMA["current"], "relative_humidity_2m": 101}},
            {"current": {**CLIMA["current"], "relative_humidity_2m": -1}},
            {"current": {**CLIMA["current"], "wind_speed_10m": -1}},
        ]
    )
    for payload in payloads:
        client = Mock(spec=httpx.Client)
        client.get.return_value.json.return_value = payload
        assert obter_clima(client, -8, -34) == CLIMA_ND


def test_clima_zero_e_negativo_sao_validos() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "current": {
                        "temperature_2m": -2,
                        "relative_humidity_2m": 0,
                        "wind_speed_10m": 0,
                    }
                },
            )
        )
    ) as client:
        assert obter_clima(client, 0, -34) == {
            "temperatura": "-2.0 °C",
            "umidade": "0%",
            "vento": "0.0 km/h",
        }


def test_percurso_sucesso_e_requisicao() -> None:

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "router.project-osrm.org"
        assert request.url.path == "/route/v1/driving/-34.9,-8.05;-35.2,-9.1"
        assert request.url.params["overview"] == "false"
        assert request.url.params["radiuses"] == "1000;1000"
        assert all(v == 6.0 for v in request.extensions["timeout"].values())
        return httpx.Response(
            200,
            json={"code": "Ok", "routes": [{"distance": 1674600, "duration": 77880}]},
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        assert obter_percurso(client, -8.05, -34.9, -9.1, -35.2) == {
            "distancia": "1674.6 km",
            "tempo": "21h 38min de carro",
            "modal": "carro",
        }
        assert not client.is_closed


@pytest.mark.parametrize(
    "segundos,esperado",
    (
        (0, "0h 0min"),
        (29, "0h 0min"),
        (30, "0h 1min"),
        (3599, "1h 0min"),
        (7199, "2h 0min"),
    ),
)
def test_arredondamento_minutos(segundos: int, esperado: str) -> None:
    client = Mock(spec=httpx.Client)
    client.get.return_value.json.return_value = {
        "code": "Ok",
        "routes": [{"distance": 0, "duration": segundos}],
    }
    assert obter_percurso(client, -8, -34, -8, -34)["tempo"] == esperado + " de carro"


def test_fernando_de_noronha_sem_rota() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"code": "NoRoute", "routes": []})
        )
    ) as client:
        assert obter_percurso(client, -8.05, -34.9, -3.85, -32.42) == SEM_ROTA


def test_percurso_payload_inadequado() -> None:
    payloads: list[object] = [
        None,
        [],
        {},
        {"code": "NoSegment"},
        {"code": "Ok"},
        {"code": "Ok", "routes": []},
        {"code": "Ok", "routes": {}},
        {"code": "Ok", "routes": [None]},
    ]
    valor: object
    for campo in ("distance", "duration"):
        for valor in (None, "12", True, [], {}, -1, float("nan"), float("inf")):
            payloads.append(
                {
                    "code": "Ok",
                    "routes": [{"distance": 1000, "duration": 60, campo: valor}],
                }
            )
        payloads.append({"code": "Ok", "routes": [{campo: 1}]})
    for payload in payloads:
        client = Mock(spec=httpx.Client)
        client.get.return_value.json.return_value = payload
        assert obter_percurso(client, -8, -34, -9, -35) == SEM_ROTA


def test_erros_http_e_json_em_ambos_servicos() -> None:
    for status in (400, 429, 500, 503):
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda r, status=status: httpx.Response(status, json={})
            )
        ) as client:
            assert obter_clima(client, -8, -34) == CLIMA_ND
            assert obter_percurso(client, -8, -34, -9, -35) == SEM_ROTA
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="JSON inválido")
        )
    ) as client:
        assert obter_clima(client, -8, -34) == CLIMA_ND
        assert obter_percurso(client, -8, -34, -9, -35) == SEM_ROTA


def test_rede_timeout_e_erro_de_programacao() -> None:
    for erro in (httpx.ConnectError("rede"), httpx.ReadTimeout("tempo")):
        client = Mock(spec=httpx.Client)
        client.get.side_effect = erro
        assert obter_clima(client, -8, -34) == CLIMA_ND
        assert obter_percurso(client, -8, -34, -9, -35) == SEM_ROTA
    client.get.side_effect = RuntimeError("bug")
    with pytest.raises(RuntimeError):
        obter_clima(client, -8, -34)
    with pytest.raises(RuntimeError):
        obter_percurso(client, -8, -34, -9, -35)


if __name__ == "__main__":
    pytest.main([__file__])
