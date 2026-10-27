# Exportações pela interface — 1.4.1

O sinal `clicked(bool)` alcançava métodos sem parâmetro `checked` através do wrapper
de atividade. O Qt conseguia adaptar métodos comuns, mas a assinatura variável do
decorador encaminhava o booleano e provocava `TypeError`.

As conexões dos botões de exportação GIS e Excel agora descartam explicitamente
somente o booleano do sinal. A revisão encontrou o mesmo risco no carregamento de
representações WaterGEMS, na comparação de investigações e na exportação de decisões;
essas conexões também foram ajustadas. O decorador continua encaminhando índices,
textos, objetos e argumentos nomeados legítimos. A atualização paginada recebe seus
parâmetros por métodos intermediários sem decoração e não exige adaptação adicional.

## Verificação no QGIS 3.44.15

1. Instale o ZIP 1.4.1 pelo gerenciador de complementos e reinicie o QGIS.
2. Crie uma auditoria GIS com camadas sintéticas ou fontes locais autorizadas.
3. Clique em **Exportar GPKG / SHP / XLSX…**; escolha cada formato separadamente
   e depois os três, sempre em pastas novas.
4. Confira as contagens, CRS, geometrias, IDs e relações após reabrir os resultados.
5. Clique no botão independente **Gerar relatório Excel…**.
6. Cancele a escolha dos formatos, pasta e arquivo Excel. A atividade deve indicar
   cancelamento, sem anunciar sucesso. Simule um destino sem permissão e repita a
   exportação para uma pasta válida.
7. Reabra a auditoria salva, repita as exportações e encerre/reabra o QGIS.

O conjunto automatizado aciona `QPushButton.click()`, inclusive o booleano emitido
pelo Qt. As escolhas de destino são controladas nos testes. Valida GPKG por leitura
SQLite e comparação de relações/geometrias, SHP por reimportação PyQGIS e XLSX por
inspeção OOXML. Essa inspeção não equivale à abertura no Excel desktop.

O núcleo, agrupamento, topologia, referências espaciais, histórico, encerramento e
gerenciamento de janelas não foram alterados. Exportadores permanecem síncronos
quando já o eram; cancelamento não é prometido dentro de gravações indivisíveis.

## Armazenamento local

O histórico público permite recuperar versões do código e reconstruir seus ZIPs
com `testes/empacotar_plugin.py`. Resultados operacionais, bases e evidências privadas
não fazem parte do repositório público de código. Seu arquivamento exige um destino
privado autorizado, com controle de acesso e integridade, antes de eliminar cópias
locais. Uma alternativa é um repositório privado separado, com arquivos de release
e manifestos de recuperação. A limpeza local remove temporários e cópias cujo backup
foi conferido, sem apagar as fontes originais.
