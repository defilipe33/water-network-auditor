# Continuidade dos projetos no Water Network Auditor 1.17.2

## Abrir e continuar

No menu **⋯** do Quadro do Modelo, use **Novo projeto (.wna)…** e escolha a pasta que receberá o novo projeto. Para retomar um projeto em outra sessão, use **Abrir projeto (.wna)…** e escolha o arquivo centralizador. O cabeçalho exibe o último trabalho salvo. **Continuar último trabalho** abre o resultado desse trabalho e, quando disponíveis, recupera filtros, ordenação, seleção, destaques, camadas temáticas próprias e enquadramento.

Em **Investigar minha rede**, **Abrir análise de conectividade salva…** lista as execuções anteriores. **Execuções desta hipótese**, no painel de conectividade, restringe a lista à hipótese escolhida e mostra a revisão usada em cada execução. Abrir uma execução restaura sua configuração histórica. **Salvar revisão da hipótese** grava uma configuração. **Executar e salvar** inicia o cálculo e registra uma nova execução.

Em **Meus trabalhos**, pesquise por nome, hipótese e outros metadados da execução. Use o menu da linha para abrir, destacar, localizar o arquivo ou consultar o histórico e as dependências. A última abertura aparece em coluna própria. Consultar uma execução antiga conserva a referência ao último trabalho salvo.

## Projetos anteriores

Selecione o projeto antigo e use **⋯ → Organizar projeto existente…**. Para criar apenas o manifesto, mantenha os arquivos onde estão. Para levar os arquivos de trabalho a uma nova pasta, escolha **Criar cópia portátil em nova pasta**. A operação conserva as identidades, verifica os bancos vinculados e grava uma cópia das referências anteriores em `backups/`.

As opções **Mostrar localização do projeto**, **Abrir pasta do projeto**, **Copiar caminho do projeto** e **Consultar arquivos vinculados…** indicam onde o manifesto e os bancos foram gravados. Se um banco tiver sido movido, escolha **Localizar arquivo…** no trabalho correspondente. A recuperação verifica o tipo, o UUID, o esquema e as identidades disponíveis no arquivo. **Recuperar trabalhos sem referência…** lista resultados reconhecidos como pertencentes ao projeto nas pastas pesquisadas. O vínculo é criado após a escolha do resultado.

## Arquivos do projeto

| Caminho | Conteúdo |
| --- | --- |
| `Nome.wna` | Identidade, referências aos GeoPackages, Modelo GIS, mapeamentos e último trabalho salvo. |
| `modelo/` | Banco de complementos e revisões de hipóteses, quando criado. |
| `analises/conectividade/` | Execuções e fotografias topológicas. |
| `analises/estruturantes/` | Investigações estruturais e corredores agrupados. |
| `analises/auditorias/` | Novos dossiês de auditoria GIS salvos no projeto. |
| `estado/` | Visualização e rascunhos separados por identidade de projeto. |
| `backups/` | Manifestos com referências anteriores, criados durante a organização. |

As pastas de dados são criadas conforme o uso. Para exportações, escolha a pasta de destino nos exportadores. Os vínculos internos são relativos à pasta do manifesto. O arquivo centralizador não duplica as fotografias dos GeoPackages. O índice local mantém a lista de projetos recentes.

As fontes GIS externas permanecem referenciadas. Se elas mudarem de caminho, use a relocalização no **Modelo GIS**. É possível consultar resultados históricos com geometrias próprias mesmo com esses arquivos indisponíveis. Para recalcular, recupere as fontes exigidas pelo Modelo GIS. O arquivo de projeto do QGIS (`.qgz`) continua sendo o local para estilos personalizados, camadas externas e outras preferências do mapa.

## Integridade e compatibilidade

O complemento usa UUID e tipo de trabalho para resolver as referências. Os novos GeoPackages GIS incluem um resumo leve para listagem. As fotografias `TG_EXECUCAO` e `TG_ESTRUTURA` permanecem legíveis. Em trabalhos antigos sem preferências de visualização, a interface usa a apresentação padrão. Trabalhos antigos sem identidade explícita de projeto podem ser conferidos pelos vínculos existentes, com recuperação automática de órfãos limitada aos arquivos cuja identidade esteja registrada.

Ao sair de uma hipótese com alterações pendentes, é possível salvar a revisão, descartar as alterações ou preservar o rascunho. O rascunho fica no estado do projeto e é recuperado separadamente da execução histórica.

A validação da 1.17.2 usa projetos sintéticos em perfis isolados do QGIS Desktop 3.44.15, incluindo retomada após reinício, abertura de trabalhos das versões 1.16.0 a 1.17.1 e consulta de uma cópia portátil deslocada com as fontes externas indisponíveis.
