# Modelo de dados e contratos para o RAG

O projeto atual usa Flask, Firestore e uma busca por palavras sobre `tickets`, com uma coluna `resolution`. Na base historica, as solucoes estao nas **interacoes**. A modelagem abaixo conserva o ticket de origem e cria uma camada derivada de casos pesquisaveis, sem assumir que todo ticket fechado contem solucao validada.

Para correcoes e melhorias no software, [revisoes de codigo-fonte](modelagem-revisoes-codigo.md) acrescentam uma segunda trilha de evidencia ligada aos tickets e interacoes.

O [dataset RAG histórico em CSV](../../suporte-inteligente-arquivo-2026-10-31/docs/dataset_rag/README.md) materializou essas entidades durante a preparação. Ele e seus geradores foram arquivados fora do repositório em 31/10/2026. O fluxo atual usa o [importador do pacote JSON/JSONL](importacao-conhecimento.md); os registros de clientes permanecem locais.

## Entidades

| Entidade | Identidade e campos minimos | Relacao / regra |
| --- | --- | --- |
| `tickets` | `source_system`, `external_id`, cliente, assunto, descricao, status original/normalizado, tipo de manutencao, datas, equipe, ticket relacionado, versao da origem | Um registro por ticket da origem. `Não Procedente` fica fora do indice RAG. |
| `interacoes` | `external_id`, `ticket_id`, data, sequencia, tipo `A/D/F`, autor, destinatario, texto, flags originais | Muitos registros por ticket. Excluir da preparacao semantica os tres grupos definidos; preservar o motivo de exclusao na carga bruta controlada. |
| `knowledge_cases` | `case_id`, `ticket_id`, `problem_text`, `diagnosis`, `action`, `outcome`, `evidence_interaction_ids`, `evidence_state`, `review_state`, `embedding`, `embedding_model`, `content_hash`, `access_scope` | Um ticket pode ter varios casos. O vetor representa apenas o problema. Diagnostico, acao e resultado apontam para interacoes. |
| `case_links` | `case_id`, `related_case_id`, tipo e origem da relacao, revisao | Associacoes confirmadas ou candidatas; `ticket_relacionado` e tags geram pistas, nao equivalencia automatica. |
| `recommendations` | consulta/ticket atual, candidatos ordenados, resposta, fontes, versao dos modelos, latencia, estado | Registra a busca e a recomendacao; permite auditoria e feedback. |
| `feedback` | `recommendation_id`, avaliador, relevancia do caso, aplicabilidade da acao, utilidade, comentario, data | Avalia recuperacao e resposta separadamente. |
| `sync_runs` | origem, cursor, inicio/fim, contagens, erros, versao da regra | Permite carga inicial e sincronizacao incremental idempotente. |

No Firestore, `interacoes` pode ser subcolecao de `tickets/{id}`. `knowledge_cases` precisa de colecao propria para consulta vetorial. `case_links` pode ser subcolecao de casos se o volume permitir. A escolha final depende das consultas e regras de acesso, nao apenas da estrutura do CSV.

## Estados que nao devem ser confundidos

- **Ticket:** aberto, em andamento, fechado ou codigo ainda desconhecido (`C`).
- **Evidencia de solucao:** ausente, candidata, acao executada sem resultado, resultado observado, confirmada por revisao.
- **Indexacao:** pendente, indexada, desatualizada, erro, retirada.
- **Recomendacao:** casos encontrados, resposta gerada, evidencia insuficiente ou falha do modelo.

Uma interacao tipo `F` indica atualizacao de fechamento, nao necessariamente a solucao. Os campos `eh_padrao`, `eh_service` e `eh_duplicada` permanecem como dados de origem ate que o negocio confirme seu significado.

## Transformacoes e consultas

1. Importar tickets e interacoes por IDs de origem, sem duplicar no reprocessamento e sem inventar datas.
2. Aplicar as regras versionadas de exclusao. Manter o dado bruto em armazenamento controlado; registrar por que um item saiu da base semantica.
3. Construir `problem_text` com informacoes disponiveis na abertura. Extrair trechos candidatos de diagnostico, acao e resultado, sempre com IDs de interacao.
4. Revisor tecnico confirma, corrige ou rejeita a solucao. O sistema ainda pode mostrar casos candidatos, com essa condicao visivel.
5. Gerar o embedding do problema e guardar modelo, dimensao e hash do texto. Mudanca no problema ou na elegibilidade exige reindexacao.
6. Buscar por termos e vetores, aplicar permissao, excluir o proprio ticket e recuperar as interacoes fonte. A LLM resume apenas as evidencias acessiveis e cita seus IDs.
7. Guardar candidatos, resposta, modelo e feedback. Comparar busca atual, vetorial e combinada no mesmo conjunto de avaliacao.

## Contrato minimo entre front-end e back-end

- `POST /api/v2/recommendations`: aceita `ticket_id` ou `query` e devolve ID, estado, casos semelhantes e evidencias. A recomendacao gerada pode chegar na mesma resposta ou por consulta posterior, conforme a latencia medida.
- `GET /api/v2/recommendations/{id}`: devolve recomendacao, fontes e estado atualizado.
- Revisao de casos: leitura das interacoes em ordem, edicao de diagnostico/acao/resultado e decisao de confirmacao com autor e data.
- Feedback: relevancia do caso, aplicabilidade da acao e utilidade no atendimento, em campos separados.

O front-end deve mostrar o ticket e a interacao que fundamentam cada afirmacao, indicar quando a solucao e apenas candidata e manter os casos recuperados visiveis se a LLM falhar. O Flask aplica autorizacao antes de enviar qualquer interacao ao provedor do modelo.

## Primeira entrega implementavel

Comecar pela carga idempotente de tickets e interacoes, reconciliando as contagens do [EDA inicial arquivado](../../suporte-inteligente-arquivo-2026-10-31/eda/01_perfil_base_tratada.md). Em seguida, revisar um pequeno conjunto de casos para definir o criterio de solucao confirmada. So depois gerar embeddings e medir a recuperacao. O [escopo de entrega](escopo-rag.md) detalha as etapas seguintes.
