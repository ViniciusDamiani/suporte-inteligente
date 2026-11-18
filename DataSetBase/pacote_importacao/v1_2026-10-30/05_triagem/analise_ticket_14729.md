# Análise da triagem — ticket #14729, C007 COOPRATA

Revisão: 30/10/2026. O usuário confirmou que o cenário discutido corresponde ao ticket #14729, da ocorrência de 18/09/2024, aproximadamente às 06h11.

## Resultado da análise documental

Há uma causa e uma correção registradas para esse caso: durante o encerramento da batelada anterior, a verificação de rotas podia selecionar novamente uma Unit que ainda estava sendo apagada e acionar a rota da produção antiga. A nova produção assumia as Units com seu destino correto, enquanto a rota anterior permanecia ou voltava a ficar ativa.

O histórico também registra uma complementação posterior na mesma instalação: o ticket #15097 informa que faltava um ajuste associado ao #14729. Portanto, a associação de conhecimento precisa incluir a ocorrência original e seu complemento, preservando as datas, versões, ações e resultados de cada um.

Esta conclusão é documental: foram analisadas as interações, o artigo e o código de referência. Os arquivos originais do incidente não foram abertos. A pasta histórica indicada na interação 156930 não ficou acessível nesta sessão.

## Contexto identificado

| Campo | Informação e origem |
| --- | --- |
| Cliente | C007 COOPRATA — FÁBRICA DE RAÇÕES, confirmado pelo usuário e no artigo 614 |
| Identificador anonimizado na base | CLI_971774, registro de associação do ticket #14729 |
| Ocorrência principal | 18/09/2024, aproximadamente 06h11 |
| Produção/batelada anterior no transporte | 62134 / 16, interação 157293 |
| Destino anterior | SEN05; o histórico técnico associa a rota 326 ao silo interno 57 |
| Produção/batelada atual | 62136 / 1 |
| Destino esperado | SE10 |
| Units da transição documentada | 8 e 9; no atendimento, a Unit 7 ainda continha a produção 62134, batelada 17 |
| Versão de origem declarada | DevGembaMillV4.3.6.0 |
| Versão corrigida declarada no #14729/RIT | DevGembaMillV4.4.0.1 |
| Revisão de desenvolvimento mencionada no #14729 | 631, interação 157290; artigo 614 também lista 631 / 640 para #14729 / #15097 |

O número da rota esperada para SE10 não foi determinado nesta revisão. A rota 327 e o silo interno 58 aparecem depois, em tentativas da produção 62134 às 07h55; não identificá-los automaticamente como a rota de SE10 ou da produção 62136.

## Linha do tempo registrada no atendimento

Fonte: interação 157293. São dados e trechos de log transcritos pelo atendimento, não uma nova extração dos arquivos originais.

| Horário em 18/09/2024 | Registro |
| --- | --- |
| 06:09:46.773 | Encerramento da produção 62134 / batelada 16 na Unit 8 |
| 06:09:48.290 | Ocupação da Unit 8 pela produção 62136 / batelada 1 |
| 06:11:00 a 06:11:01 | Nova tentativa e início registrado da rota 326, silo 57, ainda referindo a produção 62134 |
| 06:11:01.197 | Encerramento da produção 62134 / batelada 16 na Unit 9 |
| 06:11:01.243 | Ocupação da Unit 9 pela produção 62136 / batelada 1 |

Os registros de ocupação da Unit 9 estão separados por 46 ms. Esse intervalo não mede a duração da falha nem permite ordenar precisamente um log que só tem resolução de segundos. A análise deve preservar essa diferença de precisão.

A interação 156930 registra a rota de ensaque acionada apesar do destino de expedição nas Units, indícios de reacionamento da rota anterior e comandos dos equipamentos observados no PLCWrite/Analysis. A interação 155628 registra o desvio físico do produto e a contabilização no destino esperado.

## Relato e evidência documental

