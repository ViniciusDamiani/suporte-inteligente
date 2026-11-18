# Item 3 — Preparação e importação de conhecimento

Implementação local em `knowledge_import/`, compatível com Python 3.10 ou superior,
usando apenas a biblioteca padrão. Recebe o pacote normalizado JSON/JSONL descrito
em `DataSetBase/LEIA_PRIMEIRO_IMPORTACAO.md`.

## Entrada e preparação

O ponto de entrada é `DataSetBase/CATALOGO_IMPORTACAO.json`, que aponta para o
catálogo da versão. Também é possível passar diretamente o `catalogo_importacao.json`
do pacote. O importador carrega somente entradas com `importar: true`.

JSONL é JSON com um objeto por linha. A estrutura esperada é a do pacote preparado:
fontes, entidades com envelope v1, vínculos e recursos auxiliares de banco. Um JSON
arbitrário exportado do sistema de tickets precisa ser convertido para esse contrato
antes da carga. Os geradores anteriores de planilhas/CSV estão no
[arquivo de preparação](../../suporte-inteligente-arquivo-2026-10-31/dataset/README.md);
esta implementação começa no pacote normalizado já existente. Consulte a
[organização após a limpeza](organizacao-repositorio.md) para localizar as origens.

A preparação verifica tipos e representação canônica para comparação. Preserva
o conteúdo técnico, acentuação, datas desconhecidas, strings vazias, valores nulos,
revisões e metadados. Não preenche datas nem transforma um caso pendente em solução
confirmada. `conteudo_sha256` deve ser o SHA-256 de `dados`, serializado com chaves
ordenadas, UTF-8, `ensure_ascii=False` e separadores `(',', ':')`.

## Uso no Windows

Na pasta `C:\Projeto\suporte-inteligente`, com Python instalado:

```powershell
py -3 -m knowledge_import validar
py -3 -m knowledge_import importar --relatorio instance\carga-001.json
py -3 -m knowledge_import status
py -3 -m knowledge_import historico
```

Se o inicializador `py` não estiver disponível, execute o `python.exe` instalado.
Nesta máquina foi utilizado:

```powershell
& 'C:\Users\vinicius.damiani\AppData\Local\Programs\Python\Python312\python.exe' -m knowledge_import status
```

`validar` usa somente uma base temporária e não altera nem cria o banco de destino.
`importar` valida novamente e ativa a carga inteira. A saída é JSON; o progresso
vai para a saída de erros. Código de saída 0 indica sucesso; 1 indica rejeição/erro.
O relatório deve ter nome novo e ficar fora da pasta do catálogo.

Para outra versão ou outro destino:

```powershell
py -3 -m knowledge_import importar --catalogo CAMINHO\catalogo_importacao.json --banco instance\knowledge.sqlite3 --operador nome-do-responsavel --relatorio instance\carga-002.json
```

## Reabastecimento da base

1. Preparar uma nova exportação completa em JSON/JSONL, mantendo os IDs estáveis.
2. Gerar outra versão do pacote e seu catálogo, com contagens, bytes e hashes dos arquivos atualizados. O importador não gera o catálogo da exportação.
3. Executar `validar --catalogo ...` e corrigir eventuais erros.
4. Executar `importar --catalogo ...` e conferir o relatório.

O relatório apresenta incluídos, atualizados, inalterados, retirados e retirados
da pesquisa para cada destino. A comparação usa o registro inteiro, incluindo
metadados: mudar a elegibilidade provoca atualização mesmo que `dados` e seu hash
sejam iguais. Somente `disponivel_pesquisa: true` marca elegibilidade explícita;
ausência desse campo não concede elegibilidade. Esse marcador não equivale à
autorização de um usuário nem à existência de um índice de busca.

Repetir o mesmo pacote ativo valida os arquivos e registra uma execução
`sem_alteracoes`, reutilizando o snapshot e suas revisões. Alterar silenciosamente
uma versão já carregada é rejeitado. Reimportar uma versão histórica também é
rejeitado: para uma restauração deliberada, preparar uma nova versão completa.

