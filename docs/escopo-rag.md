# Escopo — tratamento de dados e RAG do Suporte Inteligente

**Base de análise:** repositório `rafaelwebber/suporte-inteligente`, commit `766919ca3c1159351637bbe789c4185cd606be9c` (17/10/2026).  
**Objetivo:** recomendar casos anteriores e suas ações registradas a partir do problema descrito em um ticket novo, com evidência rastreável até ticket e interação. O front-end e o back-end atuais podem ser adaptados para esse fluxo; seus contratos de tela e API não são requisitos fixos.

## 1. Situação atual

O projeto já dispõe de front-end em HTML/CSS/JavaScript, API Python/Flask, autenticação Firebase, Firestore, cadastro e importação de tickets por CSV, busca por palavras-chave, feedback e auditoria. Os pontos de extensão principais são [`api/services/ticket_service.py`](../api/services/ticket_service.py), [`api/services/suggestion_service.py`](../api/services/suggestion_service.py), [`api/routes/suggestions.py`](../api/routes/suggestions.py) e [`app.js`](../app.js).

| Tema | Implementado | Ajuste necessário para os dados reais |
| --- | --- | --- |
| Importação | Um CSV com título, descrição e coluna opcional `resolution`; ID externo evita duplicação no reimport. | Ingerir tickets **e interações** como entidades ligadas por `ticket`; registrar IDs de origem e mudanças incrementais. |
| Situação do ticket | Valores textuais como `resolved` e `open`. | Mapear explicitamente `F` = fechado, `N` = em andamento e `A` = aberto sem atualização. Tratar demais códigos como pendência de mapeamento. |
| Elegibilidade | `successful` exige ticket resolvido, `resolution` preenchida, sem reabertura e satisfação aceitável quando informada. | Excluir `tipo_manutencao = Não Procedente`. Não presumir solução por status F: procurar ação e resultado nas interações. Não inferir reabertura ou satisfação ausentes. |
| Busca | `keywords` + `array_contains_any`, limitada aos primeiros 500 candidatos, pontuação por termos comuns e votos como desempate. | Preservar como linha de base, acrescentar busca vetorial e comparar resultados. A limitação prévia a 500 candidatos pode ocultar casos pertinentes. |
| Resposta | Exibe o campo `resolution` do ticket. | Exibir recomendação, ticket fonte e IDs das interações que sustentam diagnóstico, ação e resultado; sinalizar ausência de evidência. |
| Segurança | O acesso passa pelo Flask; textos são mascarados por padrões de e-mail, CPF, CNPJ, cartão e telefone. | Aplicar a mesma autorização às novas interações e casos derivados; revisar dados enviados ao provedor do modelo. |

O importador atual substitui data de abertura ausente pela data da importação e data de resolução ausente pela abertura. A carga histórica RAG precisa preservar datas desconhecidas como desconhecidas: datas inventadas distorcem a avaliação temporal e a elegibilidade de soluções.

No commit analisado ainda não há entidade de interação, cliente de modelo, campo vetorial, índice vetorial ou testes de recuperação. Esses itens integram o escopo abaixo. A interface e o endpoint `/suggestions` existentes fornecem funções aproveitáveis, mas a experiência de recomendação e o contrato de API podem ser redesenhados.

## 2. Decisão arquitetural inicial

Manter **Flask e Firestore** como base do primeiro ciclo. O Firestore possui armazenamento e consulta de vetores, inclusive no cliente Python já compatível com a linguagem do back-end. Organizar o back-end em módulos de sincronização, preparação de casos, embeddings, recuperação, geração e avaliação. Um adaptador de modelos encapsula `embed(texto)`, `extrair_evidencias(interacoes)` e `gerar_recomendacao(problema, evidencias)`. A escolha do provedor fica configurável, e o nome/versão dos modelos fica gravado junto aos resultados.

```text
Software de tickets / CSV inicial
  -> sincronizador e validação -> Firestore: tickets + interações
  -> preparação assíncrona -> casos de conhecimento + vetor do problema

Front-end -> POST /api/v2/recommendations -> Flask
  -> busca por palavras + vetores -> casos anteriores autorizados
  -> interações de evidência -> LLM -> resposta estruturada
  -> validação de IDs e armazenamento da consulta -> telas de recomendação e feedback

Revisor técnico -> tela de revisão -> confirma/corrige casos extraídos
Administrador -> tela de sincronização -> acompanha erros e reprocessamentos
```

