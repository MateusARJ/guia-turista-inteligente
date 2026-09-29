"""Persistência e endpoint JSON com armazenamento temporário, sem APIs reais."""

import json
from pathlib import Path

import pytest

import app as backend


@pytest.fixture
def arquivo_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    arquivo = tmp_path / "viagens.json"
    monkeypatch.setattr(backend, "VIAGENS_FILE", arquivo)
    monkeypatch.setattr(backend, "viagens_visitante_memoria", {})
    return arquivo


def test_persistencia_separa_usuarios_e_atualiza_totais(arquivo_json: Path) -> None:
    backend.adicionar_viagem_usuario("usuario1", {"id": "1", "destino": "Recife"})
    backend.adicionar_viagem_usuario("usuario2", {"id": "2", "destino": "Olinda"})
    dados = json.loads(arquivo_json.read_text(encoding="utf-8"))
    assert dados["total_usuarios"] == 2
    assert dados["total_roteiros"] == 2
    assert backend.obter_viagens_usuario("usuario1") == [{"id": "1", "destino": "Recife"}]
    assert backend.obter_viagens_usuario("usuario2") == [{"id": "2", "destino": "Olinda"}]


def test_visitante_nao_grava_no_arquivo(arquivo_json: Path) -> None:
    backend.adicionar_viagem_usuario("visitante_a", {"id": "a"})
    backend.adicionar_viagem_usuario("visitante_b", {"id": "b"})
    assert backend.obter_viagens_usuario("visitante_a") == [{"id": "a"}]
    assert backend.obter_viagens_usuario("visitante_b") == [{"id": "b"}]
    assert not arquivo_json.exists()


def test_arquivo_corrompido_retorna_estrutura_padrao(arquivo_json: Path) -> None:
    arquivo_json.write_text("{json invalido", encoding="utf-8")
    dados = backend.carregar_dados_viagens_json()
    assert dados["usuarios"] == {}
    assert dados["total_roteiros"] == 0
    assert dados["versao_schema"] == "1.0"


def test_endpoint_json_preserva_hierarquia_e_diagnostico(arquivo_json: Path) -> None:
    viagem = {"id": "1", "diagnostico_ia": {"status": "fallback", "motivo": "timeout"}}
    backend.adicionar_viagem_usuario("usuario1", viagem)
    with backend.app.test_client() as client:
        resposta = client.get("/viagens/json")
    assert resposta.status_code == 200
    assert resposta.mimetype == "application/json"
    dados = resposta.get_json()
    assert dados["usuarios"]["usuario1"]["roteiros"] == [viagem]
    assert dados["total_roteiros"] == 1
    assert "provedores" in dados
    assert "atualizado_em" in dados
