# Ensaios do assistente espacial — 1.2.0

Ambiente: Windows, QGIS 3.44.15-Solothurn e Python 3.12 do QGIS.

- **532 testes aprovados**, incluindo os 467 anteriores e 65 novos, em 292,179 s.
- Cobertura adicional: CRS de GeoPackage/Shapefile/QGIS, projeto distinto da camada,
  metadados presentes/ausentes/inconsistentes, hipóteses de unidade, ranking cadastral,
  nulos/vazios/zeros, duplicidades, vértices, Junctions, precisão decimal, contexto
  alterado, aprovação explícita, JSON relacional, nova versão, anexos ausentes,
  cancelamento e proteção do contexto da interface.
- Ensaio real confirmou a hipótese de pé internacional diretamente nas coordenadas
  brutas, combinando metadados explícitos de CRS, comparação de vértices e um controle
  pontual independente fornecido pelo responsável. Divergências não foram eliminadas.
  Coordenadas, identificadores e relatórios operacionais permanecem somente locais.
- O piloto manteve 615 eventos, 459 locais, 17.243 tubulações e 508 componentes
  estruturais. Elementos e conexões foram comparados antes/depois da validação.
- QGIS desktop nativo em perfil isolado, escala Qt 150%: instalação do ZIP, detecção
  em thread, sete etapas, correspondências, hipóteses, mapa temporário e gravação em
  nova versão exercitados pela API Qt. Capturas examinadas.
- Outra sessão recuperou automaticamente evidência e fontes compatíveis sem repetir
  a comparação completa.
- O encerramento normal do processo desktop não concluiu no prazo do ensaio.
  A aceitação manual por cliques, a conferência independente no WaterGEMS e testes
  físicos de múltiplos monitores permanecem pendentes.

Os ensaios iniciais detectaram um handle SQLite não fechado no leitor novo; ele foi
corrigido com fechamento explícito. Fixtures GeoPackage passaram a ser preparadas
pelo provedor QGIS, que registra as funções espaciais exigidas pelos triggers.
Nenhuma alteração nos algoritmos foi feita para contornar testes.

O comparador de correspondências recebeu somente um callback opcional de cancelamento,
mantendo unicidade bilateral e comparação de todos os vértices. Núcleo geométrico,
agrupador, resolvedor topológico, estilos e roadmaps foram preservados.

Consulte o [guia e roteiro de aceitação](VALIDACAO_ESPACIAL.md) para os limites e
critérios. A versão 1.1.0 também integra esta publicação, pois ainda não estava no remoto.