| Ponto | Como registrar na triagem |
| --- | --- |
| Usuário percebeu a rota continuamente ligada | Preservar como observação relatada |
| Atendimento identificou novo acionamento da rota antiga | Acrescentar como conclusão da análise documental; a percepção de continuidade não resolve uma transição breve |
| Usuário relatou alarme de intertravamento | Preservar o relato; texto/código/horário dessa manifestação continuam sem recuperação específica |
| Interação 156930 inicialmente não identificou alarme relacionado às rotas | Registrar a diferença de observação; não converter em ausência comprovada de alarme |
| Interação 157293 traz bloqueios às 07h55 | Relacionar apenas às rotas/produção ali identificadas; não transplantar para a tentativa de SE10 às 06h11 |

## Correção original e complementação

### Ticket #14729 — ocorrência original

- Interações 157259, 157292 e 157455 documentam a restrição da verificação de rotas à condição `cd_road = 0`, em vez de `cd_road <= 0`. A finalidade era não iniciar a rota de uma Unit marcada para ser apagada (`-1`).
- A interação 157290 registra revisão 631 e disponibilização dos executáveis. A interação 157774 também registra disponibilização de pacote.
- A interação 157498 informa que seria carregado sem TAF. A interação 158524 registra carregamento, mas menciona alterações do ticket #11822; esse texto não basta para identificar com segurança a revisão exata do DataManager implantado para o #14729.
- O artigo 614 reúne mais de uma revisão e inclui também a remoção da atualização prematura de `cd_road` para zero. Não atribuir automaticamente todo o conteúdo consolidado do RIT ao primeiro pacote do #14729.

### Ticket #15097 — complemento documentado na mesma instalação

- Ocorrência distinta em 04/11/2024: produção destinada à SENS03 foi para SENS06. Não substituir os silos, produções e horários do #14729 pelos desse atendimento.
- A interação 160161 relaciona explicitamente o problema ao #14729 e informa que faltava remover a atualização de `cd_road` para zero durante a rotina de parada, além de ajustes associados ao C104/#14869.
- As interações 160152 e 160154 transcrevem a sequência: a rota 327 havia recebido comandos de parada, a Unit entrou no encerramento, a verificação voltou a iniciar a rota antiga e a nova produção encontrou intertravamento. São evidências documentais complementares do mecanismo; não são os logs do incidente de setembro.
- A interação 160616 registra a alteração desenvolvida e testes de troca de ração, nível alto e silo alternativo sem problemas identificados. A 160617 reforça o resultado dos testes.
- A interação 160618 registra disponibilização do DataManager. A 161244 registra carregamento remoto e acompanhamento de produção em 14/11/2024, sem detalhar um resultado duradouro após a implantação.
- A versão corrigida declarada nesse complemento é DevGembaMillV4.3.9.1. A divergência com a V4.4.0.1 citada no #14729/RIT deve ser mantida por fonte; a identificação da alteração depende também da revisão/pacote efetivo.

## Conferência no código de referência atual

Referência: DevGembaMillV2026.4.4.1.0, HEAD `7ec60bb87755d6c0302b5a4a7456c5873eb315e2`. Os três arquivos consultados não apresentaram alterações locais no status do Git verificado nesta revisão. Isso não comprova o conteúdo dos executáveis históricos do cliente.

- `DataManager\mdlDataHandlerUnit.vb`, linhas 822–847 e 2834–2869: a atualização dos dados de produção/destino da Unit e o início de uma rota são etapas distintas. No ramo examinado de sobreposição, uma rota positiva já vinculada à Unit impede uma nova chamada de início nesse ponto e pode gerar `Transporte de dosagem esta ocupado, Unit ... NOT pubStartNormalTransport`.
- `DataManager\mdlDataHandlerUnit.vb`, linhas 5300–5309: no caminho examinado, o retorno de estado da Unit com bit 1 inicia o tratamento de parada. O significado e a emissão no programa PLC histórico não foram auditados aqui.
- `DataManager\mdlTransportUpdateNormalTransport.vb`, linhas 282–308, 402–472 e 706–808: a verificação usa `cd_road = 0`; a parada normal não contém a atualização prematura para zero; há tratamento próprio de pausa e encerramento. Não extrapolar essa comparação parcial para equivalência funcional de versões.
- `Transports\clsTransports.vb`, linhas 2182–2283: a validação distingue conflito/intertravamento de rota de condição de estado dos equipamentos. No ramo sem caixa de mensagem, registra `TESTE DE INTERTRAVAMENTO DA ROTA:... ERRO:...` em `Transport\Log_Interlok ...`. O registro pode identificar a rota testada sem listar cada equipamento responsável; obter a configuração e o estado do período quando necessário.

