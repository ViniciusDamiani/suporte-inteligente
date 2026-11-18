# Evidencias de codigo-fonte no RAG de suporte

Esta etapa liga tickets e interacoes a revisoes de codigo para descrever correcoes e melhorias realizadas. Os repositorios sao organizados **por cliente**; dentro do repositorio do cliente, a mensagem do commit aponta para um ou mais tickets. O codigo e uma **fonte adicional de evidencia**: um commit mostra o que mudou; interacoes, testes, merge e implantacao ajudam a dizer se a mudanca resolveu o problema no ambiente do cliente.

A [ficha de conhecimento versionada](documentacao-conhecimento.md) e gerada em uma carga separada do atendimento. A busca do usuario le as fichas no banco da plataforma; nao acessa o GitLab em tempo real.

## O que o piloto mostrou

Foi possivel encontrar um ticket da base em uma mensagem de commit e comparar assunto, interacoes e diff. A mensagem e uma interacao descreviam a mesma melhoria de relatorio, e o diff mostrava a inclusao do campo correspondente. A merge request reunia commits de varios tickets; portanto, o titulo da MR ou o nome da branch nao podem atribuir todas as alteracoes a um unico ticket. O diff tambem inclui arquivos de configuracao e artefatos gerados que criam muito volume sem explicar a regra de negocio. Nenhum codigo privado ou identificador de cliente e copiado para este documento.

## Modelo complementar

| Entidade | Campos principais | Papel |
| --- | --- | --- |
| `source_repositories` | ID GitLab ou caminho local, `client_id` proprietario, projeto, modulo, visibilidade, origem, ultimo commit importado | Cada repositorio e cadastrado sob um cliente. Se o cliente tiver projetos `Sources` e `Dev`, ambos apontam para o mesmo `client_id`. |
| `code_revisions` | repositorio, SHA completo, pais, autor, datas, mensagem, branch/tag, MR, estado | Um commit pode citar varios tickets; um ticket pode ter varios commits. SHA + repositorio identificam a revisao. |
| `ticket_revision_links` | ticket, revisao, origem do vinculo (`mensagem`, `branch`, `MR`, `manual`), trecho que cita o ID, confianca, estado de revisao | A citacao explicita na mensagem e um vinculo forte quando o ticket pertence ao cliente do repositorio. Divergencia de cliente vira pendencia de revisao; nome de branch/MR e apenas pista. |
| `code_change_evidence` | revisao, arquivo, tipo de mudanca, trecho/linhas ou referencia ao diff, resumo tecnico, estado da revisao humana | Descreve *o que mudou* com rastreabilidade. Nao precisa armazenar o repositorio inteiro no banco RAG. |
| `delivery_evidence` | revisao, MR, branch de destino, tag/versao, teste, implantacao, ambiente, data, fonte | Distingue codigo escrito, aprovado, mesclado, liberado e validado no cliente. Ausencia de evidencia permanece desconhecida. |

`knowledge_cases` passa a referenciar `evidence_interaction_ids` e, quando houver, `code_change_evidence_ids`. A descricao de problema continua sendo a entrada principal da busca. Um resumo verificado da mudanca pode enriquecer a resposta, sempre com link para ticket, interacao, commit e arquivo de origem. A indisponibilidade de codigo nao impede a criacao do caso a partir das interacoes.

## Fluxo de processamento

1. Cadastrar o `client_id` de cada repositorio do cliente, usando o ID do projeto GitLab ou o caminho local como identificador da fonte. Nao inferir o cliente pelo nome da branch ou pelo numero do ticket.
2. Dentro de cada repositorio, ler commits e MRs com acesso somente de leitura. Extrair IDs de ticket da mensagem completa, considerando variantes como `Ticket #123`, `Ticket#123` e multiplos IDs. Vincular somente tickets que pertençam ao cliente cadastrado; referencias a outros clientes ou IDs ausentes ficam para revisao.
3. Para cada vinculo confirmado, ler o diff daquele commit. Separar mudancas de comportamento de formatacao, arquivos gerados, binarios, publicacao e merges. Preservar arquivos e linhas originais para auditoria.
4. Gerar um rascunho estruturado: problema relatado; componentes alterados; comportamento anterior; mudanca implementada; possivel efeito; testes/validacao observados; incertezas e fontes. Nao afirmar que houve implantacao apenas porque existe commit ou MR mesclada.
5. Comparar o rascunho com as interacoes do ticket. Um revisor tecnico confirma ou corrige a interpretacao antes de tratá-la como conhecimento validado.
6. Indexar o texto do problema e guardar o resumo tecnico como evidencia de resposta. Em consultas futuras, a recomendacao cita as duas fontes e informa se o caso foi revisado.

## Dois modos de acesso

- **GitLab acessivel:** usar a API de projetos, commits, diffs e MRs com uma credencial especifica de leitura, configurada no servidor e fora do Git. Registrar cursor por projeto para buscar somente revisoes novas. A senha pessoal usada na inspeção manual nao deve virar credencial da integracao.
- **Codigo baixado pelo usuario:** manter o repositorio local com `.git` quando possivel e fornecer um manifesto privado com cliente, projeto, caminho, branch e intervalo de SHAs ou tags. Assim e possivel ler mensagens e diffs sem conectar ao GitLab. Se houver apenas duas copias dos arquivos, e possivel comparar versoes, mas nao atribuir com certeza cada alteracao a um commit ou ticket.

O banco guarda metadados, vinculos, resumos revisados e referencias. O codigo-fonte completo continua no GitLab ou no armazenamento local autorizado. Antes de enviar um diff a um provedor externo de LLM, definir quais repositorios podem sair do ambiente e remover segredos e dados sensiveis. Quando isso nao for permitido, usar analise local ou revisao humana.

## Entrega inicial sugerida

Escolher um repositorio e alguns tickets com vinculo explicito. Medir quantos tickets encontram commits, quantos vinculos sao corretos, quantos diffs geram uma explicacao tecnica util e quantos casos tem teste/implantacao comprovados. Depois automatizar a leitura dos demais repositorios. Tickets sem codigo acessivel seguem o fluxo de RAG baseado em interacoes.

## Referencias da API GitLab

- [Commits e diffs](https://docs.gitlab.com/api/commits/)
- [Merge requests e seus commits](https://docs.gitlab.com/api/merge_requests/)
- [Escopos de token de leitura](https://docs.gitlab.com/security/tokens/access_token_scopes/)
