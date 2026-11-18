# Triagem: mistura transportada para o silo da produção anterior

Modelo piloto para revisão. Data: 30/10/2026. Este documento descreve o conhecimento e os encaminhamentos da triagem; não implementa um motor de diagnóstico.

## Cenário e observações

Identificador: TRIAGEM_MISTURA_DESTINO_001.

Relato inicial: transporte da mistura definido para um silo, porém direcionando produto para o silo da batelada anterior.

| Observação | Resposta recebida | Origem |
| --- | --- | --- |
| Destino físico do produto atual | Silo da batelada anterior | Relato do usuário nesta conversa |
| Destino exibido na Unit do transporte | Correto para a produção atual | Relato do usuário nesta conversa |
| Rota indicada como ativa no supervisório | Para o silo anterior | Relato do usuário nesta conversa |
| Comportamento observado da rota anterior | Permaneceu ligada | Relato do usuário nesta conversa |
| Produto da batelada anterior na linha | Ainda presente | Relato do usuário nesta conversa |
| Origem do novo destino | Nova produção já agendada para outro silo | Relato do usuário nesta conversa |
| Alarme | Intertravamento | Relato do usuário nesta conversa |
| Texto, código, equipamento e horário do alarme | Não informados | Desconhecido; não equivale a ausência de registro |

As oito respostas iniciais são observações relatadas, ainda não verificadas em arquivos originais do incidente. Posteriormente, o usuário identificou C007 COOPRATA e confirmou o ticket #14729. O contexto foi recuperado do atendimento: 18/09/2024, aproximadamente 06h11; produções 62134/62136; Units 8/9; destinos SEN05/SE10. A análise histórica e os limites estão detalhados em `analise_ticket_14729.md`.

Estado atual: **análise histórica documentada, com complemento relacionado identificado**. O diagnóstico e a correção estão documentados no atendimento; o ticket #15097 registra ajuste complementar, testes e carregamento. Os arquivos originais não foram reabertos e a confirmação do resultado duradouro permanece pendente. A aplicação automática continua desabilitada.

## Solicitação de evidências

A aplicação obtém as evidências da ocorrência exclusivamente pelos arquivos anexados pelo usuário. Ela solicita os anexos necessários, interpreta o material recebido e continua a triagem. Somente caminhos padrão definidos no código do produto, como `C:\Gemba\LOG\DataManager`, podem permanecer como orientação de coleta. Caminhos particulares do computador ou de compartilhamentos do ambiente não integram os dados persistidos. A aplicação recebe os arquivos por anexo.

Cada solicitação indica quais arquivos anexar, finalidade, identificadores e período. Primeiro verificar os anexos já recebidos para evitar pedidos repetidos. Quando um arquivo estiver indisponível, registrar a lacuna e solicitar uma evidência alternativa pertinente.

Fluxo previsto: identificar a lacuna → solicitar o anexo necessário → verificar conteúdo, período e identificadores → interpretar e registrar evidências com referência ao arquivo/trecho → atualizar as hipóteses → perguntar, solicitar complemento ou orientar.

Tickets, artigos e regras já preparados permanecem como base de conhecimento da RAG. Os anexos acrescentam evidências da ocorrência em análise.

Para uma ocorrência sem identidade, primeiro identificar cliente/instalação, versão efetivamente instalada, data e horário aproximado, Units envolvidas, silos anterior/esperado e números das duas produções/bateladas, na medida em que estiverem disponíveis. Neste caso, reutilizar o contexto recuperado do #14729 e solicitar apenas as lacunas. Para aplicar uma correção hoje, identificar a revisão efetiva do DataManager instalado. O período coletado deve cobrir a passagem da última batelada anterior para a primeira batelada afetada, incluindo as etapas anteriores de ocupação e posteriores de parada/troca. Sem precisão no horário, usar o intervalo conhecido e refiná-lo pelos registros encontrados.

