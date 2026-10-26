# Validação do fluxo investigativo — 1.3.0

Ambiente: Windows, QGIS 3.44.15-Solothurn e Python 3.12 do QGIS.

- **600 testes aprovados**: 562 anteriores e 38 novos, em 269,873 s.
- Testes novos cobrem anotações/preliminares, proteção das confirmações, autoria,
  histórico imutável, integridade relacional, exportação, rascunhos, fim automático
  do assistente, X antes/depois de publicar, cliques repetidos, grupos por contexto,
  originais intocados, estilos/seleções/visibilidade e reabertura de `.qgz`.
- Os ajustes finais de apresentação foram reverificados nas suítes de widgets.
- ZIP instalado pelo gerenciador oficial em perfil isolado, escala Qt 150%: callback
  de conclusão exercitado com uma publicação sintética íntegra previamente preparada;
  referência espacial e base ativa atualizadas e assistente fechado automaticamente.
- No mesmo ensaio, anotações e preliminares foram persistidas, os três grupos foram
  conferidos, o mapa foi navegado e o projeto QGZ foi salvo.
- Outra sessão recuperou o QGZ e os registros, repondo representações de memória
  vazias a partir da investigação persistida, mantendo as mesmas 24 camadas.
- O pacote final também foi instalado em outro perfil limpo e a reabertura foi
  novamente exercitada pela API Qt. Capturas foram examinadas.

Os ensaios desktop foram conduzidos pela API Qt, não por cliques humanos. A aceitação
interativa permanece pendente. Os processos QGIS excederam o prazo de encerramento
do ensaio, embora tenham concluído as etapas verificadas. Fechamento do assistente
e encerramento do processo QGIS são resultados distintos.

Não se declara nesta entrega uma nova validação operacional de modelos reais. Os
ensaios novos usam bases sintéticas; o processamento geométrico e topológico aprovado
foi preservado. O `.qgz` não substitui os GPKGs de origem e referências inválidas
continuam exigindo recuperação explícita.

Uma proposta de mover nós existentes foi rejeitada pela revisão automática por risco
de alterar a organização manual. A solução adotada preserva esses nós e usa referências
nos grupos próprios; versões legadas podem conservar referências visuais adicionais,
sem duplicação de objetos de camada ou dos dados.

O [roteiro manual](FLUXO_INVESTIGATIVO.md) inclui os testes restantes. Dados, imagens,
projetos e bases dos ensaios não são publicados com o código.
