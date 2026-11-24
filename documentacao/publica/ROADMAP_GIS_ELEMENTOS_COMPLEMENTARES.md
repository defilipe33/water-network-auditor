# Roadmap GIS — elementos e conexões complementares

Este é um plano arquitetural, não funcionalidade implementada na 1.15.2. Nenhum botão de criação, nó inferido, conexão ou exportador ModelBuilder novo é entregue nesta atualização.

| Etapa sugerida | Resultado esperado |
|---|---|
| 1.15.2 | Relevância separada de classificação geométrica e acompanhamento |
| 1.16.0 | Topologia GIS, revisão de conectividade e elementos/conexões complementares persistentes |
| 1.17.0 | Redes estruturantes, dependências de zonas, passagem e redundância |
| 1.18.0 | Intervenções, isolamento e alternativas de equipamentos |
| 1.19.0 | Exportação multielemento ModelBuilder, incluindo complementos habilitados e tecnicamente aptos |

## Requisito obrigatório da próxima etapa

Permitir complementar o cadastro recebido sem modificá-lo: Reservoir/Tank ausente, instalação booster, válvula existente ou proposta e conexão conhecida entre tubos cuja geometria não representa o vínculo. A conexão declarada não deve ser confundida com conexão inferida por cruzamento ou proximidade.

Usar o cadastro multifonte atual como registro de fontes e o projeto como dono dos complementos. Não criar um segundo cadastro nem um segundo sistema de histórico. O motor geométrico existente permanece separado do futuro adaptador de grafo GIS.

## Modelo proposto, sujeito à revisão de implementação

GeoPackage próprio do projeto, com camadas de elementos por geometria e tabelas de conexões/revisões. Identidade UUID, nunca nome, FID ou sequência de exibição como chave. Separar identidade lógica da versão imutável da entidade.

| Entidade | Conteúdo mínimo |
|---|---|
| Elemento complementar | UUID, UUID do projeto, tipo, geometria + CRS, atributos tipados conhecidos, situação, origem opcional da informação, contexto da hipótese, revisão ativa, exclusão lógica |
| Conexão complementar | UUID, extremidades referenciadas por identidade estável, fonte/elemento/porta quando aplicável, natureza declarada ou hipótese, revisão, restrições e contexto explícitos |
| Revisão | UUID, entidade, anterior, data UTC, conteúdo anterior/novo verificável; atualização concorrente protegida pela revisão esperada |
| Participação na análise | Execução, versões das fontes e complementos, cenário/hipótese, elementos/revisões habilitados, regras e identidade do algoritmo |

Quatro situações distintas: **Existente informado**, **Existente a confirmar**, **Proposto**, **Hipotético**. “Informado” preserva a informação do usuário, sem convertê-la automaticamente em existência ou operação comprovada. Origem da informação é opcional; não exigir nome, CREA, documento, assinatura ou aprovação.

Salvar atributos conhecidos e pendências; não inventar carga, curva Q-H, setpoint, nível de tanque ou estado operacional. A localização GIS de uma instalação pode estar afastada dos tubos vinculados. Validar identidades/portas e registrar a relação, sem mover geometrias originais para forçar coincidência.

## Grafo, cenários e rastreabilidade

Construir o grafo de trabalho por adaptadores de leitura: fontes originais → nós/arestas referenciados → complementos explicitamente habilitados. Divisões virtuais, se necessárias, pertencem ao resultado e preservam a referência ao tubo original. Cruzamentos e vizinhança continuam candidatos, não arestas automáticas.

A interface deverá distinguir análise apenas do cadastro original, com existentes informados, com propostos e com hipóteses. Um seletor explícito define os conjuntos/revisões participantes; não habilitar silenciosamente uma proposta. Reservoir/Tank complementar poderá ser origem topológica escolhida, sem comprovar disponibilidade operacional.

Não transferir conclusões entre cenários ou versões só por proximidade. Reconciliar por identidade e relações verificadas; vínculos removidos, alterados ou ambíguos exigem revisão. Preservar versões anteriores, anexos e decisões. Mudanças relevantes invalidam caches dependentes do grafo e não apagam análises antigas.

## Persistência, interface e exportação futuras

Reutilizar revisões, proteção de rascunhos, catálogo, workers, backups verificados e publicação atômica. Migrações devem ser versionadas, transacionais, verificadas e reversíveis, sem reescrever bases antigas silenciosamente. A compatibilidade de projeto e registro será testada antes da mudança de esquema.

No Quadro do Modelo, complementos serão apresentados no grupo funcional correspondente, com situação textual e participação na hipótese visíveis. Criação por mapa/seleção, revisão de conexões e histórico serão contextuais, sem um aplicativo separado.

O exportador ModelBuilder deverá oferecer SHP/GPKG conforme suporte e CSV de tabelas, preservando UUIDs e IDs originais. Separar cadastro, existentes informados, propostas e hipóteses; exportar apenas o que foi explicitamente selecionado. Verificar campos, unidades, CRS e requisitos nativos de cada tipo antes de considerá-lo apto. Nunca escrever diretamente no `.wtg.sqlite`.

## Critérios antes de iniciar 1.16

Validar 1.15.2 no uso cotidiano; definir portas e identidade de nós GIS; revisar regras de dispositivos direcionais, Active Topology e hipóteses; criar amostras sintéticas e casos de reconciliação. Cobrir UUID, revisões/concorrência, cancelamento, recuperação, cenários independentes, nulos/unidades/CRS, reservatório afastado associado, proposta desabilitada, conexões ambíguas e preservação das fontes. Medir custo do grafo e publicar somente dados sintéticos.
