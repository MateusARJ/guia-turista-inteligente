# Guia de testes e demonstrações

Execute os comandos deste guia no PowerShell, na raiz do projeto.

## 1. Preparar o ambiente

O ambiente `.venv` já foi criado neste projeto. Ative-o e instale as dependências:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Em uma cópia nova do projeto, crie o ambiente antes da ativação:

```powershell
python -m venv .venv
```

Se não quiser ativar o ambiente, execute os módulos pelo Python da `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.testar fallback
```

No VS Code, selecione `.venv\Scripts\python.exe` em **Python: Select Interpreter**.

## 2. Ferramentas utilizadas

| Ferramenta | Para que usamos |
| --- | --- |
| pytest | Executar testes automatizados e mostrar os casos aprovados ou com falha |
| Taskipy | Oferecer atalhos `task ...`, definidos em `pyproject.toml` |
| Fixtures e `monkeypatch` do pytest | Preparar os testes e substituir configurações temporariamente |
| `unittest.mock.Mock` e `patch` | Simular chamadas e respostas, sem depender das APIs reais |
| `httpx.MockTransport` | Simular respostas HTTP e conferir URLs, parâmetros e timeouts |
| Ruff | Verificar problemas de estilo e boas práticas no código |
| Mypy | Verificar os tipos declarados no código |
| python-dotenv | Carregar o `.env` para as demonstrações que precisam de configuração local |
| google-genai e HTTPX | Consultar Gemini, Open-Meteo e OSRM nas demonstrações reais |

As dependências estão em `requirements.txt`. `unittest.mock` faz parte do Python;
ele continua sendo usado para simulações, mas quem executa a suíte é o pytest.

## 3. Diferença entre `tests/` e `scripts/`

O nome da pasta de demonstrações no projeto é **`scripts/`**, no plural.

```text
tests/
├── conftest.py
├── test_planejamento.py
├── test_services_aluno2.py
└── test_atalhos.py

scripts/
├── __init__.py
└── testar.py

pyproject.toml
```

### `tests/`: testes automatizados

Contém verificações que comparam o resultado do código com o resultado esperado.
Esses testes simulam os serviços externos e não precisam de uma chave real nem
de internet para executar.

| Arquivo | Responsabilidade |
| --- | --- |
| `conftest.py` | Fixture automática que substitui a chave usada por planejamento e bloqueia o transporte HTTP real do HTTPX |
| `test_planejamento.py` | Limpeza do texto, sucesso da IA, contingências, diagnóstico, timeout e wrapper |
| `test_services_aluno2.py` | Clima, percurso, unidades, coordenadas, arredondamento e falhas dos provedores |
| `test_atalhos.py` | Saída das demonstrações, preservação da chave e códigos de retorno, com serviços simulados |
| `README.md` | Detalhes e histórico das validações |

Casos parametrizados aparecem como testes separados no relatório. Na última
validação, **47 casos passaram**. Esse número pode aumentar conforme a suíte evolui.

### `scripts/`: demonstrações manuais

`scripts/testar.py` permite ver o texto do guia, os dados retornados pelos serviços,
o diagnóstico e o tempo gasto. Ele reutiliza as funções de `planejamento.py` e
`services.py`.

O comando de fallback é local. Os comandos de IA, clima e percurso acessam os
provedores reais; portanto, podem depender da rede, da disponibilidade das APIs
e, no caso do Gemini, da chave e da cota.

Execute esse arquivo como módulo a partir da raiz:

```powershell
python -m scripts.testar fallback
```

Os atalhos do Taskipy já usam essa forma de execução.

## 4. Rodar todos os testes de uma vez

Com a `.venv` ativada:

```powershell
task test
```

Esse comando executa `python -m pytest`. Para listar todos os atalhos disponíveis:

```powershell
task --list
```

## 5. Selecionar testes e ajustar a saída

| Comando | O que executa |
| --- | --- |
| `task test-ia` | Testes automatizados de planejamento |
| `task test-servicos` | Testes automatizados de clima e percurso |
| `python -m pytest tests/test_atalhos.py` | Testes dos comandos de demonstração |
| `task test -v` | Todos os casos com seus nomes detalhados |
| `task test -q` | Relatório resumido |
| `task test -x` | Para na primeira falha |
| `task test -k timeout` | Seleciona testes cujo nome contém `timeout` |
| `task test --collect-only -q` | Lista os casos encontrados sem executá-los |

O pytest procura os testes em `tests/`, conforme `pyproject.toml`.

## 6. Demonstrar o fallback

```powershell
task fallback
task fallback --destino "Natal, RN"
```

Esse comando simula uma chave ausente apenas durante a chamada, sem editar o
`.env` e sem consultar o Gemini. A configuração anterior é restaurada ao terminar.

O resultado esperado é o guia de contingência e um diagnóstico com:

```json
{
  "status": "fallback",
  "modelo": "gemini-3.6-flash",
  "fallback_utilizado": true,
  "motivo": "chave_ausente"
}
```

Para verificar automaticamente outros cenários de contingência, como chave
inválida, cota, timeout e falha de rede, execute `task test-ia`.

## 7. Ver uma resposta real da IA

Preencha o arquivo `.env` local:

```dotenv
GEMINI_API_KEY=SUA_CHAVE_REAL
GEMINI_TIMEOUT_SEGUNDOS=60
```

O `.env` é ignorado pelo Git. O `.env.example` deve conter somente exemplos,
sem credenciais reais. Variáveis definidas no terminal têm prioridade sobre o
arquivo; para remover uma chave antiga desse terminal e usar a do `.env`:

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
```

Execute:

```powershell
task ia
task ia --destino "Olinda, PE"
```

O comando mostra o texto e o diagnóstico. `status: sucesso` e
`fallback_utilizado: false` indicam que o guia veio da IA. Se houver contingência,
o campo `motivo` informa a categoria da falha.

A espera padrão é de 60 segundos, configurável até 120 segundos. O SDK usa
timeout HTTP mínimo de 10 segundos. Para reproduzir o limite original da issue,
defina `GEMINI_TIMEOUT_SEGUNDOS=6`; nesse caso o chamador pode retornar antes
de a requisição HTTP terminar. Aumentar o timeout não garante sucesso do provedor.

## 8. Consultar clima e percurso reais

Clima em Recife, usando as coordenadas padrão:

```powershell
task clima
```

Clima em coordenadas escolhidas:

```powershell
task clima --lat -8.05 --lon -34.9
```

Rota padrão de Recife a João Pessoa:

```powershell
task percurso
```

Consulta entre Recife e Fernando de Noronha, para observar o tratamento de uma
viagem sem rota rodoviária direta:

```powershell
task percurso --lat -8.05 --lon -34.9 --lat-d -3.85 --lon-d -32.42
```

A resposta real depende do OSRM. O caso `NoRoute` também é coberto por um teste
simulado e determinístico em `task test-servicos`.

| Opção | Uso | Padrão |
| --- | --- | --- |
| `--destino` | Texto usado pela IA e pelo guia de contingência | `Recife, PE` |
| `--lat` | Latitude do clima ou da origem da rota | `-8.05` |
| `--lon` | Longitude do clima ou da origem da rota | `-34.9` |
| `--lat-d` | Latitude de chegada da rota | `-7.12` |
| `--lon-d` | Longitude de chegada da rota | `-34.86` |

Alterar `--destino` não altera as coordenadas do clima ou do percurso. Os comandos
não fazem geocodificação do nome da cidade. O clima usa timeout de 4 segundos;
o percurso usa 6 segundos.

## 9. Executar todas as demonstrações

```powershell
task demo
```

Executa fallback, IA, clima e percurso, nessa ordem. Esse comando acessa APIs
reais e pode consumir cota do Gemini. Se um serviço retornar contingência,
as demais demonstrações continuam.

Use **`task test`** para verificar automaticamente o código e **`task demo`**
para observar as respostas dos serviços no terminal.

## 10. Verificar estilo e tipos

```powershell
task lint
task tipos
```

São equivalentes a:

```powershell
python -m ruff check .
python -m mypy .
```

Essas verificações analisam o projeto inteiro. Ainda existem pendências
preexistentes em `app.py` e nas funções do Aluno 1 em `services.py`.
Uma suíte pytest aprovada não significa que Ruff e Mypy também estejam aprovados.
Os comandos mostram essas pendências sem ocultá-las ou apagar código.

## 11. Interpretar os resultados

| Resultado | Significado |
| --- | --- |
| `passed` no pytest | A verificação automatizada passou |
| `failed` no pytest | O comportamento observado divergiu do esperado |
| `error` no pytest | Ocorreu um erro de coleta ou preparação de um teste |
| IA com `fallback_utilizado: false` | A chamada retornou um guia aceito pelo módulo |
| IA com `fallback_utilizado: true` | O módulo retornou contingência; consulte `motivo` |
| Clima com `N/D` | Não foi possível obter dados válidos |
| Percurso com `Sem rota direta` | Não foi possível obter uma rota válida |

As demonstrações retornam código de saída **0** quando têm o resultado esperado.
`task fallback` retorna 0 porque a contingência é intencional. `task ia`,
`task clima` e `task percurso` retornam **1** quando caem na contingência;
`task demo` retorna 1 se qualquer serviço real cair nela.

Para ver o código do último comando no PowerShell:

```powershell
$LASTEXITCODE
```

Para consultar a ajuda dos parâmetros:

```powershell
python -m scripts.testar --help
```

Os testes atuais verificam os módulos e os comandos descritos aqui. A demonstração
na interface Flask ainda depende das rotas pendentes em `app.py`.
