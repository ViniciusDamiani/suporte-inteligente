# Conversa de esclarecimento — piloto

Na página principal ou em `acervo.html`, descreva o problema e envie ao
assistente. O servidor pesquisa no acervo local, prepara fichas de até três
casos e pede ao Gemini uma decisão: perguntar, orientar com citações ou declarar
evidência insuficiente. Cada resposta do usuário refaz a busca com o contexto.
Para recuperar os candidatos, usa somente o conteúdo informado pelo usuário:
as legendas do histórico (“pergunta”, “resposta do usuário”) não entram na busca.
Pedidos como “mostre opções” e “quais situações parecidas existem nos tickets”
também são retirados. Sem assunto pesquisável, o assistente pede contexto sem
executar uma busca com essas instruções. Componentes reconhecidos no relato
inicial restringem as fichas ao assunto; propostas/orçamentos não entram como
sintomas, exceto quando o pedido trata explicitamente desse tipo de solicitação.
Respostas sim/não usam também a pergunta correspondente. Neste acervo industrial,
“Unity” é expandido para “Unit”, preservando o relato original da sessão.

Exemplo: “Problema de comunicação com PLC”. Se os casos recuperados diferem
entre configuração inicial e alteração de versão, o assistente pode perguntar
se a comunicação nunca funcionou ou parou após uma mudança. A pergunta é
gerada a partir das evidências e não representa diagnóstico confirmado.

## Como testar

1. Execute `python run.py` e entre com um usuário do Firebase.
2. Atualize a página com Ctrl+F5 para carregar o JavaScript novo.
3. Descreva um problema geral e responda à pergunta quando houver.
   Quando existirem alternativas apoiadas nas fontes, elas aparecem como botões.
   Escolher uma envia a resposta e refaz a busca. “Nenhuma dessas / escrever outra
   resposta” permite descrever um caso diferente sem enviar automaticamente.
4. A orientação final aparece na própria conversa e relaciona o problema à ação
   registrada e ao resultado conhecido, preservando as incertezas. Abaixo aparecem
   os “Tickets utilizados nesta resposta”, deduplicados e limitados às fontes
   citadas. Clique em um para consultar o documento ou abra “Detalhar tickets
   utilizados” para conferir evidências. Candidatos descartados não são listados;
   durante o esclarecimento não há lista de tickets. Na busca sem IA, a seção
   “Detalhar tickets encontrados” continua disponível para consulta manual.
5. Use “Nova investigação” para mudar de problema. “Pesquisar sem IA” executa
   uma busca local independente e encerra a conversa exibida.

`GEMINI_ENABLED=true`, chave e modelo válidos continuam necessários. Enviar ao
assistente permite chamadas externas; o aviso aparece na tela. Sem ativação ou
se houver falha, os tickets locais permanecem disponíveis e um aviso explica
o ocorrido. O piloto não executa procedimentos nem altera tickets.

## Contexto e consumo

- Fichas são extraídas sob demanda dos documentos já indexados: problema,
  diagnóstico, solução documentada/candidata, resultado, versão e condições.
  Campos ausentes não são inventados. Não há resumo por IA na importação e
  não é necessário reindexar. Campos longos têm cortes identificados.
- O contexto da sessão preserva o relato inicial e pares de pergunta/resposta
  em até 2.000 caracteres. Não é uma memória sem limite; detalhes longos
  podem ficar fora do contexto enviado. Nenhum fato é inferido pelo servidor.
- São enviadas até três fichas. Títulos administrativos, origem, identificadores
  internos e objetos de sessão não entram no prompt. O mascaramento por padrões
  não substitui revisão de confidencialidade do texto livre.
- A seleção local examina até vinte candidatos e prioriza a relação com o assunto,
  sintomas concretos e diversidade. Alternativas genéricas que só repetem o relato
  são descartadas. Se a IA se abstiver ou fizer uma pergunta aberta e as fichas
  contiverem alternativas concretas, a interface pode usar opções extraídas dessas
  descrições, sem chamar o provedor novamente e respeitando o limite de perguntas.
