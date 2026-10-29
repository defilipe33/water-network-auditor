# Histórico técnico publicável

## 1.10.0 — ilhas sem caminho até origem

Origens configuráveis, Tanks como hipótese explícita, busca multiorigem estrutural e dirigida sob restrições; grupos sem origem independentemente do tamanho. Inventário e candidatos, integração ao resultado/RESOLVIDO existentes, persistência/cache, comparação conservadora e relatórios. [Guia e aceitação](ILHAS_SEM_ORIGEM.md).

## 1.9.0 — restrições de percurso

Regras por tipo e equipamento, preferências lexicográficas, bloqueios em cópia do grafo, direção obrigatória das retenções, estados manuais identificados como hipóteses, perfis versionados e comparação/exportação completa. [Guia](RESTRICOES_CORREDORES.md).

## 1.8.1 — relatórios, Queries e acompanhamento

Relatório offline por padrão, prévia de um caso, fontes locais e alternativas seguras para serviços externos; localização cadastral/logradouros; Queries com nomes por tipo e índice. RESOLVIDO independente de diagnóstico, prioridade e resultado técnico, com fila Em aberto, resolver/avançar/reabrir, histórico, comparação conservadora e relatórios. [Guia](RELATORIOS_QUERIES_ACOMPANHAMENTO.md).

## 1.8.0 — exportação completa e catálogo

Elementos e percursos ordenados, Queries, catálogo com cópias de segurança separadas e relatórios ilustrados. [Guia](EXPORTACAO_CATALOGO_RELATORIOS.md).

## 1.7.0 — corredores e recuperação

Caminhos entre terminais e corredores multi-destino, sem inclusão automática de pontes; alternativas limitadas, métricas e continuidade. Recuperação explícita de análises em todas as perspectivas, filtros e páginas. [Guia](CORREDORES_E_RECUPERACAO.md).

## 1.6.0 — locais manuais e conjuntos de redes

Pontos sem eventos automáticos, associações explícitas, histórico e recuperação conservadora. Seleções cadastrais, pontes estruturais e corredores dirigidos, critérios combinados e conjuntos editáveis. Exportação CSV de identidades e seleção QGIS; criação nativa de Selection Sets no WaterGEMS ainda requer conferência. [Guia e limitações](LOCAIS_MANUAIS_E_REDES.md).

## 1.5.0 — investigação operacional e filtros

Resultado simples sem aprovação formal, motivos opcionais, fila de trabalho e
prioridades sugerida/manual. Filtros tipados por atributos e polígonos, E/OU e
qualquer/todos/nenhum, com estado indeterminado explícito. Extensão aditiva IGD,
backup verificado e histórico preservado. [Uso e arquitetura](ANALISE_OPERACIONAL_E_FILTROS.md).

## 1.4.1 — exportação pelos botões Qt

Correção das conexões clicked(bool) de comandos decorados de exportação, consulta e
comparação. Argumentos legítimos do decorador preservados. Regressões por clique,
formatos individuais/combinados, cancelamento, erro e reabertura.
[Detalhes e roteiro](CORRECAO_EXPORTACAO_1_4_1.md).

## 1.4.0 — janelas e acompanhamento

Menu de recuperação de interfaces por identidade, diálogos irmãos do QGIS e aviso
das transições intencionais. Indicador compartilhado por operação, cancelamento
cooperativo, progresso real ou indeterminado e distinção de etapa/publicação.
Reutilização do worker existente para reabrir investigações e comparar bases, com
publicação cartográfica na GUI. Inventário auxiliar reutilizado; guardas de saída
preservadas. [Uso, arquitetura e limitações](JANELAS_E_ATIVIDADES.md).

## 1.3.1 — estabilidade de saída e refinamento de uso

Implementação de `allowExit()` com autorização positiva, guarda central para o fluxo
integrado, proteção do uso independente, descarte sem repetição e prevenção de
reentrada. Navegação por ações, opções avançadas recolhidas, divisores ajustáveis e
salvamento rápido com avanço da lista. Algoritmos e estruturas persistidas preservados.
O [plano de finalização](ESTABILIDADE_E_FINALIZACAO.md) distingue validação automatizada,
aceitação humana e frentes futuras; a distribuição permanece experimental até aceite.

Este registro conserva a evolução do software sem reproduzir diagnósticos ou
identificadores de redes reais. Relatórios operacionais detalhados, exemplos reais
e documentos de contexto permanecem preservados somente no ambiente local.

1. Núcleo geométrico genérico e classificação de eventos, com testes sintéticos.
2. Modos de transição e perímetro individual e tratamento de polígonos sobrepostos.
3. Interface PyQt, camadas temporárias e apresentação legível com rastreabilidade separada.
4. Relatório XLSX e correção da estrutura de tabelas e autofiltros OOXML.
5. Locais de investigação com preservação dos eventos e limites de agrupamento.
6. Inspeção expansível, seleção cruzada, GPKG relacional, SHP e revisão persistente.
7. Reabertura, reagrupar sem recalcular eventos, reprocessamento e versões seguras.
8. Máquina de estados e proteção de configurações e revisões não aplicadas.
9. Leitura SQLite WaterGEMS, cenários/alternativas e resolução conservadora do grafo.
10. Confronto com referência externa, dispositivos e classificação de componentes.
11. Integração GIS × WaterGEMS, painel de diagnósticos e evidências no mapa.
12. Decisões técnicas, propostas sem execução, histórico e comparação de investigações.
13. Complemento convencional QGIS, bases topológicas completas no escopo do leitor,
    catálogo, atualização versionada, nomes livres e reabertura sem fonte original.
14. Preparação da distribuição pública: documentação genérica, exclusão de fontes
    operacionais, atribuições e revisão de segurança do conjunto enviado ao Git.

Os roadmaps aprovados são mantidos como documentos históricos. Algumas frentes,
como associação espacial genérica de equipamentos e telemetria, permanecem futuras.
O README descreve o que está implementado e as limitações vigentes.


## 1.8.0

Exportação dos elementos do percurso, consultas por tipo, catálogo com backups
separados, nome de exibição e recuperação reversível. PDF ilustrado e XLSX da
mesma seleção; fontes cartográficas e localização externa opcionais.
