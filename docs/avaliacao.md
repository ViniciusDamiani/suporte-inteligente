# Avaliação de busca e resposta — item 5

O comando `python -m evaluation` executa uma suíte local e produz relatórios de
qualidade. Ele chama a busca real de tickets e o motor real de triagem, usando
14 tickets sintéticos em memória e sessões em SQLite temporário. Não precisa
iniciar o servidor, configurar credenciais ou acessar o Firebase. Não importa
dados nem altera tickets e atendimentos existentes.

## Executar no Windows

Na raiz `C:\Projeto\suporte-inteligente`, com as dependências já instaladas:

```powershell
.\.venv\Scripts\python.exe -m evaluation
```

O terminal informa a pasta criada em `instance/evaluation/`, com data e hora UTC.
Abra `relatorio.html` no navegador. A mesma execução gera:

- `relatorio.json`: resultados, expectativas, verificações, métricas e hashes;
- `relatorio.html`: leitura das falhas, respostas, evidências e limites;
- `revisao-humana.csv`: campos em branco para registrar a revisão técnica.

É possível escolher uma pasta nova e comparar com uma execução anterior:

```powershell
.\.venv\Scripts\python.exe -m evaluation --saida instance\evaluation\rodada-002 --comparar instance\evaluation\2026-11-01-inicial\relatorio.json
```

A pasta de saída não pode existir: o histórico nunca é sobrescrito. Relatórios
ficam em `instance/`, ignorada pelo Git. Os cenários e o avaliador pertencem ao
código do projeto. O HTML funciona sem conexão e não carrega recursos externos.

O código de saída permite usar o comando numa rotina de verificação:

| Código | Significado |
| --- | --- |
| `0` | Todos os cenários e metas desta suíte foram atendidos. |
| `1` | Execução concluída com falhas de qualidade ou erros de execução em cenários. Consulte o relatório. |
| `2` | Configuração, contrato, arquivo ou saída inválidos; execução não concluída. |

## O que está sendo medido

Os arquivos de entrada são `evaluation/data/scenarios.v1.json` e
`evaluation/data/corpus.v1.json`. A versão inicial contém 35 cenários:

| Grupo | Quantidade | Cobertura |
| --- | --- | --- |
| Busca | 15 | Sintomas, mensagens literais, acentos, plurais, código de erro, múltiplas fontes pertinentes, ausência de cobertura, saudação, exclusão de tickets sem êxito e paráfrases. |
| Triagem e resposta | 20 | Coleta e lacunas, perguntas condicionais, origem/data/Unit dos anexos, divergência entre relato e log, escrita ignorada/com erro, reaproveitamento de anexos, instruções no arquivo, evidência indisponível, encaminhamento e referências de linha/JSON. |

Os cenários de triagem foram selecionados a partir do contrato do piloto
`triage/models/mistura_destino.v1.json` e dos limites documentados no item 4.
Todos os relatos, instalações e logs usados nos testes são sintéticos. Nenhuma
ocorrência histórica é copiada como resposta de um novo atendimento.

A busca usa `api/services/suggestion_service.py`, incluindo a normalização,
classificação de êxito e ordenação efetivas da aplicação. O adaptador em memória
simula a consulta por palavras e o registro local da consulta; não testa índices,
latência, disponibilidade, autenticação ou regras do Firestore. A ordem dos
tickets sintéticos é fixa e desempates podem diferir da base de produção.

A triagem usa `SessionStore` com banco temporário por cenário. Cada passo passa
pelo mesmo serviço de persistência utilizado pela API. As referências e a
ausência de diagnóstico confirmado são verificadas no início, após cada passo
e no resultado final. Há também expectativas intermediárias explícitas, como
verificar uma evidência antes e depois da correção do cliente.

A resposta atual é a solução extraída de um ticket e as mensagens determinísticas
da triagem. Os testes verificam fidelidade à solução, referências existentes,
trechos rastreáveis, correlação das evidências, indícios com fonte e mensagens
que devem aparecer ou não aparecer. Isso não mede a qualidade de uma resposta
por LLM nem substitui o julgamento de um especialista.

## Métricas e critérios

Para cada consulta, `relevant_ids` define os tickets pertinentes; `forbidden_ids`
define os que não devem aparecer. `top_k` limita a posição aceita para os
pertinentes (entre 1 e 5). A consulta negativa tem `relevant_ids: []` e deve retornar
nenhum ticket. Um status HTTP incorreto continua sendo falha, mesmo sem resultados.

| Métrica | Cálculo |
| --- | --- |
| Precision@1/3/5 | Quantidade de IDs pertinentes distintos entre os primeiros k, dividida por k. Retornar menos de k não reduz o denominador. |
| Recall@1/3/5 | Quantidade de pertinentes encontrados entre os primeiros k, dividida pelo total de pertinentes rotulados para a consulta. |
| Hit@1/3/5 | Um se encontrou ao menos um pertinente; zero em caso contrário. |
| Reciprocal rank / MRR | Inverso da posição do primeiro pertinente; zero se ausente. MRR é a média dessas contribuições. |
| Empty correct | Um se uma consulta negativa não retornou tickets e executou sem erro; zero em caso contrário. |
| Taxa de triagem | Cenários de triagem que atenderam todas as verificações, divididos pelo total de cenários de triagem. |
| Taxa de resposta | Cenários que atenderam todas as verificações de fidelidade, referências e mensagens, divididos pelo total de cenários. |

