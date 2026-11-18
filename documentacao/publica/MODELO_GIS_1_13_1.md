# Modelo GIS — interface 1.13.1

A configuração do projeto começa pela função das camadas. O painel inicial apresenta grupos compactos, contagens e pendências. Cada categoria traz suas próprias fontes e as ações úteis para editá-las.

## Cadastrar e revisar

1. Na **Central de Trabalho**, selecione um projeto e use **Configurar fontes GIS** ou **Continuar configuração**.
2. Abra uma categoria e use **Adicionar camadas**. Marque todas as camadas desejadas e use **Adicionar selecionadas**. Camadas incompatíveis ficam em uma lista de consulta. As já cadastradas na categoria aparecem desabilitadas.
3. Confira os identificadores e rótulos em **Configurar campos e filtro**. A sugestão considera nomes, sinônimos, tipos de dados e categoria. Quando há candidatos concorrentes, a lista de opções fica visível e o campo permanece por mapear. A associação WaterGEMS é escolhida pelo usuário.
4. Se as fontes tiverem estrutura equivalente, selecione a referência e use **Aplicar mapeamento a outras camadas**. A cópia verifica nome e família de tipo em cada destino. Campos ausentes ou incompatíveis aparecem na conferência do lote. Os mapeamentos válidos que já existiam nesses destinos são mantidos. Filtros e papéis ficam vinculados à fonte.
5. Use **Montar filtro simples** para escolher campo, operador e valor. **Expressão avançada** continua disponível para combinações e funções de atributos. Em **Ver amostra dos valores**, a leitura consulta até 250 feições e mostra até cinco amostras correspondentes. Quando o limite é atingido, o resultado informa que o total ficou em aberto.
6. Use **Conferir fontes**. Ao abrir uma categoria após a leitura, expanda os detalhes das fontes sinalizadas para consultar quantidades, amostras de IDs repetidos, sobreposições e ações. A conferência completa roda em segundo plano e pode ser cancelada.
7. Abra **Junctions e conectividade** para escolher entre usar uma camada, inferir nós pelas tubulações ou combinar as duas estratégias. A opção é registrada para a Etapa 2.
8. Use **Salvar Modelo GIS** para registrar a revisão. Em **Mais ações da fonte**, é possível relocalizar uma origem ou retirar uma associação do rascunho. A revisão anterior permanece disponível em **Consultar alterações**.

### Cadastro, filtros e compatibilidade

O mesmo cadastro da 1.13.0 é usado pela 1.13.1. O projeto conserva seus UUIDs, filtros e revisões. A edição em painel acoplado e janela independente usa os mesmos controles e o mesmo rascunho. O fluxo salvo depende da identificação das fontes, das regras de mapeamento e das verificações técnicas aplicáveis.

Uma camada pode ser reutilizada em categorias distintas. O cadastro mantém os filtros independentes e sinaliza sobreposições na conferência. A prévia distingue expressão inválida, zero correspondências em uma leitura completa e zero correspondências nas primeiras feições examinadas. Os diagnósticos e as amostras são recalculados sob demanda.

## Comparativo com a 1.13.0

Tarefa reproduzida com as três mesmas camadas sintéticas de tubulações e com os campos sugeridos. O ponto de partida foi a aba Modelo GIS já aberta no mesmo projeto. A unidade é uma ação lógica no controle, como escolher uma camada, trocar categoria ou salvar.

| Medida | 1.13.0 | 1.13.1 |
| --- | ---: | ---: |
| Ações até salvar as três camadas | 13 | 7 |
| Janelas de configuração abertas | 3 | 0 |
| Escolhas da categoria | 3 | 1 |
| Confirmações de inclusão de fontes | 3 | 1 |
| Digitação para os campos sugeridos da tarefa | 0 | 0 |

A inclusão passa de três ciclos de formulário para uma única seleção em lote. Para a associação WaterGEMS opcional, o ensaio adicional mapeou um par manualmente e o aplicou às duas fontes equivalentes em uma operação.

## Capturas do QGIS 3.44.15

Foram usados os instaladores das duas versões em perfis isolados. As imagens registram a interface real com dados sintéticos.

| Caso | Capturas |
| --- | --- |
| Interface anterior | [Tabela da 1.13.0](capturas/modelo_gis_1_13_1/00_antes_painel.png) · [Formulário individual da 1.13.0](capturas/modelo_gis_1_13_1/00_antes_formulario.png) |
| Navegação | [Tela principal](capturas/modelo_gis_1_13_1/01_modelo.png) · [Grupos](capturas/modelo_gis_1_13_1/02_grupos.png) · [Tubulações](capturas/modelo_gis_1_13_1/03_tubulacoes.png) |
| Fontes e atributos | [Seleção das três camadas](capturas/modelo_gis_1_13_1/04_tres_camadas.png) · [Campos sugeridos](capturas/modelo_gis_1_13_1/05_mapeamento_automatico.png) · [Cópia do mapeamento](capturas/modelo_gis_1_13_1/06_mapeamento_lote.png) |
| Revisão e salvamento | [Filtro simples](capturas/modelo_gis_1_13_1/07_filtro_simples.png) · [Junctions](capturas/modelo_gis_1_13_1/08_junctions.png) · [Conferência com detalhes](capturas/modelo_gis_1_13_1/09_conferencia.png) · [Revisão salva](capturas/modelo_gis_1_13_1/10_salvo.png) |
| Reabertura e modos | [Cadastro 1.13.0 em nova sessão da 1.13.1](capturas/modelo_gis_1_13_1/11_recuperacao_1130.png) · [Painel acoplado](capturas/modelo_gis_1_13_1/12_painel.png) · [Janela independente](capturas/modelo_gis_1_13_1/13_janela.png) |

Para conferir no seu projeto, repita a seleção das três fontes, gere uma amostra, altere um filtro e mude a apresentação durante a edição. Salve, reinicie o QGIS e consulte a revisão anterior. A aceitação humana em projeto operacional e a avaliação em um segundo monitor físico ficam pendentes.
