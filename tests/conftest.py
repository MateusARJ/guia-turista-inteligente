"""A suíte automatizada não usa rede nem credenciais reais."""

import httpx
import pytest

import planejamento


@pytest.fixture(autouse=True)
def isolar_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planejamento, "GEMINI_KEY", "chave-de-teste")

    def bloquear_rede(*args: object, **kwargs: object) -> None:
        pytest.fail("Teste tentou acessar a rede; use MockTransport ou um mock do SDK.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", bloquear_rede)