As médias são por consulta, sem ponderação por volume de produção. Recall, Hit e
MRR excluem consultas negativas; `empty_correct` considera somente negativas.
O relatório mostra o número de cenários de cada média. Exceções nunca são
descartadas nem contadas como abstenção correta. Uma resposta fiel pode trazer
um ticket pouco pertinente: por isso fidelidade e recuperação são medidas
separadamente. Nas consultas sem resultados, a fidelidade da solução é uma
verificação vazia; o acerto da abstenção e a recuperação continuam sendo avaliados.

Metas iniciais de desenvolvimento, declaradas no JSON antes da medição:

- Recall@5 de pelo menos 90%;
- MRR de pelo menos 80%;
- abstenção correta em 100% das consultas negativas;
- 100% dos cenários de triagem e das verificações de resposta atendidos.

A aprovação automática exige também todos os cenários individuais atendidos.
Esses critérios são uma referência de desenvolvimento; ainda precisam de revisão
para se tornarem critérios de homologação. Os 14 tickets e 35 cenários não são
uma amostra estatística do uso real. A precisão em k=5 tende a ser baixa quando
há somente um ticket pertinente rotulado por consulta; ela não equivale à
porcentagem de atendimentos resolvidos.

## Primeira medição — 01/11/2026

| Resultado | Valor |
| --- | --- |
| Cenários atendidos | 33 de 35 |
| Busca | 13 de 15 |
| Triagem | 20 de 20 |
| Erros de execução | 0 |
| Recall@5 | 83,3% em 12 consultas positivas — abaixo da meta de 90% |
| MRR | 83,3% em 12 consultas positivas |
| Abstenção correta | 100% em 3 consultas negativas |
| Verificações de resposta | 100% em 35 cenários, dentro do escopo acima |

Falharam `B13` ("transportador imóvel") e `B14` ("conectividade controlador").
A busca lexical não encontrou os tickets rotulados, pois não há palavras
normalizadas em comum. O relatório preserva essas falhas; as expectativas não
foram reduzidas para aprovar a implementação. Isso é um resultado de qualidade,
não uma falha de execução do comando. O código de saída esperado dessa primeira
medição é `1`.

Relatório local: `instance/evaluation/2026-11-01-inicial/relatorio.html`.

## Revisar e ampliar os cenários

1. Um responsável técnico deve validar a pertinência dos tickets, as perguntas,
   as evidências e as mensagens esperadas, preenchendo `revisao-humana.csv`.
2. Corrigir os rótulos no JSON somente quando houver justificativa registrada;
   nunca remover uma expectativa apenas porque a aplicação falhou.
3. Incrementar `version` ao mudar cenários, metas ou rótulos. `schema_version`
   identifica o contrato do avaliador, não a rodada de revisão.
4. Acrescentar consultas positivas e negativas, casos ambíguos e casos de outras
   famílias de incidente. Manter IDs únicos e fontes pertinentes identificadas.
5. Para a base real, separar casos usados no desenvolvimento dos usados na
   homologação, observar a data das fontes e revisar confidencialidade antes de
   incluir qualquer conteúdo nos arquivos e relatórios.

Os parâmetros `--suite caminho.json` e `--corpus caminho.json` permitem escolher
outro conjunto com o mesmo contrato. Campos desconhecidos, IDs duplicados,
referências inexistentes, metas inválidas e expectativas vazias de triagem são
rejeitados. Preparações comuns ficam em `setups`; `steps` contém respostas,
anexos textuais, indicação de indisponibilidade e encaminhamento. Anexos de
avaliação são textos UTF-8 embutidos no JSON.

Os relatórios registram os hashes dos dados e do código Python, os modelos da
triagem, a versão do Python e os parâmetros relevantes da busca. A comparação
só calcula deltas quando os arquivos de cenários/corpus e a configuração são
iguais. Mudanças no código podem então mostrar regressões ou melhorias. Se os
rótulos mudarem, a comparação indica incompatibilidade e pede uma nova referência.
Uma referência incompatível não invalida a avaliação atual.

## O que permanece fora da cobertura

O item 3 importa o acervo JSON para SQLite, mas a aplicação ainda busca tickets
do Firestore. Esta suíte **não mede recuperação do acervo importado**. O relatório
destaca essa pendência em todas as execuções, junto de busca vetorial/híbrida,
resposta por LLM, imagens/PDF e políticas de acesso/partições temporais do acervo.
Esses itens não são contabilizados como testes aprovados.

No item 6, as escolhas de arquitetura e sua implementação deverão conectar a
busca ao acervo definido e permitir a ampliação desta avaliação para os serviços
implantados. Até lá, os resultados descrevem apenas o comportamento atual e os
casos sintéticos declarados.

Atualização do item 6: a nova busca local do acervo foi adicionada em uma rota e
tela próprias. Use `python -m evaluation.hybrid` para compará-la com a busca
textual, usando o modelo de embeddings local real e o corpus sintético. Consulte
[a busca local](busca-local.md). O comando original continua medindo a busca de
tickets e a triagem, preservando a referência inicial.

## Testes do avaliador e do projeto

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes do avaliador conferem métricas com cálculo manual, detectam soluções
alteradas e citações inexistentes, rejeitam contratos inválidos, verificam
comparações e códigos de saída, preservam relatórios existentes e executam a
suíte com rede e inicialização do Firebase bloqueadas. A suíte de qualidade pode
ficar abaixo da meta mesmo quando os testes do software passam.
