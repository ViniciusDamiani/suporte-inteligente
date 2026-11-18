# Política de uso dos tickets na pesquisa e recomendação

Versão 1.0. Aplicada em 30/10/2026 ao arquivo `00_associacoes_ticket_problema_solucao.csv`.

Os tickets elegíveis permanecem disponíveis para pesquisa mesmo sem solução. A classificação descreve a evidência existente e não constitui aprovação técnica de uma ação para um novo atendimento. Não Procedentes e interações dos grupos ENVIO DE ACEITE, BACKUPS e ASSESSORIA continuam excluídos conforme a preparação anterior. Esta edição não reimporta fontes excluídas.

## Campos acrescentados

| Campo | Interpretação |
| --- | --- |
| disponivel_pesquisa | `sim` permite integrar a pesquisa, condicionado às permissões da aplicação. Não concede acesso público ou entre clientes. |
| nivel_evidencia_solucao | Relato sem solução documentada; investigação ou ação candidata; ação/orientação documentada; ação com resultado documentado. Não é escala de probabilidade ou aprovação. |
| estado_resultado | Distingue resultado desconhecido, teste sem aprovação explícita, teste inicial, TAF, resultado observado, parcial, com ressalva ou desfecho pendente. |
| uso_na_recomendacao | `contexto_historico`, `hipotese_para_investigacao`, `acao_historica_condicionada` ou `resultado_historico_condicionado`. Descreve como citar a fonte, não autoriza execução. |
| aplicabilidade_ao_caso_atual | `nao_avaliada_para_nova_ocorrencia`. Deve ser avaliada a cada atendimento, considerando cliente, processo, versão, configuração e evidências. |
| autores_interacoes | Logins distintos encontrados nas interações preservadas, separados por ` | `. Inclui autores sem correspondência no cadastro de técnicos. |
| tecnicos_identificados | Pares `login: nome` com correspondência exata no cadastro exportado de técnicos. Lista não exaustiva do atendimento original; exclui interações removidas anteriormente. |
| motivo_classificacao | Explica a evidência e a ressalva que determinaram a classificação. |
| versao_politica_uso | Versão da política de classificação, atualmente `1.0`. |
| data_classificacao | Data da classificação derivada; não é data da ocorrência, solução, implantação ou revisão técnica. |

## Regras de interpretação

- A classificação foi derivada dos estados e interpretações já presentes. Não equivale a uma nova leitura semântica integral de todos os atendimentos.
- `sem_solucao_identificada_por_regra` torna-se `relato_sem_solucao_documentada`. A extração não localizar solução não comprova inexistência dela no histórico integral.
- `acoes_candidatas_para_analise`, diagnóstico com ação insuficiente e hipótese de RIT não confirmada tornam-se `investigacao_ou_acao_candidata`.
- Orientações e corretivas com desfecho pendente, teste sem resultado explícito, implantação parcial ou ressalvas ficam como `acao_ou_orientacao_documentada`.
- Testes com resultado documentado, TAF, testes iniciais e resultados observados ficam como `acao_com_resultado_documentado`, acompanhados do estado específico de resultado e das limitações. TAF não comprova implantação. Resultado histórico não comprova aplicabilidade futura ou eficácia duradoura.
- Um campo `resultado_documentado` preenchido pode registrar ausência de comprovação. A presença de texto, o fechamento do ticket ou o carregamento de uma versão nunca são usados isoladamente como confirmação de solução.
- Participação em interação não prova autoria de diagnóstico, execução da corretiva ou responsabilidade pelo desenvolvimento. A atribuição de uma ação depende de sua evidência específica.
- Os logins vêm de `observacao` (`autor=...`) das evidências tipo `interacao`, agrupadas por `ticket_origem`. Os nomes vêm da correspondência exata com `login` em `tecnicos (1).csv`. Evidências e cadastro permanecem inalterados.
- Cada linha mantém o `caso_id` original. Tickets conhecidos por conter várias ocorrências mantêm essa ressalva. Esta classificação não desmembra automaticamente problemas nem atribui o resultado de uma ocorrência às demais.
- O cliente original foi preservado, inclusive aliases. Não foram inferidas correspondências entre aliases e números reais de cliente.

## Uso pela futura aplicação

Uma ocorrência sem solução pode ser apresentada como precedente, identificando cliente e participantes. Uma tentativa pode ser mencionada como hipótese ou investigação, inclusive quando falhou. Ações documentadas podem ser descritas como ações históricas, com suas ressalvas.

Para recomendar uma ação ao novo atendimento, a aplicação precisa avaliar as evidências e a aplicabilidade. Quando houver lacunas, deve solicitar informações ou anexos específicos. Uma orientação baseada em regra de processo ou outro ticket deve citar essa outra fonte; não deve ser atribuída ao ticket sem solução.

Os campos originais `estado_revisao`, `estado_associacao`, `estado_implantacao` e `apto_recomendacao_automatica` foram preservados. O último continua como indicador legado de aprovação automática, distinto de disponibilidade para pesquisa. Nenhuma linha foi automaticamente homologada nesta alteração.

## Integridade e histórico

Foram acrescentadas dez colunas ao final, mantendo ordem dos registros, IDs, valores originais, delimitador ponto e vírgula, codificação UTF-8 com BOM e campos entre aspas. Os vínculos e arquivos de evidências não foram editados.

O manifesto `00_controle_classificacao_tickets.json` registra contagens, verificações e hashes. A cópia anterior fica em `_historico/classificacao_tickets_v1_2026-10-30/00_associacoes_ticket_problema_solucao.csv.bak`. A pasta `_historico` é arquivo de auditoria e deve ficar fora da ingestão RAG.
