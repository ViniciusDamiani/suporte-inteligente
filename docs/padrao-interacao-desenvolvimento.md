# Padrão futuro: interação de desenvolvimento

Quando o setor de software alterar o produto por causa de um ticket, registrar uma interação técnica legível no próprio chamado. Ela explica a mudança de forma que o suporte consiga consultá-la sem abrir o GitLab. O commit continua como evidência rastreável, quando houver acesso.

## Encaixe no histórico

- Manter `interacoes.tipo` com os valores atuais `A` (atualização), `D` (interna) e `F` (atualização de fechamento). **Não criar outro significado para esse campo.**
- Acrescentar `subtipo = desenvolvimento` (ou campo equivalente) às interações futuras. Na ausência de campo próprio no software de tickets, usar um cabeçalho padronizado no texto: `[DESENVOLVIMENTO]`.
- Registrar a nota como interna (`D`) quando contiver detalhes de implementação. Uma atualização para o cliente (`A` ou `F`) pode resumir o resultado em linguagem apropriada, ligada à nota interna.
- Preservar autor, data, ticket e destinatário. Os filtros atuais de grupos continuam valendo. Não aplicar automaticamente o novo subtipo ao histórico antigo.

## Conteúdo mínimo da nota

| Campo | O que informar |
| --- | --- |
| Problema ou pedido | Sintoma/requisito específico atendido por esta alteração. |
| Mudança implementada | Comportamento anterior e novo comportamento, ou regra modificada, em linguagem compreensível ao suporte. |
| Local da alteração | Produto, módulo, tela, serviço ou relatório; arquivos/rotinas quando ajudarem a localizar a mudança. |
| Teste e resultado | O que foi executado e qual resultado foi observado. Se não houve teste, registrar isso explicitamente. |
| Estado de entrega | `implementado`, `integrado`, `implantado` e `validado pelo cliente` como fatos separados, cada um com data/fonte quando conhecida. |
| Rastreabilidade | SHA(s) dos commits, MR e versão/release quando disponíveis. Um ticket pode ter vários commits. |
| Limitações | O que ficou pendente, condição em que a mudança vale ou risco conhecido. |

O ID do ticket, autor e horário devem vir preferencialmente do próprio sistema. O SHA, MR e versão são metadados da interação; se o sistema não tiver campos para eles, podem constar no texto em formato consistente. Não copiar o diff inteiro nem credenciais para a interação.

## Modelo de texto quando só houver campo livre

```text
[DESENVOLVIMENTO]
Problema/pedido: <sintoma ou requisito deste ticket>
Alteração realizada: <o que mudou no comportamento>
Componente: <produto, módulo, tela/serviço/relatório>
Teste realizado: <cenário e resultado; ou "não informado">
Estado: implementado <sim/não/desconhecido>; integrado <sim/não/desconhecido>;
        implantado <sim/não/desconhecido>; validado pelo cliente <sim/não/desconhecido>
Revisão: <SHA(s) e MR, se houver>
Versão: <versão/release, se comprovada>
Pendências/limites: <informação ou "nenhuma informada">
```

## Como essa interação alimenta o RAG

O importador reconhece o subtipo/cabeçalho, guarda os campos estruturados e liga o texto original ao ticket. A preparação de casos usa a nota como **evidência de implementação**; as interações de teste e validação continuam como evidências separadas de resultado. A ficha de conhecimento cita o ID da interação e, quando disponível, o commit. Se a nota divergir do diff ou das demais interações, o caso fica pendente de revisão técnica.

Uma futura automação pode propor a nota a partir da mensagem e do diff do commit, mas o responsável pelo desenvolvimento revisa antes de publicá-la no ticket. Assim, consultas posteriores usam a ficha armazenada na plataforma sem acessar o GitLab durante o atendimento.