- A resposta final exige pelo menos uma citação de diagnóstico, ação ou resultado
  documentado na ficha. Citar apenas o relato de um problema ou uma solicitação
  de serviço não libera uma orientação final. Essa verificação estrutural não
  substitui a avaliação semântica nem a revisão técnica da orientação.
- Antes de gerar, a API `countTokens` conta o pedido. Acima de 4.000 tokens de
  entrada a geração é bloqueada. A saída tem limite de 1.800 tokens, incluindo
  o JSON. A tela informa a contagem de entrada e, quando retornado pelo Google,
  o total da geração. Esses números não são valores monetários nem cotas diárias.
- Cada envio com candidatos pode fazer uma contagem e uma geração. A busca e
  as fichas são locais. Sem candidatos, a primeira pergunta básica é local.
  Se o Gemini se abstiver no primeiro turno, o servidor também faz uma pergunta
  básica sobre o sintoma, sem uma chamada adicional, em vez de encerrar o relato.
  Se houver sintomas distintos nas fichas, essa pergunta local também pode oferecer
  alternativas extraídas desses sintomas. Não são geradas alternativas sem fontes.
- São permitidas até três perguntas de esclarecimento; após isso, o modelo
  precisa orientar com evidências ou declarar insuficiência. Limite de seis
  mensagens do usuário por investigação. Não há promessa de diagnóstico.

## Sessões e API

`POST /knowledge/conversation` exige autenticação e aceita somente:

```json
{
  "message": "Parou depois de atualizar o supervisório",
  "request_id": "UUID novo por mensagem",
  "session_id": "UUID retornado na primeira resposta; omitir ao começar"
}
```

O retorno preserva os resultados da busca e acrescenta `session_id`, `turn`,
`messages`, `decision`, `follow_up`, `generated_answer`, `generation_status` e
`usage`. Na conversa, o Gemini recebe um catálogo de trechos identificados
(`F1:E1`, etc.) e seleciona esses IDs. O servidor monta as citações com o texto
original, dispensando a cópia literal pelo modelo. IDs inexistentes são rejeitados.
O texto das fichas não é duplicado no pedido. A rota antiga `/knowledge/answer`
continua conferindo as citações literais retornadas pelo modelo.
Conferir a presença da citação não comprova que a conclusão é sustentada.

Sessões ficam no SQLite `instance/conversations.sqlite3`, isoladas pelo UID do
Firebase, com bloqueio de processamento simultâneo. Repetir a última mensagem
com o mesmo `request_id` retorna a resposta armazenada sem gerar outra vez.
Para integração externa, preservar esse ID em tentativas após falha de rede.
Falhas técnicas aparecem separadas de evidência insuficiente. O botão “Tentar
novamente” faz uma nova chamada somente ao ser acionado. Repetir a mesma mensagem
após falha técnica mantém o turno original, sem acrescentar uma resposta fictícia
do usuário ou gastar outro dos seis turnos. Uma falha técnica não libera uma
resposta inválida nem relaxa a verificação de referências.

Registros inativos por 24 horas são removidos na próxima operação. A sessão
atual fica apenas na memória da página; atualizar/fechar a página inicia outra
investigação. “Nova investigação” limpa a tela, sem apagar imediatamente o
registro local. As rotas antigas de busca e resposta continuam disponíveis.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check acervo.js
node tests/test_conversation_ui.cjs
```

Os testes de conversa verificam isolamento, repetição idempotente, falhas do
provedor, orçamento, perguntas repetidas, recuperação de solução no final de
documentos longos e preservação das referências. As respostas do provedor nos
testes automatizados são simuladas; homologação da utilidade exige casos reais.

Também foi exercitado o fluxo completo da API com o Gemini real, autenticação
simulada e dois tickets fictícios: a primeira mensagem gerou esclarecimento
(712 tokens de entrada; 760 no total); a resposta sobre atualização gerou
orientação citando o ticket compatível (772 de entrada; 899 no total). Nenhum
conteúdo real do acervo foi enviado nesse teste. Esses valores são exemplos,
não estimativas para todos os atendimentos. O controlador da tela foi testado
em Node; a inspeção visual em navegador ficou indisponível no ambiente.