| Arquivos a solicitar ao usuário | Origem orientativa para coleta pelo usuário | Finalidade e leitura esperada |
| --- | --- | --- |
| Histórico de alarmes da ocorrência | Exportação ou captura do sistema | Recuperar texto integral, código, início/fim, rota/Unit/equipamento e horários disponíveis. Identificar o bloqueio efetivamente indicado e sua posição na sequência. |
| Eventos de escolha e transição da rota | `C:\Gemba\LOG\DataManager\Transport` e arquivos complementares pertinentes | Correlacionar Unit/rota e horários de teste, início, parada e atualização de estado. No código de referência há mensagens `TEST INTERLOCK ROAD`, `VERIFY TEST ROAD`, `TRANSPORT ROAD`, `START STOPPING` e `TRANSPORT STATUS`. O texto varia por versão; a linha de teste não comprova aprovação. |
| Escritas dos equipamentos que determinam o destino | `C:\Gemba\LOG\DataManager\PLCWrite` | Localizar os blocos `Escreveu-> Programa` correspondentes ao PLC, equipamento, endereço/tag, rota e período. Comparar comandos da rota anterior e da esperada, incluindo escritas posteriores que possam ter substituído a anterior. Produção/batelada podem não estar presentes ou estar zeradas em alguns rótulos. Valores esperados dependem do cadastro, protocolo e etapa. |
| Resultado das escritas correlacionadas | `C:\Gemba\LOG\DataManager\Write` | Cruzar o mesmo item/endereço e período com sucesso, erro e eventual `Write Skiped`. No ramo OPC Word examinado, `Valor` nessa mensagem representa o código de retorno, não o valor do comando. Nem confirmação da API nem registro no PLCWrite comprovam movimento físico. |
| Sequência de ocupação e encerramento das Units | Registros de Unit/produção/batelada no sistema, complementados por `Log REG*` e `Log_Unit*` na raiz de `C:\Gemba\LOG\DataManager` | Relacionar produção/batelada e Unit real com os eventos do transporte. No código de referência, a mensagem `Apagou a Unit de transporte:` imprime um número de produção nessa posição; não interpretá-lo como código da Unit. Preservar a precisão temporal disponível. |

Coleta complementar depende do que aparecer: `Analysis`, quando existente e pertinente à versão; configurações de origem/rota/destino e equipamentos; retornos do equipamento em diagnóstico ou logs com interpretação comprovada; registros de mudança de destino e nível alto se houver eventos dessa natureza. PLCRead não é uma captura universal de todos os sinais do PLC.

Se o usuário não dispuser de um arquivo, registrar sua indisponibilidade e solicitar um anexo alternativo pertinente. A ausência do arquivo não demonstra que o comando ou evento não ocorreu. Não solicitar alteração de configuração ou reprodução em produção para preencher essa lacuna.

## Hipóteses e decisões

| Hipótese candidata | Evidência necessária | Próximo encaminhamento |
| --- | --- | --- |
| Encerramento/troca da rota anterior não concluído na passagem entre produções | Linha do tempo de produto, Units, rota, parada e alarme | Localizar a última etapa comprovada e a próxima etapa esperada para a versão/configuração da instalação. Só então interpretar por que a nova rota foi bloqueada. |
| Rota anterior acionada novamente durante a transição | Sequência registrada de parada seguida de novo início da rota anterior | Comparar com os precedentes #14729 e #14869. O usuário percebeu continuidade; eventual reacionamento só pode ser acrescentado como constatação dos registros, preservando o relato original. |
| Rota/comandos escolhidos não correspondem ao destino esperado | Cadastro da ligação Unit/origem/destino e registros da rota e de cada equipamento | Separar escolha da rota, mapeamento/configuração e comando efetivamente gerado. Destino correto na Unit não comprova essas etapas. |
| Comando esperado foi gerado, mas houve falha, descarte, substituição ou divergência de retorno | PLCWrite + Write + retorno do mesmo equipamento/endereço no período | Seguir o ponto da divergência constatada. Pedir diagnóstico específico do equipamento quando necessário. Não inferir falha de PLC ou mecânica a partir da escrita isolada. |

É possível haver mais de uma condição contribuinte. O conjunto de hipóteses deve admitir causas ainda não catalogadas. Não converter a ordem desta tabela em probabilidades ou diagnóstico confirmado.

## Critérios de avanço

1. Relacionar evidências à mesma instalação, período, produção/batelada, Unit e rota. Se não for possível, solicitar apenas a identificação faltante.
2. Confrontar a versão instalada e a configuração efetiva com a fonte de conhecimento. O código de referência 2026.4.4.1.0 não identifica a versão do incidente.
3. Construir a sequência de ocupação, rota anterior, solicitação de parada/troca, escolha da nova rota, escrita, resultado e alarme, conforme os eventos disponíveis. Não forçar uma ordem global só pela posição das linhas de arquivos diferentes.
4. Se os registros contradisserem uma resposta, manter as duas origens e esclarecer o conflito. Não sobrescrever silenciosamente o relato.
5. Recomendar uma ação específica somente quando sua aplicabilidade e fundamentação estiverem documentadas. Registrar verificação do resultado separadamente da ação.
6. Se faltar evidência, produzir uma solicitação delimitada ou encaminhar para análise técnica com a lacuna identificada. Não encerrar com a solução do ticket mais parecido.