O texto vetorizado de cada caso deve descrever **o problema**: assunto e descrição do cliente, com contexto técnico disponível na abertura. Diagnóstico, ação e resultado ficam vinculados como conteúdo de resposta, não misturados ao texto da consulta. O mesmo ticket pode originar mais de um caso quando contém problemas distintos.

O contrato HTTP novo pode usar `POST /api/v2/recommendations`, com `ticket_id` ou `query` (um deles obrigatório), e `GET /api/v2/recommendations/{id}` para consultar o resultado. A resposta contém `id`, `status`, `cases` com `case_id`, `ticket_id`, `evidence_interaction_ids` e `evidence_status`, além de `recommendation` com `hypothesis`, `suggested_action`, `historical_result` e `citations`. Feedback e revisão ganham endpoints próprios. A rota `/suggestions` atual pode permanecer durante a migração da interface e ser retirada depois; não precisa ditar o novo desenho. Pontuação de similaridade é ordem de busca, não probabilidade de correção.

**Busca lexical:** usar a busca atual como comparador inicial. Se os testes mostrarem perda de termos técnicos exatos, avaliar busca textual dedicada. A pesquisa textual nativa documentada pelo Firebase exige Firestore Enterprise; por isso a edição contratada e o custo devem ser confirmados antes de depender dela. A busca híbrida pode ser composta no Flask a partir de duas listas de resultados.

**Modelos:** usar um modelo de embeddings pronto e uma LLM pronta; não há necessidade de treinar um modelo próprio neste escopo. Comparar pelo menos uma opção da mesma nuvem do Firestore (embeddings do Vertex AI) com outra opção autorizada pela empresa. `text-embedding-3-small`, por exemplo, produz 1.536 dimensões, dentro do limite de 2.048 do Firestore; `gemini-embedding-001` produz até 3.072 e deve ser configurado com saída menor para uso nesse índice. Indexação e consulta precisam usar o mesmo modelo e a mesma dimensão. A LLM recebe poucos casos selecionados e retorna JSON com campos definidos; o back-end verifica os IDs citados antes de apresentar a resposta.

## 3. Modelo de dados proposto

| Coleção / objeto | Conteúdo mínimo | Observação |
| --- | --- | --- |
| `tickets/{id}` | ID interno e externo, cliente, equipe, status original e normalizado, tipo de manutenção, assunto, descrição, ticket relacionado, datas de origem, hash/versão de sincronização. | Registro de origem preservado; `Não Procedente` identificado, não indexado. |
| `tickets/{id}/interacoes/{interacao_id}` | Tipo A/D/F, data, autor, destinatário usuário/grupo, texto, flags originais e motivo de exclusão quando houver. | Descartar da preparação para RAG as interações dirigidas a ENVIO DE ACEITE, BACKUPS e ASSESSORIA. Não interpretar `eh_padrao`, `eh_service` e `eh_duplicada` sem regra validada. |
| `knowledge_cases/{case_id}` | Ticket fonte, índice do problema dentro do ticket, `problem_text`, candidato de diagnóstico/ação/resultado, IDs das interações de evidência, nível de evidência, revisão técnica, metadados autorizados, embedding, modelo e hash do texto. | `case_id` estável permite reprocessamento sem duplicar. Guardar estados como `candidato`, `confirmado`, `sem_solucao_identificavel`. |
| `recommendations/{id}` | Consulta, ticket consultado se houver, IDs/rank dos candidatos, modelo/versão, resposta, evidências, custo/latência e feedback. | Nova coleção da experiência RAG; conservar `suggestion_queries` apenas para histórico até migrar métricas e feedback necessários. |

Cliente, processo, status, datas, ticket relacionado e autor são **metadados**. Assunto e descrição são o texto principal de busca por problema. Textos de interações são a fonte para solução e evidências. Números de erro, nomes de telas, equipamentos, Units e serviços devem ser preservados no texto técnico.

## 4. Entregas por etapa

### E1 — Contrato e carga histórica

- Definir correspondência entre os campos dos arquivos de origem e as coleções acima, inclusive IDs, chaves, tipos e datas.
- Importar tickets e interações de forma idempotente, com relatório de linhas lidas, aceitas, rejeitadas, faltantes e duplicadas.
- Aplicar o filtro Não Procedente e os três grupos de destinatário; manter a regra e sua versão registradas.
- Mapear status F/N/A e tipos de interação A/D/F sem deduzir que tipo F contém a solução.
- Separar estado de fechamento do ticket de estado da solução; adaptar a regra atual que exige `resolution` para fechar um ticket, pois o histórico importado guarda ações nas interações.
- Preservar datas de origem e valores ausentes; não preencher datas históricas com o instante da importação.

