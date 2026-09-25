"""Valida as demonstrações sem enviar requisições reais."""

from unittest.mock import Mock

import pytest

import planejamento
from scripts import testar


def test_fallback_mostra_guia_e_preserva_chave(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chave_original = planejamento.GEMINI_KEY
    assert testar.main(["fallback", "--destino", "Olinda, PE"]) == 0
    saida = capsys.readouterr().out
    assert "Olinda, PE" in saida
    assert "chave_ausente" in saida
    assert chave_original not in saida
    assert planejamento.GEMINI_KEY == chave_original


@pytest.mark.parametrize("fallback,codigo", [(False, 0), (True, 1)])
def test_ia_informa_sucesso_ou_contingencia(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallback: bool,
    codigo: int,
) -> None:
    consultar = Mock(return_value=("Guia de teste", {"fallback_utilizado": fallback}))
    monkeypatch.setattr(planejamento, "obter_guia_destino_com_diagnostico", consultar)
    assert testar.main(["ia", "--destino", "Olinda, PE"]) == codigo
    consultar.assert_called_once_with("Olinda, PE")
    assert "Guia de teste" in capsys.readouterr().out


def test_demo_executa_todos_mesmo_com_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    guia = Mock(return_value=("Guia", {"fallback_utilizado": True}))
    clima = Mock(return_value={"temperatura": "N/D"})
    percurso = Mock(return_value={"modal": "alternativo"})
    monkeypatch.setattr(planejamento, "obter_guia_destino_com_diagnostico", guia)
    monkeypatch.setattr(testar, "obter_clima", clima)
    monkeypatch.setattr(testar, "obter_percurso", percurso)
    assert testar.main(["demo"]) == 1
    assert guia.call_count == 2
    clima.assert_called_once()
    percurso.assert_called_once()
