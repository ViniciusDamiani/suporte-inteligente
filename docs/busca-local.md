# Item 6 — Busca híbrida local

Esta entrega conecta o acervo importado ao atendimento. Usa o SQLite existente
como origem e um segundo SQLite como índice, sem PostgreSQL, Ollama ou API de IA.
Os embeddings são calculados por um modelo multilíngue executado em CPU.

A busca retorna uma lista de trechos com fontes. A geração opcional pelo Gemini
foi acrescentada em seguida e permanece desativada por padrão; veja
[a configuração do Gemini](gemini.md). Pesquisar não chama a API de geração.
A autenticação e os tickets existentes continuam no Firebase e exigem conexão.

## Preparação no computador que hospeda a aplicação

Use Python 3.10 ou superior, 64 bits. Esta entrega foi verificada com Python 3.12
no Windows. O runtime ONNX precisa de plataforma compatível; o pip informa se
não houver pacote disponível para o ambiente.

Na pasta do projeto, usando o ambiente Python do destino:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m knowledge_search preparar-modelo
.\.venv\Scripts\python.exe -m knowledge_import status
```

`preparar-modelo` é o único comando da busca que usa internet. Baixa cerca de
129,2 MiB de arquivos públicos, fixados por revisão e SHA-256, para
`instance/models/multilingual-e5-small/`. Não envia textos do acervo. Execute uma
vez no servidor ou transfira essa pasta já preparada. Não é preciso instalar
banco ou modelo nos computadores dos atendentes.

Se o banco de conhecimento ainda não existir no destino:

```powershell
.\.venv\Scripts\python.exe -m knowledge_import importar
```

Prepare o índice e confira a situação:

```powershell
.\.venv\Scripts\python.exe -m knowledge_search indexar --relatorio instance\busca-carga-001.json
.\.venv\Scripts\python.exe -m knowledge_search status
.\.venv\Scripts\python.exe -m knowledge_search buscar --consulta "falha de comunicação com PLC"
```

Não existe download automático quando um usuário pesquisa. Sem o modelo local,
a indexação híbrida informa o que falta. Para preparar apenas a parte textual,
use `indexar --somente-texto`. Essa opção publica um índice textual e **não
equivale à busca híbrida**. Para ativar a parte vetorial, prepare o modelo e
execute `indexar` sem essa opção.

A primeira indexação exige mais processamento. O terminal informa progresso a
cada 250 documentos. Novas indexações reaproveitam vetores de conteúdos idênticos
quando o modelo é o mesmo. Os arquivos JSON originais não são alterados.

## Uso na interface

Reinicie a aplicação e atualize o navegador com Ctrl+F5.

- No painel, abra **Pesquisar no acervo** (`acervo.html`).
- Digite uma descrição do problema ou mensagem de erro.
- Confira os trechos e use **Consultar conteúdo da fonte** para ler o texto
  técnico preparado daquele registro.
- Na triagem, use **Pesquisar no acervo com o contexto desta triagem**. A busca
  combina relato, descrição complementar, versão e texto de alarme. Cliente,
  horário, Units e anexos completos não são acrescentados.

A pesquisa de tickets do painel permanece separada da nova pesquisa do acervo.
A nova busca usa o Firebase somente para autenticar o usuário.

Todos os atendentes autenticados consultam o mesmo acervo, conforme definido
para esta instalação. As sessões de triagem continuam privadas ao proprietário.

## O que entra no índice

A seleção exige `searchable=1` na visão ativa do importador e
`metadados.disponivel_pesquisa=true`. A projeção atual suporta `caso_ticket`;
tipos diferentes ficam fora do índice até terem um contrato próprio de conteúdo.
O relatório contabiliza essas exclusões. No pacote atual, os 10.226 registros
elegíveis são desse tipo.

A projeção inclui assunto, área técnica, problemas, diagnóstico, soluções
documentadas/candidatas, resultado, pendências, versões e aplicabilidade. Campos
administrativos como cliente, autores e técnicos não são copiados como campos
de contexto. Há mascaramento de padrões de e-mail, documentos formatados,
credenciais e caminhos. Isso não garante anonimização do texto livre.
**A pesquisa e os embeddings não enviam conteúdo a APIs externas.** A geração
opcional com Gemini envia um recorte quando ativada e solicitada pelo atendente.

As marcas de revisão e uso são preservadas. Hipóteses e contexto histórico não
viram soluções confirmadas. Uma solução documentada também exige verificação de
aplicabilidade ao atendimento atual.

Cada trecho referencia pacote, registro, arquivo de origem e intervalo de
caracteres do texto preparado. Esse intervalo não é uma linha do JSON original.
Referências de arquivo são somente texto; não permitem abrir caminhos arbitrários.

## Recuperação e limites

1. Textos são divididos em trechos de até 1.000 caracteres, com sobreposição de
   até 120. Trechos que excederiam o limite do modelo são subdivididos.
2. SQLite FTS5 pesquisa palavras normalizadas e códigos, com peso maior no título.
3. O modelo E5 representa perguntas (`query:`) e trechos (`passage:`) em vetores
   de 384 dimensões, normalizados. A pesquisa compara esses vetores por cosseno.
4. As duas listas de até 80 candidatos são combinadas por Reciprocal Rank Fusion
   (`k=60`). A saída remove duplicatas por registro e mostra até oito fontes por
   padrão. A pontuação não é uma probabilidade de diagnóstico correto.

Os vetores ficam no banco do índice. Uma matriz é carregada na memória de cada
processo do servidor e reutilizada entre consultas. A pesquisa vetorial faz uma
varredura exata da matriz; ampliações do acervo precisam de novas medições e
podem justificar outro índice. Cada processo também mantém seu modelo na memória.

Modelo: `intfloat/multilingual-e5-small`, revisão
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, ONNX quantizado em int8, licença MIT.
O runtime usa CPU, pooling pela média com máscara de atenção e normalização L2.
Pesos e tokenizer são conferidos antes de carregar.
[Referência oficial do modelo](https://huggingface.co/intfloat/multilingual-e5-small).

A nota mínima vetorial padrão é **0,85**, uma referência inicial de desenvolvimento,
não um limite universal de confiança. Na avaliação sintética, 0,80 recuperou
também resultados para consultas sem cobertura. O corte conservador reduz isso,
mas pode perder paráfrases pertinentes. Ambos os relatórios foram preservados.
É necessário validar o limite com casos reais rotulados, sem reduzir expectativas
apenas para aprovar a implementação.

Se o modelo estiver indisponível durante uma consulta, a parte textual continua
funcionando e a interface informa a limitação. Uma consulta longa demais para o
modelo também pode usar apenas a parte textual. Se o acervo mudou desde a
indexação, a busca bloqueia os resultados até atualizar o índice, evitando servir
registros retirados ou com elegibilidade antiga.

## Atualização do acervo

Depois de preparar uma nova versão do pacote JSON:

```powershell
.\.venv\Scripts\python.exe -m knowledge_import importar --atualizar-busca --relatorio instance\carga-com-busca-002.json
```

Também é possível importar e executar `python -m knowledge_search indexar`
separadamente. O índice é preparado em arquivo temporário e publicado numa única
transação. Falhas de cálculo não substituem a versão anterior. A origem é
reconferida antes da publicação para evitar ativar um índice de uma versão vencida.

Se a importação concluir e a indexação falhar, a carga fica preservada; o comando
retorna `2` e registra `busca.estado=pendente`. Corrija a causa e execute `indexar`.
Código `1` continua indicando rejeição/erro de importação. O comando independente
`knowledge_search` retorna `0` em sucesso e `1` em erro.

## Configuração e transferência

| Caminho padrão | Conteúdo |
| --- | --- |
| `instance/knowledge.sqlite3` | Origem importada, com histórico. |
| `instance/search.sqlite3` | Índice reconstruível, com textos e vetores. |
| `instance/models/multilingual-e5-small/` | Modelo e tokenizer. |
| `instance/triage.sqlite3` | Sessões de triagem existentes. |

Veja `.env.example`. Podem ser configurados `KNOWLEDGE_DATABASE`,
`KNOWLEDGE_SEARCH_DATABASE`, `KNOWLEDGE_MODEL_DIR`,
`KNOWLEDGE_EMBEDDING_THREADS` e `KNOWLEDGE_MIN_SIMILARITY`.
O índice não pode usar o mesmo arquivo da origem. Por padrão o modelo usa dois
threads; ajuste após medir o impacto no computador de destino.

Ao atualizar o ambiente, preserve `.env`, credenciais, bancos e sessões existentes.
Transfira o código, instale dependências na `.venv` do destino e prepare o modelo
e o índice ali. Alternativamente, copie uma origem/índice correspondentes e a
pasta do modelo com aplicação, importador e indexador parados. Para bancos em
uso, utilize backup próprio do SQLite; não copie apenas o arquivo principal
ignorando arquivos WAL. O índice pode ser reconstruído a partir da origem.

Bancos, pesos e relatórios são ignorados pelo Git e não são servidos como
arquivos estáticos. É necessário disco persistente no servidor/VM. Cinco
usuários diários não equivalem a cinco consultas simultâneas: memória e tempo
de resposta precisam ser medidos no equipamento de destino.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m evaluation.hybrid
```