**Aceite:** contagens conciliadas com os arquivos, reimportação sem duplicatas e amostra de tickets com histórico completo e ordenado.

### E2 — Preparação de casos de conhecimento

- Para cada ticket elegível, montar `problem_text` com informações disponíveis na abertura.
- Propor automaticamente trechos de diagnóstico, ação executada e validação a partir das interações; registrar texto e IDs de origem.
- Distinguir ação planejada, ação executada, resultado confirmado e ausência de solução identificável. Encaminhamentos e fechamentos genéricos não são evidência técnica.
- Separar problemas múltiplos quando uma descrição/interação tratar de assuntos diferentes.
- Revisar amostra por técnico antes de elevar casos a `confirmado`.
- Casos ainda candidatos podem aparecer como histórico semelhante, mas a interface deve distingui-los de soluções confirmadas.

**Aceite:** toda solução exibida aponta para interação existente; casos incertos continuam identificados como candidatos.

### E3 — Indexação e atualização

- Gerar embeddings em lote para os casos históricos e criar índice vetorial no Firestore.
- Guardar modelo, dimensão, hash do texto e instante da indexação; recalcular quando o problema mudar.
- Retirar ou rebaixar do índice de soluções os tickets que se tornarem Não Procedentes, forem reabertos ou perderem evidência validada.
- Criar rotina de carga inicial, reprocessamento controlado, falhas/repetições e monitoramento da fila.

**Aceite:** um mesmo caso não gera vetores duplicados; mudança relevante atualiza o vetor; exclusão/invalidação remove o caso das recomendações.

### E4 — Recuperação e API

- Implementar `POST /api/v2/recommendations` para texto livre ou ID de ticket; disponibilizar `GET /api/v2/recommendations/{id}` e manter autenticação/autorização no Flask.
- Buscar por palavras e por vetor; combinar os rankings e recuperar as interações de evidência dos melhores casos.
- Aplicar permissões antes de compor a resposta. Excluir o próprio ticket; na avaliação histórica, excluir casos cuja solução ainda não existia na data da consulta.
- Retornar lista de casos com ticket, motivo de semelhança e IDs de evidência, mesmo se a LLM estiver indisponível.
- Versionar o contrato da API e migrar os consumidores da rota `/suggestions`; preservar somente as partes úteis da implementação atual.

**Aceite:** nenhuma sugestão vem de ticket Não Procedente, do próprio ticket, de conteúdo sem autorização ou, no teste temporal, de solução futura.

### E5 — Recomendação pela LLM

- Criar cliente de modelo no servidor com credencial em configuração segura, timeout, tentativas limitadas e registro de custo/latência.
- Fornecer à LLM somente problema atual e evidências recuperadas, exigindo saída estruturada: hipótese, ação registrada, resultado observado, ressalvas, tickets e interações fonte, ou `evidencia_insuficiente`.
- Validar formato e referências no Flask: IDs citados devem pertencer aos candidatos recuperados e acessíveis. Diferenciar observação histórica de ação sugerida.
- Persistir a recomendação e seu estado para que as telas exibam as fontes e recolham feedback.

**Aceite:** todas as referências exibidas são válidas e clicáveis; falha/timeout da LLM mantém disponível a lista de casos recuperados; ausência de evidência produz resposta explícita.

### E6 — Front-end de recomendação e revisão

- Adaptar a tela de consulta para aceitar um ticket existente ou uma descrição livre. Mostrar os estados `processando`, `concluido`, `sem_evidencia` e `erro` de forma compreensível.
- Exibir casos semelhantes com assunto, contexto, ação, resultado, estado de validação e links para ticket/interações originais. Destacar quando o caso é apenas candidato, sem solução confirmada.
- Criar fluxo de revisão técnica: ler interações em ordem, aceitar/corrigir/rejeitar diagnóstico, ação e resultado propostos; registrar responsável, data e versão.
- Adaptar feedback para distinguir `caso relevante`, `ação aplicável` e `ajudou no atendimento`; manter comentário opcional.
- Criar visão administrativa de sincronização/indexação com quantidade de registros, falhas, última execução e comando de reprocessamento autorizado.
- Aplicar permissões também às telas de evidência e revisão; o front-end consome somente a API do Flask.

**Aceite:** um técnico consegue pedir recomendação, conferir cada evidência e registrar feedback; um revisor consegue corrigir um caso; uma falha de modelo mantém os casos recuperados visíveis.

### E7 — Integração contínua com o software de tickets

