# Contribuir

Use branch própria e descreva problema, comportamento resultante e validação no PR.
Não introduza dependências ou reorganizações sem justificar a necessidade.

## Contratos de engenharia

- Entradas são somente leitura; não editar modelos WaterGEMS nem cadastro GIS.
- Não conectar elementos por cruzamento/proximidade, nem transformar hipótese em fato.
- Preservar identidades de origem, campos escolhidos e vínculos entre camadas.
- Separar geometria, agrupamento, grafo, interface, persistência e exportação.
- Trabalhar em CRS métrico confirmado para medir distâncias.
- Alterações de regras validadas exigem defeito demonstrado e regressão correspondente.
- Não herdar decisões de uma versão para composição nova sem equivalência comprovada.

## Desenvolvimento

Execute a suíte no Python do QGIS conforme o README. Testes novos devem usar dados
sintéticos inventados, coordenadas locais simples e identificadores sem origem real.
Evite caminhos absolutos, dados pessoais e municípios obrigatórios.

Não inclua modelos, cadastros, relatórios reais, screenshots operacionais, logs,
segredos ou arquivos privados em commits, issues e PRs. Consulte SECURITY.md.
Use `git diff --cached`, `git ls-files` e o verificador de publicação antes de enviar.

Registre claramente o ambiente e a diferença entre teste sintático, PyQGIS offscreen,
QGIS desktop e Excel/WaterGEMS desktop. Não declare validação que não foi executada.
Atualize a documentação pública quando mudar um contrato ou um fluxo do usuário.

O projeto ainda não tem licença definida. Não inclua código de terceiros sem revisar
suas condições e atribuições; não suponha que um repositório público permite cópia.