Registros ausentes na nova versão deixam a visão ativa; o histórico permanece.
Cargas parciais são recusadas para evitar retiradas por exportações incompletas.
O catálogo deve representar fielmente a exportação completa: o importador não
consulta a origem para descobrir registros omitidos pelo exportador.

## Validações

- Versão do contrato, modo completo, destinos e formatos reconhecidos.
- Arquivos declarados, tamanho, SHA-256 e contagens, incluindo totais do catálogo.
- JSON UTF-8, sem chaves duplicadas, números não finitos ou linhas JSONL vazias.
- Envelope, campos obrigatórios, tipos, IDs únicos e hash dos dados.
- Restrições do contrato v1: acesso obrigatório, revisão preservada e indexação não executada.
- Existência das duas pontas de cada vínculo normalizado entre fontes e entidades.
- Caminhos de carga dentro do pacote; referências de procedência são armazenadas como texto e não são abertas.

O processamento para no primeiro erro e devolve motivo, arquivo e linha quando
aplicáveis. A carga completa é rejeitada; não há aceitação parcial. Corrigir a
origem e gerar uma nova exportação antes de tentar novamente. A validação cobre
a estrutura e os vínculos normalizados; interpretação semântica de perguntas,
condições e anexos pertence ao item 4.

Limites por arquivo: catálogo 4 MiB, linha JSONL 16 MiB e recurso auxiliar JSON
64 MiB. Os JSONLs são lidos progressivamente; os registros são preparados em banco
temporário em disco, apagado ao encerrar a execução normal.

## Armazenamento e integração futura

O banco local fica em `instance/knowledge.sqlite3`, fora do Git. SQLite foi usado
como armazenamento de preparação para permitir validar a carga real sem depender
de credenciais ou alterar as coleções existentes no Firestore. A integração desse
acervo com a aplicação e o armazenamento de produção permanece como decisão do
item 6. A busca atual da aplicação continua consultando sua base existente.

Tabelas:

| Estrutura | Finalidade |
| --- | --- |
| `revisions` | Conteúdo por pacote, ID e hash completo; versões inalteradas são reutilizadas. |
| `snapshots` | Catálogo, versão, instante de importação e relatório de cada snapshot. |
| `membership` | IDs e revisões que integram cada snapshot. |
| `active_packages` | Ponteiro para a versão ativa de cada pacote. |
| `import_runs` | Execuções, operador local, resultado e falhas. |
| `active_records` | Visão consistente dos registros da versão ativa. |

As gravações e a troca da versão ativa ocorrem na mesma transação, depois da
validação completa. Falhas de escrita desfazem a transação. Escritores concorrentes
são serializados pelo SQLite. A auditoria de falhas é gravada quando o armazenamento
está disponível; `auditoria_persistida: false` informa quando isso não foi possível.
O operador registrado é o usuário local ou `--operador`, sem autenticação remota.

O acesso ao arquivo é administrativo, controlado pelo sistema operacional. Não há
rota pública de consulta a esses dados. O código futuro que consumir a visão ativa
deverá aplicar as permissões do usuário antes de exibir conteúdo ou enviar dados
a modelos. Esta entrega não gera embeddings, não executa conversas e não chama
serviços externos.

Atualização do item 6: o módulo `knowledge_search` consome a visão ativa em modo
de leitura e oferece a busca autenticada no acervo. `importar --atualizar-busca`
também prepara o índice local após a carga, desde que o modelo esteja instalado.
Se a atualização do índice falhar, a carga concluída é preservada e o comando
retorna `2`. Consulte [instalação e atualização da busca](busca-local.md).

## Verificação

```powershell
py -3 -m unittest discover -s tests -v
```

A suíte usa dados sintéticos e cobre carga inicial, repetição, atualização,
retirada, alteração somente de metadados, histórico, falha de ativação, isolamento
entre pacotes, caminhos indevidos, corrupção, IDs duplicados e vínculos órfãos.

A carga local do pacote 1.0.0 conciliou 87.418 entidades, 172.224 vínculos,
61 fontes e quatro recursos auxiliares. O relatório está em
`instance/relatorio-primeira-carga.json`; a repetição fica em
`instance/relatorio-reimportacao.json`.
