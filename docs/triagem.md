# Funcionalidade retirada do aplicativo

A triagem guiada foi removida da interface e da API. O código em `evaluation/legacy_triage` existe somente para reproduzir avaliações históricas offline. Bancos antigos foram preservados, mas não são acessados pelo aplicativo.

## Documentação histórica

# Item 4 — Triagem guiada

Implementação de 01/11/2026. A primeira versão executa o cenário **mistura
transportada para o silo incorreto**, derivado do piloto preparado no pacote 1.0.0.
O mecanismo é determinístico: perguntas e condições são dados JSON, e a leitura
de anexos usa marcadores conhecidos. Não há chamada a modelo de linguagem.

## Como usar

Com o `.env` e o Firebase configurados conforme o README:

```powershell
cd C:\Projeto\suporte-inteligente
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Abra `http://127.0.0.1:5000`, faça login e escolha **Triagem guiada** no menu.
A página também está em `http://127.0.0.1:5000/triagem.html`.

1. Selecione o cenário e descreva a ocorrência atual.
2. Responda às perguntas de contexto e observação. Use **Não sei / não informado**
   para registrar uma lacuna, sem inventar uma resposta.
3. Envie os arquivos disponíveis e informe se conferiu que pertencem à instalação
   e à ocorrência. Cada arquivo pode atender a mais de um pedido.
4. Confira os trechos encontrados, suas interpretações e divergências. Use
   **Corrigir** para atualizar uma resposta, preservando seu histórico.
5. Registre anexos indisponíveis e consulte a alternativa proposta.
6. Use **Encerrar coleta para análise técnica** para preservar o resumo. Isso
   encerra a edição da sessão e não envia mensagens nem confirma um diagnóstico.

Atendimentos podem ser retomados pela lista à esquerda. A lista mostra os 50 mais
recentemente atualizados do próprio usuário. A API também permite recuperar uma
sessão antiga pelo ID. Uma sessão nova sempre começa sem respostas, anexos,
diagnóstico ou observações herdadas do caso histórico.

## Dataset executável

O modelo está em `triage/models/mistura_destino.v1.json`, separado do pacote
histórico imutável. Ele contém:

- Perguntas de texto, data, horário, identificadores e escolha.
- Condições baseadas em respostas anteriores.
- Pedidos de evidência iniciais e condicionais, com alternativas.
- Hipóteses, evidências necessárias e eventos que representam indícios a verificar.
- Limites da interpretação e procedência do piloto, incluindo ID e hash da fonte.

As condições suportadas são igualdade de resposta, presença de tipo de evento
correlacionado e indisponibilidade de evidência. Não são expressões Python e não
executam código. O carregamento verifica IDs, referências e ordem de dependência
das perguntas. Uma sessão guarda a versão e uma cópia do modelo, de forma que
mudanças posteriores no arquivo não alterem silenciosamente um atendimento aberto.

Novos cenários podem ser adicionados com outro JSON compatível em `triage/models/`.
A versão do modelo deve mudar quando suas regras forem alteradas após publicação.
O importador do item 3 continua recebendo o catálogo normalizado da `DataSetBase`;
esta primeira versão da triagem usa o modelo executável incluído no código e não
faz busca RAG na base histórica durante a conversa.

## Leitura dos anexos

Formatos: **TXT, LOG, CSV, JSON e JSONL**, com UTF-8, UTF-16 com BOM ou Windows-1252.
Limites: 2 MiB por arquivo, 20.000 linhas/registros, 32.000 caracteres por registro,
500 marcadores extraídos por arquivo e 20 anexos por atendimento. Atingir o limite
de marcadores é informado como leitura parcial e exige um recorte mais específico.

São identificados marcadores de teste, início, parada e estado de rota, ocupação,
encerramento, comando, retorno de escrita e alarme. Cada achado guarda o ID do
anexo, nome sem diretório, linha ou referência de registro JSON, trecho tratado,
horário quando reconhecido, Unit quando explícita e interpretação limitada.

CSV exige cabeçalho, com separador vírgula, ponto e vírgula ou tabulação. JSON aceita
um objeto, uma lista de objetos ou uma lista na chave `registros`, `eventos`,
`records` ou `events`. Esses registros são inspecionados como texto estruturado.
JSONL exige um objeto por linha. Os nomes dos campos e mensagens precisam ser
compatíveis com os marcadores reconhecidos; os formatos reais variam por versão.

O mecanismo confere período e Unit e exige confirmação da origem pelo atendente.
Registros com outra data/Unit ficam destacados. Sem horário ou identificador
comprovável, a interpretação permanece pendente. Horários são comparados no
horário local informado; timestamps com fuso explícito exigem conferência de
conversão. Um fim anterior ao início representa passagem para o dia seguinte.
Não se deduz uma ordem global entre arquivos diferentes.

