# Water Network Auditor — GIS & WaterGEMS

Ferramenta Python/PyQGIS para auditar fronteiras espaciais, examinar a conectividade
de modelos Bentley WaterGEMS e acompanhar investigações técnicas no QGIS.

O fluxo de trabalho é **detectar → localizar → investigar → decidir → propor →
validar**. A ferramenta **não altera automaticamente modelos WaterGEMS ou dados GIS**.
Proximidade, cruzamento e pertencimento ao mesmo componente não comprovam conexão
hidráulica direta nem irregularidade operacional.

## Funcionalidades disponíveis

A versão **1.3.1** corrige o contrato de encerramento do QGIS, centraliza a resolução
de pendências e refina a navegação e o registro rápido. Consulte o
[guia de estabilidade, roteiro de aceitação e plano de finalização](documentacao/publica/ESTABILIDADE_E_FINALIZACAO.md).

- Múltiplas redes e limites, com campos e modos de análise configuráveis.
- Transição entre regiões e perímetro individual, inclusive áreas aninhadas/sobrepostas.
- Travessias, tangências, extremidades, coincidências, continuidades potenciais e ambiguidades.
- Eventos individuais preservados e agrupamento conservador em locais de investigação.
- Interface PyQt, seleção cruzada e painéis de evidências e diagnósticos no mapa.
- Leitura SQLite somente leitura, cenários/alternativas, directed nodes e componentes.
- Perspectivas ESTRUTURAL e TODAS_VALVULAS_ABERTAS, com restrições documentadas.
- Bases topológicas persistentes, snapshots consistentes, versões e comparação de conteúdo.
- Integração GIS × WaterGEMS por correspondências explicitamente verificadas.
- Revisões, conclusões, propostas sem execução automática e histórico persistente.
- Exportações GPKG, SHP e XLSX; tabelas técnicas JSON/CSV conforme a operação.

## Requisitos

Ambiente validado: **Windows 64 bits, QGIS 3.44.15-Solothurn / Python 3.12**.
Utilize o Python do QGIS: um Python independente normalmente não contém PyQGIS.
São utilizados PyQt, NetworkX e openpyxl, além das bibliotecas padrão. Veja
[dependências e atribuições](THIRD_PARTY_NOTICES.md). Verifique a disponibilidade
no seu ambiente antes de instalar dependências; o complemento não instala pacotes.

## Instalar o complemento

Este repositório contém os fontes; o ZIP é gerado localmente, sem modelos ou dados.
Na raiz do clone, execute com o Python do QGIS:

```text
python testes/empacotar_plugin.py dist/WaterNetworkAuditor.zip
```

O diretório `dist` precisa existir. No Windows, o comando pode ser executado no
OSGeo4W Shell da instalação QGIS. Não use um Python sem os módulos do QGIS para
executar a aplicação ou a suíte de processamento.

No QGIS: **Complementos → Gerenciar e instalar complementos → Instalar a partir
do ZIP**. Selecione o arquivo gerado e habilite **Auditoria de Redes — GIS &
WaterGEMS**. Abra pelo ícone ou menu e escolha a pasta de trabalho.
Não é necessário configurar manualmente PYTHONPATH ou utilizar o console QGIS.
Após atualizar um complemento cujas bibliotecas já foram carregadas, reinicie o QGIS.

## Uso inicial

1. Carregue no QGIS suas camadas autorizadas de rede e limites.
2. Escolha **NOVA AUDITORIA**, selecione redes, polígonos, campos e modos por camada.
3. Confirme CRS métrico e tolerâncias, execute e examine os resultados temporários.
4. Salve um GPKG novo para continuar posteriormente. Entradas concluídas ficam protegidas.
5. **CONTINUAR AUDITORIA** recupera resultados; **REGERAR LOCAIS** refaz apenas o
   agrupamento; **REPROCESSAR AUDITORIA** permite mudanças que afetam eventos.

Para integrar um modelo, use **ANALISAR COM WATERGEMS…** a partir de uma auditoria
concluída. Selecione um `.wtg.sqlite` salvo, nome amigável, projeto, cenário e
perspectiva. **Criar nova versão persistente…** produz a fotografia topológica.
CRS e unidades exigem evidência explícita; não são deduzidos pelo nome do município.

**ABRIR BASE WATERGEMS EXISTENTE…** permite consultar sem o modelo original.
**ATUALIZAR BASE WATERGEMS…** compara o conteúdo e cria uma versão nova quando
necessário, mantendo a anterior. O catálogo identifica bases por UUID, permite
filtros e relocalização de arquivos; nomes de arquivos não constituem identidade.

Escolha os campos GIS a confrontar com Label WaterGEMS. A prova exige unicidade
bilateral e compatibilidade geométrica; candidatos ambíguos não são escolhidos
automaticamente. A investigação resultante conserva as versões exatas de origem.