## Precedentes e fontes

Base consultada: `00_evidencias_associações.csv`.

- #14729: `interacao_155536` relata destino correto nas Units e rota para silo anterior; `interacao_156930` documenta análise de registros com reacionamento da rota anterior; `interacao_157259` e `interacao_157455` documentam alteração do critério de seleção de rota. Versão de origem informada nesse histórico: V4.3.6.0; versão corrigida informada: V4.4.0.1. A aplicação e o resultado no cenário atual não estão demonstrados.
- #14869: `interacao_157451` descreve reacionamento durante encerramento e alteração relacionada. Esse ticket também contém outra ocorrência após troca manual de silo; não consolidar ambas como a mesma causa. O artigo 614 documenta a ocorrência de sobreposição e o 619 trata o cenário posterior de troca manual sem reinício automático.

Fundamentação dos pedidos de evidência: `02_evidencias_processos.csv`, IDs `e2e_codigo_transport`, `e2e_codigo_transport_status`, `e2e_codigo_resultado_escrita`, `e2e_codigo_reg`, `proc_plcwrite_comando_equipamento` e `e2e_codigo_registro_plcwrite`.

Código de referência consultado nesta modelagem: `DataManager\mdlTransportUpdateNormalTransport.vb`, seleção/início de rota, linhas 35–145, e verificação de rota disponível, linhas 690–825. A associação do código de referência com qualquer executável instalado precisa de confirmação própria.

Os arquivos existentes de Tickets, Regras de Negócio e Processos foram apenas consultados. Este piloto permanece separado para revisão do padrão de triagem.

## Continuação após identificação da ocorrência

Consultar `analise_ticket_14729.md` para a linha do tempo, distinção entre relato e registro, correção original e complemento #15097. O modelo JSON inclui o contexto identificado, fontes, pendências e uma etapa de recuperação da análise histórica. O caminho CEDOC indicado no atendimento não ficou acessível nesta sessão.

## Regra de recebimento de evidências

Definição do usuário: a aplicação solicita arquivos anexados e não acessa caminhos do ambiente do cliente. A tentativa manual anterior de consultar a pasta CEDOC é apenas histórico desta análise. O fluxo da aplicação utiliza os anexos recebidos; informar um caminho não equivale a fornecer o arquivo. Este ajuste foi modelado nos documentos e no JSON, sem implementação no software.

## Armazenamento proposto e referências

O armazenamento está em definição, possivelmente em banco de dados. Este piloto define os registros e vínculos sem escolher uma tecnologia de banco ou implementar a persistência.

- Guardar conhecimento técnico, observações, perguntas, respostas, hipóteses, ações e relações por identificadores.
- Guardar os caminhos padrão de logs/saídas definidos no código do produto, com seu contexto de versão, apenas como orientação de coleta.
- Identificar anexos por `anexo_id`, nome do arquivo sem diretório e metadados de conteúdo; apontar evidências para `anexo_id`/`fonte_id` e trecho/linha/evento.
- Identificar código por versão/revisão, caminho relativo no repositório, método/linhas e hash.
- Não persistir caminhos locais do computador de coleta, diretórios de checkout ou endereços particulares de compartilhamentos. A aplicação não acessa o ambiente do cliente por caminhos.
- O armazenamento do conteúdo dos anexos originais ainda será definido. O modelo de conhecimento derivado precisa tratar referências particulares encontradas no texto antes da persistência, mantendo caminhos padrão confirmados no produto.

As referências de arquivos de importação nesta documentação são nomes lógicos de origem, sem localização no computador. O modelo JSON utiliza `fonte_id` para vincular essas fontes.

## Estrutura de banco como fonte transversal

Foi adicionada a fonte lógica `esquema_agpr5_referencia_2026_10_30`, identificada pelos objetos do catálogo e associada ao código. Ela documenta estrutura, não os valores da ocorrência C007 de 2024. A origem do backup consultado é AGPR5_C389, restaurado como AGPR5_CLEAM conforme confirmação do usuário. Quando necessário, a triagem solicita exportações específicas do caso por anexo (E08); a aplicação não acessa banco remoto. A descrição do levantamento está em `analise_banco.md`, e o armazenamento final permanece em definição.

## Versão associada ao banco de referência

O usuário informou que o backup e o banco de referência correspondem à **DevGembaMillV2026.4.4.1.0**. O vínculo de versão foi registrado com essa proveniência nos metadados da fonte. Ele permite organizar as relações com o código da mesma versão nominal; a validação das regras por processo permanece necessária. O incidente C007 de 2024 mantém sua própria versão histórica.
