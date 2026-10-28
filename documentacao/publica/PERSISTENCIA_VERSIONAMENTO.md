# Persistência e versionamento

O GPKG geométrico possui execuções, eventos, locais, referências de tubos/polígonos,
vínculos e revisões. LOCAL_EVENTO e EVENTO_REDE preservam associações explícitas.
IDs técnicos não dependem de fid ou de números de linha.

Reagrupar conserva eventos, geometrias e classificações; muda somente estruturas
dependentes dos locais. Grupos idênticos podem ter correspondência técnica;
divisões/fusões preservam histórico e exigem reconciliação de composição alterada.
Reprocessamento com outras entradas ou parâmetros produz comparação de contexto.
Criar nova versão é padrão; substituição exige confirmação e backup íntegro verificado.

## Bases WaterGEMS

Cada arquivo de base contém camadas/tabelas WG existentes e a extensão:

| Tabela | Função |
|---|---|
| WB_BASE | UUID, modelo, contexto, assinatura, versão, origem e proveniência |
| WB_ELEMENTOS | Dados relevantes extraídos, UID, tipo, atividade, exclusão e WKB bruto |
| WB_RESULTADOS | Conexões, componentes, diagnósticos e resumos por perspectiva |

O snapshot é produzido pela API de backup SQLite, incluindo commits presentes no
WAL. Não é uma cópia arbitrária apenas do arquivo principal, nem inclui mudanças
não salvas no WaterGEMS. A fonte é aberta somente leitura. Arquivos técnicos ficam
no destino controlado; publicação final ocorre depois da validação, sem sobrescrita.

A assinatura exclui caminho e tabelas auxiliares não extraídas; inclui dados e
contexto relevantes. Fonte equivalente reutiliza a base anterior. Outra identidade
de modelo exige base independente, mesmo no mesmo projeto. Mudanças recebem UUID
próprio e referência à versão anterior. Arquivos separados evitam crescimento obrigatório
de um banco único. Comparação não transfere automaticamente conclusões.

Consulta inicial usa metadados. Inventário é paginado e não carrega WKB para uma
lista de elementos. Reconstrução completa ocorre por ação explícita e confronta os
resultados persistidos; ordem de emissão dos diagnósticos não constitui identidade.

## Investigações e decisões

Tabelas IG_* vinculam execução integrada, contexto GIS/topológico, locais, pares,
componentes, membros, associações, áreas e snapshots. Extensões IGD_* mantêm decisões,
propostas, histórico e comparação no contexto integrado. Revisões espaciais ficam separadas.
As versões antigas permanecem consultáveis e não são atualizadas silenciosamente.

O catálogo mantém apenas identidades, metadados e caminhos; não replica geometrias.
Relocalização verifica UUID e conserva a localização anterior. Bases legadas podem
ser abertas ou importadas para cópia nova conforme o conteúdo disponível; campos
ausentes não são inventados. Importação parcial é identificada explicitamente.

GPKG é a base completa. SHP tem campos resumidos e relacionamentos auxiliares;
XLSX tem visões analíticas e expansíveis. Exportação nova não substitui as antigas
automaticamente. Nenhuma versão ou proposta é escrita de volta no modelo hidráulico.

## Situação de acompanhamento — 1.8.1

As tabelas aditivas `IGD_ACOMP_SCHEMA` e `IGD_ACOMPANHAMENTO` conservam resolução/reabertura separadas do resultado técnico. A primeira gravação cria backup verificado; leitura de base antiga não aplica migração. Novos registros referenciam a revisão anterior, a execução e a perspectiva; alteração concorrente bloqueia a sobrescrita. Comparação explícita conserva somente equivalências técnicas comprovadas, sinaliza alterações locais e preserva histórias nas duas versões. [Detalhes](RELATORIOS_QUERIES_ACOMPANHAMENTO.md).
