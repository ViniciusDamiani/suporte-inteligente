# Organização da base de conhecimento

O pacote preparado está em [pacote_importacao/v1_2026-10-30](pacote_importacao/v1_2026-10-30/LEIA_PRIMEIRO.md).

Comece pelo [catálogo de importação](CATALOGO_IMPORTACAO.json), que aponta para a versão e seu manifesto de integridade. A [organização do pacote](pacote_importacao/v1_2026-10-30/LEIA_PRIMEIRO.md) explica cada segmento e a atualização.

Os CSVs de origem, controles, o diretório `03_banco_dados` e `_historico` foram arquivados em [DataSetBase de preparação](../../suporte-inteligente-arquivo-2026-10-31/DataSetBase/), fora do repositório, na limpeza de 31/10/2026. O pacote é uma versão derivada: editar a origem não o atualiza automaticamente. Uma nova carga deve gerar e validar outra versão, preservando a anterior.

Não carregar os CSVs de origem junto com o pacote. O pacote versionado foi preservado integralmente, inclusive seus hashes e documentos históricos; menções nele às antigas localizações devem ser interpretadas conforme esta mudança. Os estados de revisão técnica foram preservados. A importação local do item 3 foi executada; nenhuma solução foi homologada automaticamente e nenhuma RAG/LLM foi executada.