## Como a triagem deve prosseguir neste caso

1. Utilizar o vínculo confirmado com o #14729 para recuperar o contexto já documentado, sem perguntar novamente por produções, Units e horário conhecidos.
2. Apresentar a causa como documentada no atendimento e indicar o complemento #15097, mantendo separados relato, análise documental e eventual verificação independente.
3. Para recomendar uma intervenção em uma instalação atual, identificar a revisão do DataManager efetivamente instalada e conferir se contém o conjunto das alterações pertinentes. O nome da versão isoladamente não basta neste histórico.
4. Para auditar novamente o incidente, solicitar que o usuário anexe os logs históricos de 18/09/2024 e os dados da Unit/rota no intervalo da transição. Priorizar os arquivos `Analysis` e `PLCWrite` citados no atendimento; solicitar também `Transport`/`Log_Interlok` quando disponíveis e pertinentes à versão e `Write` para conferir resultados. A origem documental é identificada pela interação do atendimento; um caminho particular de compartilhamento não será persistido nem acessado pela aplicação.
5. A orientação operacional precisa indicar a divergência, os registros a comparar e a correção documentalmente relacionada. Não transformar a alteração de consulta em instrução para editar diretamente o banco ou alterar uma rota em produção.

## Resultado para a base de conhecimento

Associação modelada: **ticket #14729 → divergência de destino durante sobreposição → reacionamento da rota anterior no encerramento → correção original + complemento #15097 → testes documentados no complemento + carregamento registrado, com resultado posterior não detalhado**.

O modelo pode recuperar esse conjunto para futuras ocorrências compatíveis. A aplicação automática continua desabilitada: mesma descrição não garante mesma versão, configuração ou causa. A base principal não foi alterada nesta revisão; os arquivos deste piloto foram atualizados separadamente.

## Localizadores das fontes

- `00_associacoes_ticket_problema_solucao.csv`: tickets 14729 e 15097.
- `00_evidencias_associações.csv`: interações 155536, 155628, 156930, 157259, 157290, 157292, 157293, 157455, 157498, 157774 e 158524; artigo 614, trechos 1–4; interações 160040, 160152, 160154, 160161, 160616, 160617, 160618 e 161244.
- Código de referência: caminhos relativos acima sob `Sistemas/Sources/PrdGemba`.

## Forma de obtenção na aplicação

As evidências da ocorrência serão recebidas exclusivamente por anexos enviados pelo usuário. A aplicação não consulta pastas locais ou compartilhadas do cliente. Somente caminhos padrão definidos no código do produto podem ser mantidos como orientação de coleta; a proveniência dos demais conteúdos usa IDs, nomes de arquivo e localizadores de trecho. Interpretar primeiro o material já anexado e solicitar apenas o complemento necessário. A tentativa de acesso descrita nesta análise foi uma consulta manual anterior à definição desse fluxo.

## Armazenamento proposto e referências

O armazenamento está em definição, possivelmente em banco de dados. Este piloto define os registros e vínculos sem escolher uma tecnologia de banco ou implementar a persistência.

- Guardar conhecimento técnico, observações, perguntas, respostas, hipóteses, ações e relações por identificadores.
- Guardar os caminhos padrão de logs/saídas definidos no código do produto, com seu contexto de versão, apenas como orientação de coleta.
- Identificar anexos por `anexo_id`, nome do arquivo sem diretório e metadados de conteúdo; apontar evidências para `anexo_id`/`fonte_id` e trecho/linha/evento.
- Identificar código por versão/revisão, caminho relativo no repositório, método/linhas e hash.
- Não persistir caminhos locais do computador de coleta, diretórios de checkout ou endereços particulares de compartilhamentos. A aplicação não acessa o ambiente do cliente por caminhos.
- O armazenamento do conteúdo dos anexos originais ainda será definido. O modelo de conhecimento derivado precisa tratar referências particulares encontradas no texto antes da persistência, mantendo caminhos padrão confirmados no produto.

As referências de arquivos de importação nesta documentação são nomes lógicos de origem, sem localização no computador. O modelo JSON utiliza `fonte_id` para vincular essas fontes.
