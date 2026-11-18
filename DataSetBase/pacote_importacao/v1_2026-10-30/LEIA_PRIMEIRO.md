# Pacote de conhecimento para importação

Versão 1.0.0, preparada em 30/10/2026.

Este pacote consolida os registros existentes e a triagem piloto. Ele prepara a carga da base de conhecimento. Ainda não executa importação em banco, embeddings, busca RAG ou chamadas a uma LLM.

## Organização

| Pasta | Conteúdo | Uso |
| --- | --- | --- |
| `00_tickets` | 10.226 casos, com a classificação de uso já aprovada | Pesquisa de ocorrências, clientes, participantes e ações documentadas. |
| `01_artigos` | 31 artigos representados por 73 trechos preparados | Catálogo documental ligado às evidências. Não representa toda a wiki. |
| `02_regras_negocio` | 865 variantes de regras | Funcionamento documentado, preservando revisão e comparação pendentes. |
| `03_processos` | 90 regras de processos | Condições, estados, alarmes e verificações de suporte. |
| `04_banco_dados` | 2.407 objetos do catálogo SQL e sete interpretações selecionadas | Estrutura de referência e interpretação de quatro tabelas e três condições. Os 2.407 objetos não são 2.407 tabelas: o snapshot contém 271 tabelas e outros tipos de objeto. |
| `05_triagem` | Um cenário histórico, seu modelo e análise | Exemplo de perguntas, evidências e encaminhamentos. |
| `06_evidencias` | Trechos de atendimento, artigos, fluxogramas, código e banco | Sustentar afirmações e conferir a origem. |
| `07_vinculos` | Relações entre registros | Navegar entre caso, regra, artigo, evidência e fonte. |
| `08_fontes` | Referências portáveis de procedência | Identificar a fonte sem depender do computador de preparação. |
| `09_controle` | Dicionário, esquema, validação e pendências | Conferir e importar o pacote de maneira reproduzível. |

Tickets, Regras de Negócio e Processos continuam sendo os três grupos principais. Artigos, banco e evidências são recursos transversais. As pastas indicam tipos de conteúdo e não mudam essa divisão funcional.

## Arquivo de entrada

O arquivo `catalogo_importacao.json` é a lista oficial do que carregar. O importador deve ler apenas entradas com `importar: true`, usando os caminhos relativos à pasta deste pacote. Não deve procurar todos os CSVs ou JSONs na DataSetBase.

Os arquivos JSONL contêm um objeto JSON completo por linha. Permitem leitura em lotes e preservam listas, booleanos e metadados. Os CSVs de origem continuam disponíveis para edição e auditoria na DataSetBase. Eles não devem ser carregados novamente junto com este pacote, pois isso duplicaria o conteúdo.

Os documentos completos de banco e o modelo de triagem em JSON são cópias auxiliares para consulta. O catálogo distingue esses recursos dos registros normalizados, evitando indexar duas vezes a mesma explicação.

## Identidade, evidências e acesso

Cada entidade tem um ID com prefixo de tipo, ID original, procedência, contexto de cliente/versão, estado de revisão e hash do conteúdo. Os vínculos usam esses IDs completos e todos os seus extremos foram conferidos. Os números e listas dentro de `dados` conservam a convenção da origem; para navegar no pacote, usar os vínculos normalizados.

Uma relação como `historico_do_atendimento` identifica a origem de uma evidência. Ela não afirma que a interação contém uma solução. Relações derivadas de fluxogramas também não certificam a lógica implantada. As ressalvas e os estados originais permanecem nos registros.

Disponibilidade para pesquisa não concede acesso irrestrito. A aplicação precisa aplicar as permissões do usuário antes de recuperar conteúdo ou enviá-lo a um modelo. Aliases de cliente permanecem como na base; esta entrega não deduz números reais a partir deles.

## Portabilidade

As fontes locais foram substituídas por IDs e referências lógicas. Referências locais presentes nos textos foram normalizadas; esses trechos não devem ser descritos como transcrições literais integrais. Os arquivos de origem não foram modificados e seus hashes constam na validação.

Somente os caminhos padrão de logs do produto permanecem absolutos, como orientação de coleta. A aplicação obtém evidências do incidente por anexos do usuário; nenhuma referência do pacote habilita acesso automático a discos, compartilhamentos, GitLab ou banco do cliente.

Esta organização não constitui auditoria integral de dados pessoais ou segredos nos textos históricos. A configuração de acesso e o tratamento adicional do conteúdo precisam ser definidos antes do envio a provedores externos.

## Triagem

O cenário da mistura contém observações do ticket #14729 e referências ao complemento #15097. É um exemplo histórico documentado, com limitações e revisão pendente. As respostas desse cenário não podem ser copiadas para o estado de um novo atendimento.

Cada sessão nova precisa de contexto próprio, evidências anexadas e hipóteses atualizadas. O material aqui define o conhecimento disponível; ainda será necessário implementar o motor que escolhe perguntas e interpreta anexos.

## Atualização e retirada

1. Editar os registros de origem e registrar a revisão funcional quando aplicável.
2. Gerar uma nova versão completa do pacote. Não editar silenciosamente uma versão já publicada.
3. Validar estrutura, integridade, referências, contagens e permissões antes de ativá-la.
4. Carregar entidades por `id`, atualizando quando o hash do conteúdo mudar. Carregar fontes e entidades antes dos vínculos. Carregar referências auxiliares do banco conforme o catálogo.
5. Preparar o novo índice separadamente e ativar o pacote apenas após a carga inteira passar nas verificações. Um erro mantém a versão anterior ativa.
6. Retirar do índice ativo os registros que deixaram de constar na nova versão completa ou perderam elegibilidade. Preservar o histórico de auditoria.
7. Reprocessar os vetores quando o conteúdo de busca, modelo, dimensão ou estratégia de divisão em trechos mudar. Uma mudança de elegibilidade exige atualizar o índice mesmo que o texto seja igual.

O catálogo raiz da DataSetBase aponta para a versão preparada. Esse apontamento organiza os arquivos; não representa publicação em produção ou homologação técnica.

## Verificações e limites

As contagens e hashes estão em `09_controle/validacao.json`. O dicionário está em `09_controle/dicionario.json`, e o esquema do envelope em `09_controle/schema_entidade.json`. Pendências estruturais, quando existirem, ficam em `09_controle/pendencias.jsonl`, fora dos vínculos ativos.

Não houve nova análise semântica integral dos tickets, homologação automática de soluções, comparação completa entre versões, carga adicional da wiki ou acesso ao SQL Server/GitLab nesta consolidação. Permanecem pendentes as decisões de modelos, divisão dos textos, ranking, permissões efetivas e implementação da aplicação.
