# Documentacao de conhecimento a partir de tickets e revisoes

O GitLab serve como **fonte de preparacao**. A consulta de suporte usa documentos ja preparados e aprovados no banco da plataforma; ela nao consulta o GitLab nem analisa diffs em tempo real.

Para novos desenvolvimentos, uma [interacao tecnica padronizada no ticket](padrao-interacao-desenvolvimento.md) pode registrar a mudanca e o teste no momento em que ocorrem. Ela reduz a dependencia de reconstruir a explicacao a partir do diff.

```text
Carga historica / nova carga autorizada
  Tickets + interacoes + commits/diffs por cliente
                 -> vinculos e interpretacao
                 -> revisao tecnica
                 -> ficha de conhecimento versionada + indice de busca

Atendimento
  Problema atual -> busca nas fichas publicadas -> casos e recomendacao com fontes
```

## Ficha de conhecimento

Uma ficha corresponde a um problema ou melhoria identificavel, nao necessariamente a um ticket inteiro. Campos minimos:

| Grupo | Campos |
| --- | --- |
| Identidade | `case_id`, `client_id`, ticket(s), produto/modulo, versao da ficha, estado (`rascunho`, `revisada`, `publicada`, `substituida`) |
| Problema | assunto, descricao tecnica do sintoma ou pedido, contexto, termos/codigos preservados |
| Interpretacao | causa identificada ou `desconhecida`, mudanca implementada, arquivos/componentes afetados, limites da conclusao |
| Resultado | teste realizado, resultado observado, versao implantada se comprovada, estado de validacao |
| Rastreabilidade | IDs das interacoes, repositorio, SHA(s), MR, arquivos/linhas ou referencia ao diff, data da analise, autor/revisor |
| Operacao | texto de busca, embedding, modelo/versao, hash do conteudo, nivel de acesso, data de publicacao |

Separar **o que o ticket pediu**, **o que o diff mostra** e **o que foi validado**. Um commit nao prova sozinho que o cliente recebeu a mudanca. Quando uma informacao nao estiver comprovada, guardar `desconhecido` em vez de preencher por inferencia.

## Documentacao atual: carga inicial

1. Cadastrar cada repositorio sob seu cliente e importar os tickets/interacoes existentes.
2. Obter uma exportacao controlada dos commits e diffs (GitLab de leitura ou copia local com `.git`). Extrair IDs de ticket das mensagens e conferir o cliente dos dois lados.
3. Gerar rascunhos das fichas com os trechos pertinentes de interacoes e codigo. Ignorar ruído de arquivos gerados, binarios e mudancas apenas de formatacao na interpretacao tecnica.
4. Revisor tecnico confirma a mudanca, a aplicabilidade e o resultado. Publicar apenas fichas com fontes verificaveis; casos incompletos continuam rotulados como candidatos.
5. Armazenar fichas e metadados de origem em colecoes privadas do Firestore; gerar embeddings do texto do problema. O repositorio publico da plataforma guarda somente esquema, codigo de processamento e exemplos ficticios.

## Documentacao futura: atualizacao

Novos commits/tickets entram por **lotes**, fora da consulta do atendente. O modo inicial pode ser exportacao ou clone local periodico e comando administrativo de importacao. Se a empresa quiser automatizar depois, um processo de fundo pode receber evento do GitLab ou consultar apenas revisoes novas; a API de recomendacao continua lendo somente a base interna.

Cada importacao registra `source_repository_id`, ultimo SHA/cursor, data, contagens, erros e versao da regra. Repetir o mesmo lote nao duplica fichas. Mudanca de ticket, interacao, commit associado ou validacao cria nova versao da ficha e atualiza o indice. A versao anterior permanece rastreavel. Uma ficha publicada pode ser substituida quando a correção deixar de valer para uma versao do produto.

## Uso na plataforma

O front-end consulta a API Flask. O back-end recupera fichas autorizadas por cliente/equipe e retorna problema semelhante, mudanca documentada, resultado observado e links/IDs das fontes. A LLM, quando habilitada, usa apenas as fichas e evidencias recuperadas para redigir a recomendacao. A indisponibilidade do GitLab durante o atendimento nao interrompe a busca.

E preciso distinguir a visao de suporte da visao tecnica: a primeira mostra sintomas, acao recomendada e resultado; a segunda permite abrir evidencias de commit, arquivo e interacao conforme a permissao do usuario. Codigo-fonte completo permanece no repositorio do cliente ou em armazenamento privado autorizado.

## Primeira entrega

Produzir manualmente algumas fichas a partir de tickets com commits explicitos, revisar com um tecnico e medir se o resultado responde a duas perguntas: **"qual problema ocorreu?"** e **"o que foi alterado e validado?"**. Depois implementar o importador em lote e a tela de revisao. O RAG usa as fichas publicadas assim que estiverem no banco.

## Referencias

- [API de commits e diffs do GitLab](https://docs.gitlab.com/api/commits/)
- [Eventos de push e merge request do GitLab](https://docs.gitlab.com/user/project/integrations/webhook_events/)
