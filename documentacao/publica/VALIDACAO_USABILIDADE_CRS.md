# Validação de usabilidade e referência espacial — versão 1.1.0

- QGIS 3.44.15-Solothurn, Python empacotado 3.12, Windows.
- Suíte completa: **467 testes aprovados**, sendo 419 anteriores e 48 novos.
- Nova suíte isolada: 48 aprovados em 10,930 s; suíte completa em 216,317 s.
- Matriz de áreas úteis lógicas: nove janelas × duas resoluções (1366 × 768 e
  1920 × 1080) × cinco escalas (100%, 125%, 150%, 175%, 200%): 90 cenários sem
  janela fora da área. Inclui principal, WaterGEMS, versões, catálogo, inspeção,
  diagnósticos, componentes, integração e exportação. As decisões/propostas são
  formulários do painel e usam a mesma adaptação e rolagem.
- QGIS desktop nativo, plataforma `windows`, perfil isolado, escala Qt 150%:
  instalação do ZIP pelo gerenciador oficial, abertura pela QAction, consulta
  topológica sem CRS, recuperação de base validada, prévia GIS × Label e
  reabertura da investigação concluídas pela API Qt. Capturas examinadas.
- O ensaio desktop descarregou o complemento, mas o processo não encerrou dentro
  do prazo de 120 s. O encerramento normal permanece pendente.
- Pacote ZIP: verificação CRC e dos 61 arquivos do manifesto SHA256 aprovada.
- O ensaio real preservou as quantidades e verificou hashes das fontes; os dados,
  coordenadas, identificadores e evidências operacionais não são distribuídos aqui.

Os testes incluem campos GIS explicitamente escolhidos, nulos/vazios/zero,
zeros à esquerda, candidatos múltiplos, fator de conversão, CRS geográfico bloqueado,
contexto compatível/incompatível, assinatura ausente, versões sem sobrescrita,
cancelamento, reabertura de declarações legadas e bloqueio antes de criar saída.

A automação visual disponível falhou ao inicializar o runtime. O ensaio desktop
pela API Qt não equivale a operação por cliques. Permanecem pendentes a aceitação
manual completa, escalas físicas do Windows e troca real entre monitores.
O [roteiro manual](USABILIDADE_CRS.md) descreve as verificações restantes.
