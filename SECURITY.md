# Segurança de dados e publicação

Este repositório distribui código e exemplos sintéticos, não redes operacionais.
Não abra issues públicas contendo modelos, geometrias reais, credenciais ou evidências
cadastrais. Em caso de exposição, evite reproduzir o conteúdo e use o canal privado
disponível com o mantenedor; não há endereço confidencial específico configurado.

## Política de versionamento

São publicáveis fontes revisados, testes sintéticos, ícones, configuração distribuível,
documentação genérica e roadmaps inspecionados. Dados de entrada, resultados, modelos,
bancos, rasters, planilhas, ZIPs gerados, referências institucionais, cópias de terceiros,
logs e configurações pessoais permanecem locais.

Os documentos operacionais originais também ficam locais. A documentação pública
em `documentacao/publica` conserva contratos e histórico de desenvolvimento sem
expor identificadores, geometrias e decisões vinculadas a ativos reais.

`.gitignore` agrupa regras de Python/Windows, diretórios privados, ensaios operacionais
e formatos de dados/saídas. As fixtures sintéticas essenciais não são ignoradas:
os testes constroem suas próprias geometrias e bancos temporários. Não usar `git add -f`.

Antes de publicar:

1. Examinar `git status`, lista exata de arquivos staged e `git diff --cached`.
2. Executar `python ferramentas/auditar_publicacao.py` após staging.
3. Inspecionar caminhos, IDs, coordenadas, tabelas e arquivos binários: detecção por
   extensão ou expressão regular sozinha não prova ausência de dados sensíveis.
4. Verificar histórico que será enviado, não apenas o último estado dos arquivos.
5. Executar testes e empacotar o plugin a partir de um clone limpo.

O verificador é complementar e pode exigir revisão humana de falsos positivos.
Se houver conteúdo sensível no histórico, interromper o envio e planejar a limpeza;
não reescrever histórico remoto ou usar force push silenciosamente.

Nenhum arquivo local deve ser apagado apenas por passar a ser ignorado pelo Git.