Testes unitários usam vetores controlados para verificar persistência, combinação
de listas, invalidação, permissões e referências. `evaluation.hybrid` usa o
modelo real local com o corpus sintético do item 5, compara com a busca textual
e gera HTML/JSON/CSV em `instance/evaluation/`. Falhas retornam código `1` e
permanecem visíveis; o avaliador não altera os rótulos para aprovar resultados.

Na verificação desta entrega, os 83 testes de funcionamento passaram. A interface
foi exercitada no Edge em larguras de computador e celular, com consulta, leitura
da fonte, ausência de resultados e contexto da triagem. A autenticação desses
testes foi simulada; a conexão com o Firebase do ambiente de destino ainda precisa
ser conferida durante a implantação.

Na avaliação com corte 0,85, passaram **13 de 15 cenários**, sem erros de execução.
Recall@5 foi 83,3% em 12 consultas positivas, abaixo da meta de 90%. As três
consultas negativas não retornaram fontes. As paráfrases B13/B14 ainda falham.
Não foi demonstrado ganho agregado sobre a busca textual nessa pequena amostra.

### Medição no acervo completo em 01/11/2026

No computador de desenvolvimento, 10.226 registros produziram 12.550 trechos.
A primeira carga levou 1.919,61 segundos (cerca de 32 minutos). Uma nova carga,
sem alterações, levou 13,47 segundos e reaproveitou os 12.550 vetores, sem novos
cálculos. O índice ocupa aproximadamente 82 MiB, além do banco de origem e modelo.

