# Organização do repositório

Revisão de 31/10/2026. A limpeza considerou os arquivos registrados no Git, os
caminhos carregados pela aplicação e pelo importador e os testes do item 3.

## Pastas mantidas

| Pasta | Uso | Situação no Git durante a limpeza |
| --- | --- | --- |
| `api/` | Aplicação Flask, autenticação, tickets, busca atual e auditoria. | Versionada. |
| `models/` | Regras do Firestore. | Versionada. |
| `knowledge_import/` | Importação e validação do pacote de conhecimento. | Nova, ainda sem commit. |
| `knowledge_search/` | Índice SQLite, embeddings locais, busca híbrida e geração opcional com Gemini do item 6. | Nova, ainda sem commit. |
| `tests/` | Testes do importador, triagem e avaliador. | Nova, ainda sem commit. |
| `evaluation/` | Cenários sintéticos versionados, avaliação de busca/resposta e geração de relatórios do item 5. | Nova, ainda sem commit. |
| `triage/` | Motor, modelos JSON, interpretação de anexos e sessões do item 4, adicionado em 01/11/2026. | Nova, ainda sem commit. |
| `DataSetBase/` | Catálogo, pacote JSON/JSONL ativo e política de uso dos tickets. | Local, ainda sem commit. |
| `instance/` | Banco SQLite e relatórios das cargas já realizadas. | Ignorada pelo Git. |
| `docs/` | Instruções de uso, modelagem e decisões para as próximas etapas. | Nova, ainda sem commit. |

Os arquivos da interface, `run.py`, `requirements.txt`, `.gitignore`, `README.md`
e a pasta `.git` foram mantidos. Os 28 arquivos já versionados foram preservados
durante a movimentação. O README foi atualizado depois para documentar a organização.

## Materiais arquivados

Foram retirados da árvore ativa 83 arquivos (370,81 MiB), preservados em:

`C:\Projeto\suporte-inteligente-arquivo-2026-10-31`

| Caminho anterior | Conteúdo e motivo |
| --- | --- |
| `dataset/` | Geradores antigos de planilha/CSV e snapshots auxiliares. Não são chamados pela aplicação nem pelo importador JSON atual. |
| `eda/` | Levantamento exploratório inicial. Referência histórica. |
| `exportação tickets/` | Sete exportações brutas, já representadas no pacote preparado. |
| `plc/` | Backup de projeto PLC e imagem de comparação. Material de análise, sem carregamento pela aplicação. |
| `docs/dataset_rag/` | Datasets intermediários, relatórios e vistas anteriores ao pacote JSON. |
| `DataSetBase/_historico/` | Cópia anterior da classificação de tickets. |
| `DataSetBase/03_banco_dados/` | Fontes de preparação de banco; as referências de importação estão no próprio pacote. |
| CSVs e controles JSON da raiz de `DataSetBase/` | Origens editáveis e controles da preparação; não participam da carga definida pelo catálogo. |

Esses arquivos não eram versionados. A movimentação preservou os caminhos
relativos dentro do arquivo externo, e os SHA-256 dos 83 arquivos foram conferidos
após a transferência. O inventário está em
[manifesto-limpeza.json](../../suporte-inteligente-arquivo-2026-10-31/manifesto-limpeza.json).

O pacote ativo `DataSetBase/pacote_importacao/v1_2026-10-30/` foi mantido integralmente:
documentação e arquivos de controle também fazem parte de sua rastreabilidade.
Seus documentos internos conservam a descrição da organização original.

## Novas cargas e recuperação

Para importar, usar `DataSetBase/CATALOGO_IMPORTACAO.json` conforme o
[guia do item 3](importacao-conhecimento.md). Para preparar novas exportações,
as origens e ferramentas antigas continuam disponíveis no arquivo externo.

Para recuperar um material, copiar seu caminho relativo do arquivo externo para
a mesma posição no repositório, verificando antes se já existe conteúdo no destino.
O arquivo externo deve acompanhar o backup local das fontes de conhecimento.

A limpeza não criou commits. O código novo do item 3 continua disponível para
revisão e versionamento; o banco e os dados históricos não devem ser confundidos
com código de aplicação.

Em 01/11/2026, o item 4 acrescentou `triagem.html`, `triagem.js`, `triagem.css`,
`api/routes/triage.py`, os testes da triagem e o [guia de uso](triagem.md).
O ambiente Python local `.venv/` foi preparado para executar e verificar a
aplicação; ele permanece ignorado pelo Git. As sessões usam `instance/triage.sqlite3`.

O item 5 acrescentou o [guia de avaliação](avaliacao.md) em 01/11/2026. Relatórios
de cada execução ficam em uma pasta nova de `instance/evaluation/`; os cenários
e o corpus de desenvolvimento ficam em `evaluation/data/`. A avaliação utiliza
memória e bancos temporários, sem escrever nos bancos do projeto.

O item 6 acrescentou `acervo.html`, `acervo.js`, `acervo.css`, a API autenticada
`api/routes/knowledge.py`, `evaluation/hybrid.py` e o [guia da busca local](busca-local.md).
O índice fica em `instance/search.sqlite3`, separado da origem, e os pesos do
modelo em `instance/models/`. Esses artefatos locais permanecem ignorados pelo Git.