No painel, selecione uma ocorrência e consulte mapa, resumo e detalhes expansíveis.
Em **ANÁLISE E DECISÃO**, registre situação administrativa, conclusão explícita,
justificativa e evidências. Propostas possuem aprovação e validação independentes.
`VERIFICADO` não significa problema corrigido; `APLICACAO_INFORMADA` apenas declara
uma intervenção externa. Reabra a mesma investigação pelo catálogo para continuar.

## Arquitetura e documentação

```text
complemento_qgis/auditoria_redes/  # classFactory, metadados, ícone e ciclo do plugin
scripts/auditoria_aplicacao/      # fluxo unificado, catálogo e consulta
scripts/auditoria_fronteiras/     # geometria, agrupamento, GUI, revisão e exportação
scripts/auditoria_topologica_watergems/ # leitor, grafo, integração, decisões e bases
testes/                          # fixtures sintéticas e testes PyQGIS
documentacao/publica/            # documentação revisada para publicação
```

- [Uso e instalação](documentacao/publica/USO.md)
- [Arquitetura geométrica](documentacao/publica/ARQUITETURA_GEOMETRICA.md)
- [Arquitetura topológica](documentacao/publica/ARQUITETURA_TOPOLOGICA.md)
- [Integração, diagnósticos e decisões](documentacao/publica/INTEGRACAO_DECISOES.md)
- [Persistência e versionamento](documentacao/publica/PERSISTENCIA_VERSIONAMENTO.md)
- [Desenvolvimento, testes e validação manual](documentacao/publica/DESENVOLVIMENTO.md)
- [Histórico técnico publicável](documentacao/publica/HISTORICO.md)
- [Roadmap de engenharia](documentacao/Roadmap_01_Processo_Topologia_WaterGEMS.pdf)
- [Roadmap de ferramentas](documentacao/Roadmap_02_Desenvolvimento_Ferramentas_WaterGEMS.pdf)

Os roadmaps são registros de planejamento datados. Funcionalidades planejadas não
devem ser confundidas com a lista implementada acima. Documentos operacionais e
exemplos reais são mantidos fora desta distribuição pública.

## Testes

Com o Python do QGIS, na raiz do clone:

```text
python -m unittest discover -s testes -p "test_*.py" -v
```

As fixtures são geradas em memória ou temporários, sem distribuição de cadastro real.
A execução offscreen verifica processamento e widgets, mas não substitui aceitação
interativa. O empacotador valida a composição do ZIP por manifesto SHA256.
Na preparação pública, os [419 testes da cópia limpa passaram](documentacao/publica/VALIDACAO_PUBLICACAO.md).
Instruções para revisão de publicação: [segurança](SECURITY.md).

## Limitações atuais

A versão 1.3.0 acrescenta [registros investigativos simples e organização de camadas](documentacao/publica/FLUXO_INVESTIGATIVO.md),
com fechamento automático do assistente espacial, anotações/preliminares e grupos por execução.

A versão 1.2.1 corrige a [inicialização e recuperação do catálogo de bases](documentacao/publica/RECUPERACAO_CATALOGO.md),
incluindo abertura do assistente com índice vazio e preservação das bases existentes.

Na versão 1.2.0, [Validar referência espacial do WaterGEMS](documentacao/publica/VALIDACAO_ESPACIAL.md)
detecta metadados, recomenda campos GIS, testa unidades e compara geometrias em um
assistente. A aprovação técnica gera evidência persistente e nova versão da base.

O [guia de usabilidade e validação espacial](documentacao/publica/USABILIDADE_CRS.md)
documenta as tabelas de inspeção, dimensionamento das janelas e confirmação de CRS/unidades.

- ESTADOS_DO_CENARIO permanece bloqueado; estados iniciais não são estados simulados.
- Bombas e retenções mantêm restrições próprias; válvulas abertas não comprovam operação.
- Sem CRS/unidades comprovados, integração espacial e SHP real permanecem bloqueados.
- Extração e análise completa ainda exigem memória e espaço proporcionais ao modelo.
- Fontes GIS movidas podem exigir relocalização antes de repetir a prova cadastral.
- A validação desktop anterior verificou ações pela API em perfil isolado; a aceitação
  por cliques e o encerramento normal do processo permanecem verificações manuais.
- Associação espacial genérica de equipamentos aos locais e telemetria seguem no roadmap.

## Segurança, colaboração e licença

Dados operacionais, modelos, resultados, credenciais e configurações pessoais não
fazem parte do repositório. `.gitignore` é uma proteção adicional, não substitui
revisão de conteúdo/histórico. Originais locais não são apagados ao serem ignorados.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).
**Ainda não foi definida uma licença para este projeto.** A disponibilidade pública
do código não equivale a uma concessão de licença open-source. Dependências e
referências de terceiros conservam seus próprios direitos e condições.
