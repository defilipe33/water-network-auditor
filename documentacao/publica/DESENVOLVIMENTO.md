# Desenvolvimento e validação

Usar o Python do QGIS 3.44.15, com NetworkX e openpyxl disponíveis. A suíte
`python -m unittest discover -s testes -p "test_*.py" -v` cria fixtures sintéticas
em memória e em diretórios temporários. Escolher TEMP/TMP graváveis se o ambiente
estiver restrito; nunca direcionar temporários para uma fonte operacional.

O projeto não distribui cadastros, modelos, resultados ou dependências externas.
Os exemplos sintéticos usam coordenadas locais e identidades inventadas. Ensaios
privados dependentes de dados reais não fazem parte da suíte pública.

## Verificações automatizadas

- Núcleo geométrico: interseções, limites compartilhados/aninhados/sobrepostos,
  multipartes, tangência, extremidade, coincidência, ambiguidades e CRS.
- Agrupamento: compatibilidade, distâncias independentes, extensão e encadeamento.
- Identidades: repetição/nulidade de IDs, origem de camadas e preservação de relações.
- Persistência: revisões, histórico, concorrência, reconciliação, versões e backup.
- Topologia: cenários/alternativas, dispositivos, incidência, atividade e direcionalidade.
- Bases: snapshot WAL, cancelamento, falhas, reabertura sem fonte, paginação e assinatura.
- Saídas: reimportação SHP/GPKG, integridade relacional e estrutura OOXML do XLSX.
- Interface: estados, rascunhos, cancelamento e navegação com widgets reais PyQGIS.
- Plugin: ZIP/manifesto e bloqueio da mistura de distribuições na mesma sessão.

Os validadores XLSX não equiparam sucesso do openpyxl a compatibilidade desktop.
`validar_excel_desktop.py` é opcional e exige Excel Windows e pywin32 disponíveis.
O ensaio sintético `ensaio_versionamento_bases.py` gera duas versões controladas,
sem alterar um modelo real.

## Aceitação manual no QGIS desktop

1. Instalar o ZIP em perfil de teste, abrir pelo menu/botão e reiniciar a sessão.
2. Executar uma auditoria sintética, conferir mapa/tabelas e bloqueio das entradas.
3. Iniciar reprocessamento explicitamente, cancelar e conferir preservação do contexto.
4. Reagrupar sem refazer eventos; comparar locais e efeitos sobre revisões.
5. Abrir uma base persistente sem sua fonte, consultar páginas e ambas as perspectivas.
6. Criar investigação, selecionar no mapa e no painel, conferir zoom explícito.
7. Salvar decisão/proposta; fechar e reabrir a mesma investigação.
8. Alterar rascunho e testar Salvar/Descartar/Cancelar ao trocar caso, base e fechar.
9. Testar atualização equivalente e modificada em controle sintético e comparar versões.
10. Relocalizar cópia de uma base; testar rejeição de identidade incompatível.
11. Exportar formatos, reimportar e conferir coordenadas, CRS, chaves e vínculos.
12. Fechar normalmente o QGIS e descarregar/recarregar o complemento.

Ensaios anteriores por API em perfil isolado verificaram ações do complemento,
mas não encerraram a validação de saída normal do processo nem a aceitação por cliques.
Registre os passos realmente executados e suas limitações no relatório do teste.

## Publicação

Executar o verificador em `ferramentas/auditar_publicacao.py` depois do staging,
revisar o diff e o histórico e empacotar a partir de um clone limpo. Resultados,
logs e arquivos de instalação gerados permanecem fora do Git. Ver SECURITY.md.