A primeira consulta, incluindo o carregamento do modelo e da matriz, levou
1,656 segundo. Com esses recursos já carregados, cinco consultas curtas em
paralelo concluíram em 0,063 segundo no total. Foram verificadas a ausência de
duplicatas e a correspondência dos trechos com as fontes, com conexões de rede
bloqueadas durante essa verificação. Isso mede o serviço de busca diretamente;
não inclui navegador, autenticação Firebase, tráfego de rede ou julgamento da
pertinência dos resultados. Não é uma previsão de desempenho na VM do cliente.

Relatórios locais: `instance/search-primeira-carga.json`,
`instance/search-reindex-verificacao.json`, `instance/verificacao-busca-real.json`
e `instance/evaluation/hybrid-2026-11-01-final/relatorio.html`. Não são versionados.

`python -m evaluation` continua avaliando a busca de tickets do Firestore com
adaptador em memória e a triagem; não mede a nova recuperação no acervo.

## Pendências do item 6

- Ativação do Gemini com a chave do destino, cotas e autorização dos conteúdos
  que podem sair do ambiente. Integração e verificação de referências implementadas.
- Avaliação da qualidade das respostas geradas pelo modelo real.
- Homologação com casos reais e medição de carga na VM do cliente.
- Leitura de imagens e PDF, caso incluída posteriormente.

Não há dependência de chave Gemini para a busca. A rota de pesquisa retorna
`generated_answer=null` e `generation_status=pending`. A geração é uma ação
separada, descrita no guia do Gemini.
