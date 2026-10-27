# Fluxo vigente — 1.5.0

O registro cotidiano usa resultados investigativos, motivos e observações opcionais,
sem exigência de responsável, fonte, documento ou aprovação. A extensão operacional
reutiliza IGD_OCORRENCIAS, assinaturas e a base integrada existente. Consulte
[arquitetura, filtros e compatibilidade](ANALISE_OPERACIONAL_E_FILTROS.md).
As regras formais descritas abaixo documentam o legado e suas APIs, preservados
para histórico; não são requisitos do formulário principal.

# Integração, diagnósticos e decisões

O controlador `auditoria_aplicacao.controlador.Aplicacao` inicializa os componentes
existentes a partir do plugin. `integracao.preparar` aceita contexto topológico
recuperado ou os contratos legados, sem duplicar o leitor ou resolvedor.

Uma investigação referencia a execução GIS e a versão exata da base WaterGEMS.
É persistida em arquivo novo; não substitui os contextos de origem. Comparação de
município e CRS é uma barreira adicional, não prova suficiente de correspondência.

`validacao.provar_correspondencia` confronta campo GIS explicitamente escolhido com
Label WG, unicidade bilateral e vértices. O conjunto de fontes é examinado conjuntamente.
DomainElementID não equivale a ID cadastral. Correspondências inequívocas, múltiplas,
inconsistentes e não encontradas conservam candidatos e razões. Não há desempate por distância.

`investigacao.py` separa nó diretamente compartilhado de pertencimento ao mesmo
componente ou existência de caminho alternativo. Classes investigativas incluem:

- CONEXAO_DIRETA_CONFIRMADA_NO_MODELO;
- MESMO_COMPONENTE_SEM_CONEXAO_DIRETA;
- COMPONENTES_DIFERENTES;
- POSSIVEL_CONEXAO_AUSENTE;
- CONEXAO_POTENCIALMENTE_INDEVIDA;
- CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO;
- CORRESPONDENCIA_INSUFICIENTE.

Essas classes não são conclusões hidráulicas automáticas. O painel de diagnósticos
organiza casos por evidência, componente, região, revisão e perspectiva. Mapa e
detalhes expansíveis auxiliam a investigação sem alterar símbolos dos dados originais.

`decisoes.py` e `form_decisao.py` separam situação administrativa, conclusão técnica
e proposta. Estados administrativos: PENDENTE, EM_ANALISE, VERIFICADO, DESCARTADO e
NECESSITA_CONFIRMACAO. A revisão topológica não sobrescreve a revisão espacial.

Conclusões são explícitas. Conexão faltante/indevida confirmada, desconexão intencional
e problema cadastral confirmado exigem justificativa e evidência apropriadas.
Observações podem ser salvas durante investigação incompleta. Rascunhos são protegidos
por Salvar/Descartar/Cancelar nas trocas de contexto e no encerramento.

Propostas registram elementos, IDs/Labels, cenário, justificativa, responsáveis,
evidências e requisitos. Identificação incompleta impede aprovação. Os estados
RASCUNHO, AGUARDANDO_CONFIRMACAO, PROPOSTA_PARA_APROVACAO, APROVADA, REJEITADA,
APLICACAO_INFORMADA, VALIDACAO_PENDENTE, VALIDADA e VALIDACAO_FALHOU são independentes
da revisão administrativa. Aplicação informada é uma declaração, não alteração no modelo.

`comparacao_decisoes.py` produz evidências entre contextos comparáveis. PERMANECE,
ALTERADA, NAO_OBSERVADA, NOVA, CORRESPONDENCIA_INCERTA e REQUER_REAVALIACAO não
significam correção automática. Validação final permanece uma ação do engenheiro.
Histórico é acrescentado, com transações e proteção contra gravação concorrente.
