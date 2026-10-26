# Dependências e referências

O projeto utiliza APIs de terceiros; não reivindica sua autoria nem redistribui os
modelos e cadastros utilizados em ensaios privados.

| Componente | Uso | Condição de distribuição |
|---|---|---|
| QGIS / PyQGIS | Geometria, camadas, CRS, interface e exportação | Fornecido pela instalação QGIS; consultar a licença GPL do QGIS |
| Qt / PyQt | Widgets e sinais | Fornecidos pelo ambiente QGIS; respeitar as licenças aplicáveis à distribuição utilizada |
| NetworkX | Grafo e conectividade | Dependência externa, licença BSD de três cláusulas |
| openpyxl | XLSX e validação de conteúdo | Dependência externa, licença MIT |
| Python / SQLite | Runtime, persistência e snapshots | Fornecidos pelo ambiente; licenças próprias |
| pywin32 (opcional) | Ensaio COM no Excel desktop Windows | Não necessário para uso normal do complemento; licença própria |

O empacotador inclui apenas os fontes deste projeto e o ícone SVG do complemento;
não incorpora bibliotecas externas. As condições acima não substituem os textos
das licenças das versões efetivamente utilizadas.

## Model Builder Composer

Referência técnica: [defilipe33/model-builder-composer](https://github.com/defilipe33/model-builder-composer),
branch `main`, commit consultado `b3205a2579eee782375b757f7a0b96f40f7a88ff`.
Foi consultado para confrontar cenários, alternativas, directed nodes e topologia.
O resolvedor deste projeto possui regras conservadoras próprias e não incorpora
fallback geométrico como conexão confirmada.

A cópia local do repositório de referência não é publicada nem empacotada aqui.
Não foi encontrado arquivo de licença nessa cópia consultada. Portanto, sua
visibilidade pública não foi tomada como autorização de redistribuição. Ensaios
opcionais de confronto exigem obter a referência separadamente e revisar suas condições.

Bentley WaterGEMS, QGIS e nomes de organizações mencionados conservam seus direitos.
Não há declaração de afiliação ou aprovação oficial. Não foi adicionada licença
open-source ao Water Network Auditor; essa definição permanece pendente.