- Implementar adaptador para API/eventos do software de tickets ou sincronização incremental por data de alteração, conforme a interface disponível.
- Usar ID de origem como chave de reconciliação; registrar cursor, tentativas, falhas e última sincronização bem-sucedida.
- Atualizações de status e novas interações disparam preparação e indexação novamente; exclusões e reaberturas invalidam conhecimento derivado.

**Aceite:** criar, atualizar e fechar um ticket no sistema de origem reflete-se no Firestore e no índice sem intervenção manual, inclusive após repetição do evento.

### E8 — Avaliação e liberação

- Usar os 31 tickets associados a problemas como conjunto inicial de avaliação, corrigindo a ausência do #6590 na base usada no piloto e os vínculos múltiplos dos #13571 e #14869.
- Ampliar a amostra antes da liberação geral para cobrir processos, clientes, problemas sem correspondência e tickets pouco documentados; os 31 são um piloto dirigido.
- Um técnico marca quais casos anteriores são úteis e quais interações contêm ação e resultado; incluir consultas sem correspondência.
- Comparar busca atual, vetorial e combinada usando acerto entre os cinco primeiros, cobertura de casos relevantes e posição do primeiro acerto.
- Avaliar separadamente a resposta da LLM: fidelidade às interações, utilidade da ação, referências válidas, respostas sem evidência, latência e custo.
- Congelar a amostra final de teste; durante a simulação, indexar apenas soluções concluídas antes da abertura da consulta.

**Aceite:** relatório reproduzível com métricas por abordagem e revisão técnica das recomendações. Definir a meta numérica de qualidade após medir a linha de base atual; não escolher o limiar sem dados.

### E9 — Segunda fonte: wiki e vínculos documentais

- Ingerir artigos da wiki como fonte separada dos tickets, preservando título, versão, trecho e ID do artigo.
- Usar `ticket_artigo`, `ticket_referencia` e `ticket_tag` quando disponíveis para ligar fontes por chave real, sem tratar um vínculo como prova de que o artigo resolveu o ticket.
- Indexar artigos e problemas de tickets em coleções identificáveis por `source_type`; a resposta deve dizer se a evidência veio de interação ou artigo.
- Avaliar cobertura e utilidade da wiki separadamente antes de incorporá-la à classificação de soluções históricas.

**Aceite:** toda recomendação documental informa artigo/trecho de origem e não se apresenta como correção confirmada de ticket.

## 5. Sequência de implementação

1. E1 e definição da política de acesso.
2. E2 em uma amostra; validar regras de extração com técnicos.
3. E3 e E4; comparar busca atual e vetorial antes da geração.
4. E5 e E6; entregar recomendação fundamentada, telas de evidência, revisão e feedback.
5. E7; substituir a carga manual pela integração incremental.
6. E8 desde o início, repetindo a medição a cada etapa.
7. E9 após estabilizar a busca por tickets e medir o ganho trazido pela wiki.

## 6. Decisões pendentes para implementação

1. Qual API ou mecanismo de eventos o software de tickets oferece e quais são seus identificadores estáveis?
2. Qual edição do Firestore está contratada? A busca vetorial funciona no Firestore; busca textual nativa documentada exige Enterprise.
3. Quem pode ver interações internas e casos de outros clientes/equipes? A busca deve filtrar antes de enviar evidências à LLM.
4. Qual provedor de embeddings e LLM pode receber os dados após mascaramento? O modelo escolhido define dimensão, custo e política de dados.
5. O que a equipe considera solução confirmada quando o histórico não contém confirmação explícita do cliente?

## 7. Fora do primeiro ciclo

Treinar ou ajustar uma LLM própria, executar ações corretivas automaticamente, encerrar tickets sem validação humana e migrar todo o banco para outro produto.

## Referências técnicas

- [Busca vetorial no Firestore](https://firebase.google.com/docs/firestore/vector-search) — armazenamento, índices, consulta e limite de 2.048 dimensões.
- [Busca textual no Firestore Enterprise](https://firebase.google.com/docs/firestore/enterprise/text-search) — requisito de edição e índice textual.
- [Embeddings da OpenAI](https://developers.openai.com/api/docs/guides/embeddings) — dimensões e geração de vetores.
- [Embeddings do Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings) — alternativa integrada ao Google Cloud e configuração da dimensão.
- [Saídas estruturadas da OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs) — contrato JSON para a recomendação.
- [Avaliação de recuperação para RAG](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-information-retrieval) — precisão, cobertura e posição dos resultados.
- [Preparação e busca híbrida para RAG](https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview) — preparação de conteúdo e combinação de palavras/vetores.
