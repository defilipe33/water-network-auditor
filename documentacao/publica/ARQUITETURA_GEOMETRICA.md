# Arquitetura da auditoria geométrica

O pacote `scripts/auditoria_fronteiras` separa contratos, entradas, núcleo geométrico,
agrupamento, apresentação, interface, persistência, versionamento e exportação.
Os pontos de entrada anteriores por console permanecem disponíveis para compatibilidade.

`modelos.py` define entradas, parâmetros e ocorrências; `entradas.py` valida campos,
CRS e geometria e conserva referências técnicas. IDs cadastrais não são presumidos
únicos, nem mesmo entre camadas. Chaves preservam origem, atributos e discriminação.

`nucleo.py` detecta fronteiras individuais usando índices espaciais. Não modifica
geometrias de entrada nem cria conexões. Modos TRANSICAO e PERIMETRO compartilham
o núcleo. Polígonos aninhados e sobrepostos são analisados independentemente.
Fronteiras compartilhadas no modo transição evitam multiplicação artificial do evento.

Classificações: TRAVESSIA, TANGENCIA, EXTREMIDADE, COINCIDENCIA,
CONTINUIDADE_POTENCIAL e AMBIGUA. Uma classificação diferente de AMBIGUA ainda pode
ter indicador geral de ambiguidade. Exterior, indeterminação e extremidade são distintos.

`investigacao.py` agrupa candidatos compatíveis sem apagar eventos. Distância de
busca e extensão máxima são independentes. Identidades de tubulações, limites e
compatibilidade técnica evitam grupos formados somente por proximidade ou encadeamento.
A localização representativa não altera as coordenadas dos eventos originais.

`apresentacao.py` e `inspecao.py` produzem registros legíveis e dossiê técnico.
Listas apresentadas não substituem relações entre tubos, camadas e chaves internas.
A normalização de ID é somente de apresentação, com tolerância conservadora;
texto com zeros à esquerda e identificador bruto são preservados.

`interface.py`, `estados.py` e `fluxos.py` controlam configuração e resultados.
SEM_AUDITORIA, CONFIGURANDO, CONFIRMANDO, PROCESSANDO, INSPECIONANDO,
PREPARANDO_REPROCESSAMENTO, PREPARANDO_REAGRUPAMENTO e ERRO têm ações guardadas.
Configuração pendente nunca representa implicitamente um resultado confirmado.

`persistencia.py`, `versoes.py` e `ciclo.py` conservam execuções, vínculos, revisões,
histórico e reconciliação. Substituições exigem confirmação e backup íntegro;
criar nova versão é a opção conservadora. Comparações usam composição técnica,
não sequências de apresentação. Ver [persistência](PERSISTENCIA_VERSIONAMENTO.md).

Os exportadores são independentes do algoritmo. SHP tem nomes de até dez caracteres,
validações de reimportação, arquivos auxiliares e avisos de representação. GeoPackage
é relacional. XLSX preserva tabelas/filtros compatíveis e detalhes por agrupamento de linhas.