A instalação e a versão são informações fornecidas pelo atendente, não descobertas
automaticamente do arquivo. Alterar cliente ou versão invalida a confirmação de
origem dos anexos; reanexar o mesmo conteúdo com a confirmação atualizada reutiliza
o anexo existente. Alterar data, horário ou Units recalcula a correlação.

O recebimento de um arquivo não significa que a evidência está completa. **Trechos
pertinentes localizados** significa que foram encontrados marcadores correlacionados;
a cobertura de toda a transição e a interpretação funcional exigem revisão. Pedidos
de configuração e retorno sem leitor específico continuam como complemento técnico.

Imagens, PDFs, arquivos compactados e formatos binários não têm leitura automática
nesta versão. A interface pede exportação textual ou transcrição identificada.
OCR, análise visual e interpretação livre por LLM dependem da escolha e integração
dos modelos, tratadas na etapa de decisões técnicas.

## Hipóteses e divergências

As hipóteses permanecem candidatas. Marcadores de falha/descarte de escrita
correlacionados acrescentam um indício à hipótese correspondente, com IDs das
evidências. Isso não confirma a causa. Respostas e evidências são armazenadas
separadamente; uma menção a alarme diante de um relato de ausência gera um ponto
a esclarecer, sem substituir a resposta.

O sistema não conclui aprovação por uma linha de teste, não trata retorno de API
como movimento físico e não interpreta o número de `Apagou a Unit de transporte`
como código da Unit. Não prescreve mudanças de configuração ou reprodução em produção.

## Persistência e acesso

O armazenamento local padrão é `instance/triage.sqlite3`. Pode ser alterado pela
variável `TRIAGE_DATABASE`. Ele é separado de `instance/knowledge.sqlite3` e está
ignorado pelo Git. Para hospedagem em Vercel ou múltiplas instâncias, substituir
essa persistência por um serviço externo antes da publicação.

Todas as rotas exigem a autenticação Firebase existente. Somente o proprietário
pode listar, ler ou alterar a sessão, inclusive quando outro usuário é administrador.
A atualização exige a revisão corrente: duas abas não sobrescrevem silenciosamente
as respostas uma da outra. Alterações e histórico são gravados na mesma transação.

Os anexos originais não são gravados. Permanecem hash SHA-256, tamanho, nome,
metadados e trechos derivados. Há mascaramento por padrões de e-mail, documentos
formatados, caminhos Windows/UNC e campos comuns de credenciais. Essa heurística
não constitui anonimização completa. A aplicação não acessa caminhos do cliente
nem executa instruções ou conteúdo recebidos em anexos.

O histórico registra respostas, correções, recebimento/reutilização de anexos,
indisponibilidade, desconsideração de anexo e encerramento da coleta. Desconsiderar
um anexo retira seus achados do estado atual e conserva o evento de auditoria.

## API

| Método e rota | Uso |
| --- | --- |
| `GET /triage/models` | Modelos disponíveis. |
| `GET /triage/sessions` | Sessões do usuário autenticado. |
| `POST /triage/sessions` | Criar com `model_id` e `problem`. |
| `GET /triage/sessions/{id}` | Retomar a sessão com perguntas, respostas, evidências e histórico. |
| `POST /triage/sessions/{id}/actions` | Enviar `version`, `operation` e os campos da operação. |
| `POST /triage/sessions/{id}/attachments` | Multipart com `version`, `request_id`, `occurrence_confirmed` e `file`. |

Operações: `answer` (`question_id`, `value`, nulo significa não informado),
`unavailable` (`request_id`, `reason`), `remove_attachment` (`attachment_id`)
e `handoff`. Respostas antigas conflitantes retornam 409; sessões inacessíveis
retornam 404; formato de anexo não suportado retorna 415; excesso de tamanho, 413.

## Verificação realizada

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

49 testes passaram: 20 do importador e 29 de triagem. A integração Flask foi
verificada com autenticação simulada e dados sintéticos, sem acesso ao Firebase
real ou aos clientes. O fluxo também foi exercitado no Edge: criação, perguntas
condicionais, upload, divergência/correção, deduplicação e retomada, incluindo
verificação de largura de celular e ausência de erros JavaScript.

A dependência `tzdata` foi incluída porque a aplicação usa `America/Sao_Paulo` e
precisa desses dados de fuso horário no Windows.

## Integração com a busca local — item 6

A sessão oferece **Pesquisar no acervo com o contexto desta triagem**. O acesso
ao contexto continua restrito ao proprietário da sessão, mesmo que o acervo seja
compartilhado entre atendentes. A busca combina o relato com a versão e o texto
de alarme, quando disponíveis; essa pesquisa local não transmite dados para APIs externas.
Os resultados são trechos com fontes. Uma ação separada permite gerar a resposta
com Gemini quando [configurado no servidor](gemini.md).
Preparação, atualização e limites estão em [Busca local](busca-local.md).
