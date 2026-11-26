"""Controles da visão macro integral na investigação estrutural."""

from pathlib import Path

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog,
                                QDialogButtonBox, QDoubleSpinBox, QFileDialog, QInputDialog, QListWidget,
                                QListWidgetItem, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from . import macro_origem_gis as motor
from .mapa_macro_origem import MapaMacroOrigem, PADRAO, plano, preparar
from .modelo_gis import identificar, revisoes
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import acao_disponivel, navegar_registros


CATEGORIAS = (
    ('MACRO_BLOCOS', 'Blocos macro de distribuição'),
    ('MACRO_CORREDORES', 'Corredores de referência'),
    ('MACRO_AREAS', 'Áreas GIS e percursos'),
    ('MACRO_DETALHES', 'Blocos topológicos detalhados'),
    ('MACRO_SEGMENTOS', 'Segmentos, pontes e alternativas'),
    ('MACRO_NOS', 'Nós e articulações'),
    ('MACRO_CONEXOES', 'Conexões declaradas'),
    ('MACRO_ORIGENS', 'Alcance compartilhado e exclusivo'),
)
VISTAS = (('AMBOS', 'Corredores e blocos'), ('CORREDORES', 'Somente corredores'),
          ('BLOCOS', 'Somente blocos'), ('COMPLETA', 'Completa com rede de contexto'),
          ('COMPARACAO', 'Alcance por origem'), ('INFLUENCIA', 'Influência por distância em rede'))


class MacroOrigemUI:
    def montar_macro_integral(self, layout):
        self.macro_integral = None
        self.mapa_integral = MapaMacroOrigem()
        self._cor_integral = PADRAO
        self._grupos_macro = {}
        self._filhos_integral = {}
        self._alvo_integral = None
        self._isolado_integral = None
        self._painel_integral, v = expansivel(layout, 'Visão macro do abastecimento por origem')
        self._painel_integral.setChecked(True)
        form = formulario(v)
        self.origem_integral = QComboBox()
        form.addRow('Origem de abastecimento', self.origem_integral)
        self.origens_integral = QListWidget()
        self.origens_integral.setMaximumHeight(92)
        self.origens_integral.setSelectionMode(QAbstractItemView.ExtendedSelection)
        v.addWidget(self.origens_integral)
        self.origem_integral.currentIndexChanged.connect(self._mostrar_escolha_origens)
        self._opcoes_integral, opcoes = expansivel(v, 'Critérios de agrupamento')
        self.minimo_integral = QDoubleSpinBox()
        self.minimo_integral.setRange(.01, 10000000)
        self.minimo_integral.setValue(500.)
        self.minimo_integral.setSuffix(' m')
        formulario(opcoes).addRow('Extensão mínima dos ramais', self.minimo_integral)
        self.orientar_integral = QCheckBox('Orientar os blocos pelas áreas GIS')
        opcoes.addWidget(self.orientar_integral)
        self.calcular_integral_b = botao(v, 'Calcular visão integral', self.calcular_macro_integral)
        self.resumo_integral = aviso()
        v.addWidget(self.resumo_integral)
        self._resultado_integral, r = expansivel(v, 'Mapa, árvore e exportação')
        f = formulario(r)
        self.visao_integral = QComboBox()
        for k, n in VISTAS:
            self.visao_integral.addItem(n, k)
        f.addRow('Apresentação do mapa', self.visao_integral)
        self.area_integral = QComboBox()
        f.addRow('Área GIS de interesse', self.area_integral)
        self.area_integral.activated.connect(self._alterar_area_integral)
        self.referencia_integral = QComboBox()
        f.addRow('Percursos de referência', self.referencia_integral)
        self.referencia_integral.activated.connect(self._alterar_area_integral)
        self.nivel_integral = QComboBox()
        for n in ('Geral', 'Por bloco', 'Detalhada'):
            self.nivel_integral.addItem(n)
        f.addRow('Detalhamento', self.nivel_integral)
        self.nivel_integral.activated.connect(self._nivel_origem)
        self.uniforme_integral = QCheckBox('Exibir todos os corredores na mesma cor')
        self.uniforme_integral.setChecked(True)
        r.addWidget(self.uniforme_integral)
        botao(r, 'Escolher cor dos corredores…', self._escolher_cor_integral)
        botao(r, 'Mostrar no QGIS', self.mostrar_mapa_integral)
        botao(r, 'Restaurar visibilidade das camadas', self.restaurar_mapa_integral)
        self.arvore_integral = QTreeWidget()
        self.arvore_integral.setHeaderHidden(True)
        self.arvore_integral.setUniformRowHeights(True)
        self.arvore_integral.setMaximumHeight(190)
        self.arvore_integral.currentItemChanged.connect(self._detalhar_arvore_integral)
        self.arvore_integral.itemExpanded.connect(self._expandir_arvore_integral)
        navegar_registros(self.arvore_integral, self._navegar_arvore_integral,
                          lambda i: self.menu_macro_integral(self._registro_arvore(i)),
                          self.restaurar_mapa_integral)
        r.addWidget(self.arvore_integral)
        self.detalhe_arvore_integral = aviso()
        r.addWidget(self.detalhe_arvore_integral)
        self.acoes_integral = botao(r, 'Ações da visão macro ▾')
        menu = QMenu(self.acoes_integral)
        menu.addAction('Mostrar caminho até a área selecionada',
                       lambda: self.localizar_macro_integral(self._alvo_area_integral(), True, True))
        menu.addAction('Exportar rede alcançável…', lambda: self.exportar_integral(None, 'REDE'))
        menu.addAction('Exportar corredores apresentados…', lambda: self.exportar_integral(None, 'CORREDORES'))
        menu.addAction('Exportar vários blocos…', self._exportar_blocos_integral)
        menu.addAction('Exportar área selecionada…', lambda: self.exportar_integral(self._alvo_area_integral(), 'AREA'))
        menu.addAction('Exportar caminho até a área…', lambda: self.exportar_integral(self._alvo_area_integral(), 'CAMINHO'))
        menu.addAction('Abrir agrupamento automático original', self._abrir_automatico_integral)
        self.acoes_integral.setMenu(menu)
        self.central.paginas.currentChanged.connect(self._sair_macro_integral)

    def _sair_macro_integral(self, *_):
        if self.central.paginas.currentWidget() is not self:
            self.mapa_integral.restaurar()

    def _mostrar_escolha_origens(self, *_):
        self.origens_integral.setVisible(self.origem_integral.currentData() in ('SUBCONJUNTO', 'COMPARAR'))

    def origens_da_fotografia_integral(self):
        self.origem_integral.clear()
        self.origens_integral.clear()
        self.origem_integral.addItem('Todas as origens habilitadas', 'TODAS')
        self.origem_integral.addItem('Escolher várias origens', 'SUBCONJUNTO')
        self.origem_integral.addItem('Comparar duas origens', 'COMPARAR')
        self.origem_integral.addItem('Sem origens · diagnóstico estrutural', 'NENHUMA')
        for u, n in self.nomes.items():
            self.origem_integral.addItem(n, ('ORIGEM', u))
            item = QListWidgetItem(n)
            item.setData(Qt.UserRole, u)
            self.origens_integral.addItem(item)
        self.area_integral.clear()
        self.area_integral.addItem('Todas as áreas', None)
        for u in self.areas_foto:
            self.area_integral.addItem(self._nome_area(u), u)
        self._mostrar_escolha_origens()

    def calcular_macro_integral(self):
        if not self.foto or self.central.ocupado():
            return
        modo = self.origem_integral.currentData()
        ids = None
        if isinstance(modo, (tuple, list)):
            ids = [modo[1]]
        elif modo in ('SUBCONJUNTO', 'COMPARAR'):
            ids = [i.data(Qt.UserRole) for i in self.origens_integral.selectedItems()]
            if not ids or (modo == 'COMPARAR' and len(ids) != 2):
                self.status.setText('Selecione duas origens para comparar.' if modo == 'COMPARAR' else 'Selecione as origens.')
                return
        elif modo == 'NENHUMA':
            ids = []
        foto, pasta = self.foto, self._pasta_resultados()
        criterios = dict(minimo_m=self.minimo_integral.value(), orientar_areas=self.orientar_integral.isChecked(),
                         comparar=modo == 'COMPARAR')
        escopo = sorted(ids if ids is not None else foto['origens_validas'])
        if self.macro_integral and self.macro_integral['origens'] == escopo and self.macro_integral['parametros'] == criterios:
            self.mostrar_mapa_integral()
            return
        assinatura = motor.assinatura(escopo, criterios)
        anterior = next((r for r in reversed(self._projeto()['bases']) if r.get('macro_assinatura') == assinatura
                         and r.get('topologia_uid') == foto['uuid'] and Path(r['base']).is_file()), None)
        if anterior:
            self.central.ao_abrir_trabalho(self.reabrir(anterior), self, anterior, cartografar=True)
            return
        nome = 'Visão macro · ' + self._nomes(escopo)
        def calcular(p, e):
            m = motor.analisar(foto, ids, **criterios, cancelar=p, etapa=e)
            return self._gravar(pasta, motor.trabalho(foto, m, nome), p, e)
        def pronto(r):
            self._registrar(r)
        worker = self.tarefa('Calculando a visão macro por origem', calcular, pronto)
        if worker:
            op = self.app.atividades.atual
            worker.finished.connect(lambda: self.mostrar_mapa_integral() if op.estado == 'CONCLUIDO'
                                    and self.central.paginas.currentWidget() is self else None)

    def carregar_macro_integral(self, d):
        self.mapa_integral.restaurar()
        self._alvo_integral = None
        self._isolado_integral = None
        self.macro_integral = m = (d or {}).get('macro_origem')
        self._grupos_macro = {}
        self._filhos_integral = {}
        self.arvore_integral.clear()
        self.detalhe_arvore_integral.clear()
        self.referencia_integral.clear()
        self.referencia_integral.addItem('Síntese das origens selecionadas', None)
        self.resumo_integral.clear()
        self._resultado_integral.setEnabled(bool(m))
        self._resultado_integral.setChecked(bool(m))
        self.nivel_integral.setCurrentIndex(0)
        if not m:
            return
        self.minimo_integral.setValue(m['parametros']['minimo_m'])
        self.orientar_integral.setChecked(m['parametros']['orientar_areas'])
        ids = m['origens']
        modo = ('COMPARAR' if m['parametros']['comparar'] else ('ORIGEM', ids[0]) if len(ids) == 1
                else 'TODAS' if set(ids) == set(self.nomes) else 'SUBCONJUNTO' if ids else 'NENHUMA')
        self.origem_integral.setCurrentIndex(max(0, self.origem_integral.findData(modo)))
        for i in range(self.origens_integral.count()):
            item = self.origens_integral.item(i)
            item.setSelected(item.data(Qt.UserRole) in ids)
        for u in m.get('referencias_por_origem', {}):
            self.referencia_integral.addItem(self._nomes([u]), u)
        for tabela, lista in (('MACRO_CORREDORES', m['corredores']), ('MACRO_BLOCOS', m['blocos']),
                              ('MACRO_DETALHES', m['detalhados'])):
            for r in lista:
                self._grupos_macro[tabela, r['uid']] = r
        areas = {}
        for i, os in m['areas_segmentos'].items():
            for u, metros in os.items():
                r = areas.setdefault(u, dict(uid=u, nome=self._nome_area(u), segmentos=[], comprimento_m=0.))
                r['segmentos'].append(int(i))
                r['comprimento_m'] += metros
        for u, r in areas.items():
            self._grupos_macro['MACRO_AREAS', u] = r
        c = m['cobertura']
        self.resumo_integral.setText(
            f"{len(ids)} origem(ns) · {c['pipes_alcancaveis']}/{c['pipes_escopo']} Pipes alcançáveis "
            f"· {c['alcancavel_m']:,.1f} m em {len(m['blocos'])} blocos.\n"
            f"{c['corredores_m']:,.1f} m em corredores · {c['rede_restante_m']:,.1f} m de rede restante "
            f"· {c['pipes_parciais']} Pipes parcialmente alcançáveis."
            + (f"\n{c['pipes_sem_acesso']} Pipes sem acesso às origens consideradas." if ids else
               '\nAlcance indeterminado. Consulte os blocos topológicos detalhados.'))
        if c['partes_sem_aresta'] or c['referencias_pendentes']:
            self.resumo_integral.setText(self.resumo_integral.text() +
                f"\n{len(c['partes_sem_aresta'])} partes sem aresta · {len(c['referencias_pendentes'])} referências pendentes.")
        self._construir_arvore_integral()

    def _blocos_integral(self):
        m = self.macro_integral
        a = self.area_integral.currentData()
        u = self.referencia_integral.currentData()
        return [b for b in m['blocos'] if (not u or u in b['origens'])
                and (not a or a in b['areas'] or a in b['areas_declaradas'])]

    def _alterar_area_integral(self, *_):
        if self.macro_integral:
            self.atualizar_tabela()
            self.central.agendar_estado_visual()

    def _alvo_area_integral(self):
        return self._grupos_macro.get(('MACRO_AREAS', self.area_integral.currentData()))

    def _nivel_origem(self, *_):
        cats = ('MACRO_CORREDORES', 'MACRO_BLOCOS', 'MACRO_DETALHES')
        self.categoria.setCurrentIndex(self.categoria.findData(cats[self.nivel_integral.currentIndex()]))
        self.central.agendar_estado_visual()

    def _construir_arvore_integral(self):
        from collections import defaultdict

        m = self.macro_integral
        self._filhos_integral = filhos = defaultdict(list)
        ids = {c['uid'] for c in m['corredores']}
        for c in m['corredores']:
            filhos[c['pai']].append(('MACRO_CORREDORES', c['uid']))
        for b in m['blocos']:
            inicio = next((u for u in b['corredores'] if u in ids), b['corredor_vizinho'])
            filhos[inicio].append(('MACRO_BLOCOS', b['uid']))
        raiz = QTreeWidgetItem(self.arvore_integral, [self._nomes(m['origens']) if m['origens'] else 'Sem origens'])
        raiz.setExpanded(True)
        self._expandir_arvore_integral(raiz)

    def _expandir_arvore_integral(self, item):
        if item.childCount():
            return
        chave = item.data(0, Qt.UserRole)
        for tab, u in self._filhos_integral.get(chave[1] if chave else None, ()):
            r = self._grupos_macro[tab, u]
            filho = QTreeWidgetItem(item, [r['nome']])
            filho.setData(0, Qt.UserRole, (tab, u))
            if u in self._filhos_integral:
                filho.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

    def _registro_arvore(self, indice):
        chave = indice.data(Qt.UserRole)
        return self._grupos_macro.get(tuple(chave)) if chave else None

    def _detalhar_arvore_integral(self, atual, _):
        if atual is not None:
            r = self._registro_arvore(self.arvore_integral.indexFromItem(atual))
            self.detalhe_arvore_integral.setText(self.detalhe_macro_integral(r) if r else '')

    def _navegar_arvore_integral(self, indice, aproximar):
        self.localizar_macro_integral(self._registro_arvore(indice), aproximar)

    def tabela_macro_integral(self, tipo):
        m = self.macro_integral or {}
        if tipo == 'MACRO_CONEXOES':
            rs = []
            if m:
                resolucoes = self.foto.get('resolucoes_conexoes', {})
                por_porta = {tuple(p): n['uid'] for n in self.foto['nos'] for p in n['portas']}
                rs = [dict(r, uid=r['uuid'], resolucao=resolucoes.get(r['uuid'], 'NÃO APLICADA'),
                           nos=sorted({por_porta[tuple(p)] for p in r['portas'] if tuple(p) in por_porta}))
                      for r in self.foto['participantes'] if r['tipo'] == 'CONEXAO']
            return tipo, ('Conexão', 'Situação', 'Topologia', 'Nós'), rs, lambda r: (
                r.get('nome'), r['situacao'], r['resolucao'], len(r['nos']))
        if tipo == 'MACRO_ORIGENS':
            rs = [dict(uid='|'.join(fs), origens=fs, segmentos=es, nome=self._nomes(fs),
                       comprimento_m=sum(self.foto['arestas'][i]['comprimento_m'] for i in es))
                  for fs, es in motor.acessos_comparados(m).items()] if m else []
            return tipo, ('Origens consideradas', 'Acesso', 'Segmentos', 'Comprimento (m)'), rs, lambda r: (
                r['nome'], 'Compartilhado' if len(r['origens']) > 1 else 'Exclusivo' if r['origens'] else
                'Sem acesso' if m['origens'] else 'Indeterminado', len(r['segmentos']), r['comprimento_m'])
        if tipo == 'MACRO_SEGMENTOS':
            extras, pontes = set(m.get('alternativas', ())), set(m.get('pontes', ()))
            ids = m.get('alcancaveis', ()) if m.get('origens') else range(len(self.foto['arestas'])) if m else ()
            rs = [dict(e, uid=str(i), segmentos=[i], nome=str(self.originais[e['tubo']].get('id') or e['tubo'][:8]),
                       tipo='Ponte' if i in pontes else 'Fora da árvore de referência' if i in extras else 'Referência')
                  for i in ids for e in [self.foto['arestas'][i]]]
            return tipo, ('Pipe GIS', 'Trecho', 'Comprimento (m)', 'Função', 'Geometria'), rs, lambda r: (
                r['nome'], r['uid'], r['comprimento_m'], r['tipo'],
                'Proposta' if self.originais[r['tubo']].get('proposta_uid') else
                'Divisão virtual' if (r['inicio'], r['fim']) != (0., 1.) else 'Cadastro')
        if tipo == 'MACRO_NOS':
            a = m.get('arvore', {})
            arts = set(m.get('articulacoes', ()))
            rs = [dict(n, nome=n['uid'][:10], distancia=metros, articulacao=n['uid'] in arts)
                  for n, metros in zip((self.foto or {}).get('nos', ()), a.get('distancias', ()))
                  if metros is not None or not m['origens']]
            return tipo, ('Nó', 'Distância em rede (m)', 'Articulação'), rs, lambda r: (
                r['nome'], r['distancia'], 'Sim' if r['articulacao'] else '—')
        rs = self._blocos_integral() if m and tipo == 'MACRO_BLOCOS' else (
            r for (tab, _), r in self._grupos_macro.items() if tab == tipo)
        return tipo, ('Nome', 'Tipo', 'Comprimento (m)', 'Pipes', 'Origens', 'Áreas GIS'), rs, lambda r: (
            r.get('nome', r['uid'][:8]), r.get('tipo', 'Área GIS'), r.get('comprimento_m'),
            len(r['pipes']) if 'pipes' in r else None, self._nomes(r.get('origens', ())),
            ', '.join(self._nome_area(u) for u in r.get('areas', ())))

    def detalhe_macro_integral(self, r):
        if r.get('tipo') == 'CONEXAO':
            return f"{r.get('nome') or r['uid']} · {r['situacao']} · {r['resolucao']} · {len(r['portas'])} portas."
        if 'xy' in r:
            return (f"Nó {r['uid']} · {r['distancia']:,.1f} m pela rede." if r['distancia'] is not None
                    else f"Nó {r['uid']} · distância a origem indeterminada.")
        return (f"{r.get('nome', r['uid'][:8])} · {len(r['segmentos'])} segmentos. "
                f"{len(r.get('fronteiras', ()))} nós de fronteira · {len(r.get('corredores', ()))} corredores associados "
                f"· {len(r.get('alternativas', ()))} segmentos fora da árvore de referência. "
                f"Organização {r.get('criterio', r.get('tipo', 'espacial')).lower()} · "
                f"{len(r.get('pontes', ()))} segmentos-ponte. "
                + ('Associação declarada com ' + ', '.join(self._nome_area(u) for u in r['areas_declaradas'])
                   if r.get('areas_declaradas') else ''))

    def _escolher_cor_integral(self):
        cor = QColorDialog.getColor(QColor(self._cor_integral), self, 'Cor dos corredores')
        if cor.isValid():
            self._cor_integral = cor.name()
            self.mostrar_mapa_integral()

    def restaurar_mapa_integral(self):
        self.mapa_integral.restaurar()
        self.central.mapa.limpar()
        self._alvo_integral = self._isolado_integral = None
        self.central.agendar_estado_visual()

    def _macro_de_referencia(self, m, origem):
        if origem:
            return dict(m, corredores=m['referencias_por_origem'][origem]['corredores'])
        return m

    def _tarefa_cartografica(self, nome, operacao, pronto):
        resultados = []
        worker = self.tarefa(nome, operacao, resultados.append)
        if worker:
            op = self.app.atividades.atual
            worker.finished.connect(lambda: self._com_erro(lambda: pronto(resultados[0]))
                                    if resultados and op.estado == 'CONCLUIDO' else None)
        return worker

    def mostrar_mapa_integral(self, checked=False, *, aproximar=False, ao_mostrar=None, isolado=None):
        if not self.macro_integral or self.central.ocupado():
            return
        d, geo = self.dados, self.geo
        m = self.macro_integral
        origem = self.referencia_integral.currentData()
        modo = self.visao_integral.currentData()
        alvo = self._grupos_macro.get(tuple(isolado)) if isolado else None
        if alvo:
            modo = 'BLOCO' if isolado[0] == 'MACRO_BLOCOS' else 'CORREDOR'
        blocos = self._blocos_integral()
        camada_ids = {r['uid'] for r in d['foto'].get('fontes', ())}
        camadas = self.central.modelo_gis.camadas()
        fontes = next((r.get('fontes', ()) for r in revisoes(self._projeto())
                       if r['uuid'] == d['foto'].get('modelo_rev')), ())
        sobrepostas = {c.id() for r in fontes if r['uid'] in camada_ids and (c := identificar(r, camadas))}
        ids = [origem] if origem and modo not in ('INFLUENCIA', 'COMPARACAO') else m['origens']
        origens = {}
        for u in ids:
            try:
                origens[u] = geo.referencia(geo.origens[u])
            except (ValueError, RuntimeError):
                origens[u] = None
        def calcular(p, _):
            mapa = plano(d['foto'], self._macro_de_referencia(m, origem), modo, blocos, cor, uniforme, alvo)
            return preparar(geo, mapa, origens, p)
        def pronto(resultado):
            if self.dados is not d or self.central.paginas.currentWidget() is not self:
                return
            self.central.mapa.limpar()
            self._alvo_integral = None
            self._isolado_integral = isolado if alvo else None
            self.mapa_integral.publicar(d['uuid'], geo.crs, resultado, sobrepostas)
            if aproximar:
                from qgis.core import QgsGeometry
                geometrias = []
                for _, _, _, wkb in resultado[0]:
                    g = QgsGeometry()
                    g.fromWkb(wkb)
                    geometrias.append(('tubo', g))
                self.central.mapa.destacar_investigacao(geometrias, geo.crs, True, toda_extensao=True)
                self.central.mapa.limpar()
            self.status.setText('Mapa da visão macro atualizado.' if not resultado[2] else
                                f'{len(resultado[2])} segmentos sem geometria para representar.')
            self.central.agendar_estado_visual()
            if ao_mostrar:QTimer.singleShot(0, ao_mostrar)
        cor, uniforme = self._cor_integral, self.uniforme_integral.isChecked()
        self._tarefa_cartografica('Preparando mapa da visão macro', calcular, pronto)

    def localizar_macro_integral(self, r, aproximar, percurso=False):
        if not r or not self.macro_integral or self.central.ocupado():
            return
        d, geo = self.dados, self.geo
        origem = self.referencia_integral.currentData()
        m = self.macro_integral
        self._alvo_integral = None
        if 'xy' in r:
            self.central.mapa.destacar_investigacao([('evento', geo.no(r['uid']))], geo.crs, aproximar)
            return
        if r.get('tipo') == 'CONEXAO':
            itens = [('evento', geo.no(n)) for n in r['nos']]
            if not itens and (g := geo.referencia(r)):
                itens = [('evento', g)]
            self.central.mapa.destacar_investigacao(itens, geo.crs, aproximar)
            return
        def preparar_destaque(p, _):
            from auditoria_fronteiras.modelos import verificar_cancelamento
            from qgis.core import QgsGeometry

            es = motor.caminho(d['foto'], m, r['segmentos'], origem, p) if percurso else r['segmentos']
            gs = []
            for i in es:
                verificar_cancelamento(p)
                if (g := geo.trecho(i)) and not g.isEmpty():
                    gs.append(g)
            geo_linhas = QgsGeometry.collectGeometry(gs) if gs else None
            nos = r.get('nos', [])
            itens = [('tubo', geo_linhas)] if geo_linhas else []
            if r.get('tipo') in ('TRONCO', 'RAMAL'):
                itens.extend((('inicio_corredor', geo.no(nos[0])), ('fim_corredor', geo.no(nos[-1]))))
            pontos = [geo.no(n) for n in r.get('fronteiras', [])]
            if any(pontos):
                itens.append(('ramificacao', QgsGeometry.collectGeometry([n for n in pontos if n])))
            areas = sorted({u for i in es for u in m['areas_segmentos'].get(str(i), {}) if u != r['uid']}) if percurso else []
            return itens, len(es), len(gs), areas
        def pronto(resultado):
            if self.dados is not d or self.central.paginas.currentWidget() is not self:
                return
            itens, total, visiveis, areas = resultado
            exibido = self.central.mapa.destacar_investigacao(itens, geo.crs, aproximar, toda_extensao=True)
            self.mapa_integral.atenuar(bool(exibido))
            alvo = next((tab for tab, u in self._grupos_macro if u == r['uid']), None)
            if alvo:
                self._alvo_integral = [alvo, r['uid'], percurso]
            texto = (f'{visiveis}/{total} segmentos com geometria.' if total else
                     'Nenhum caminho de referência até os destinos a partir desta origem.')
            if areas:
                texto += ' O percurso intercepta ' + ', '.join(self._nome_area(u) for u in areas) + '.'
            self.status.setText(texto)
            self.central.agendar_estado_visual()
        self._tarefa_cartografica('Preparando destaque da visão macro', preparar_destaque, pronto)

    def _testar_alternativa_integral(self, r):
        d, geo = self.dados, self.geo
        u = self.referencia_integral.currentData()
        def pronto(resultado):
            if self.dados is not d or self.central.paginas.currentWidget() is not self:
                return
            self.status.setText(resultado['situacao'])
            if resultado.get('alternativa'):
                itens = [('tubo', geo.trecho(i)) for i in resultado['referencia']]
                itens += [('evento', geo.trecho(i)) for i in resultado['alternativa']['segmentos']]
                self.central.mapa.destacar_investigacao(itens, geo.crs, True, toda_extensao=True)
        self._tarefa_cartografica('Testando alternativa sem Pipe físico compartilhado',
            lambda p, _: motor.alternativa(d['foto'], d['macro_origem'], r['segmentos'], u, p), pronto)

    def menu_macro_integral(self, r):
        if not r or 'segmentos' not in r:
            return []
        m = self.macro_integral
        alcançado = bool(r['segmentos']) and ('origens' not in r or bool(r['origens']))
        caminho = '' if m['origens'] and alcançado else 'Este resultado não tem caminho de referência.'
        acoes = [('Mostrar caminho desde o reservatório', lambda: self.localizar_macro_integral(r, True, True), caminho),
                 ('Testar alternativa independente até um destino representativo…',
                  lambda: self._testar_alternativa_integral(r), caminho),
                 ('Exportar seleção…', lambda: self.exportar_integral(r, r.get('tipo', 'AREA')), caminho),
                 ('Exportar percurso completo…', lambda: self.exportar_integral(r, 'CAMINHO'), caminho)]
        if r.get('tipo') in ('TRONCO', 'RAMAL', 'MACRO'):
            tabela = 'MACRO_BLOCOS' if r['tipo'] == 'MACRO' else 'MACRO_CORREDORES'
            acoes.insert(0, ('Mostrar somente este conjunto',
                             lambda: self.mostrar_mapa_integral(aproximar=True, isolado=[tabela, r['uid']])))
            acoes.append(('Renomear…', lambda: self._editar_integral(r, 'RENOMEAR_BLOCO' if r['tipo'] == 'MACRO'
                                                                  else 'RENOMEAR_CORREDOR')))
        if r.get('tipo') == 'MACRO':
            acoes += [('Agrupar com bloco adjacente…', lambda: self._editar_integral(r, 'AGRUPAR')),
                      ('Dividir por segmentos…', lambda: self._editar_integral(r, 'DIVIDIR')),
                      ('Associar área GIS…', lambda: self._editar_integral(r, 'ASSOCIAR_AREA'))]
        if r.get('alternativas'):
            acoes.append(('Destacar segmentos fora da árvore', lambda: self.localizar_macro_integral(
                dict(r, segmentos=r['alternativas'], tipo='ALTERNATIVAS'), True)))
        return acoes

    def _escolher_itens_integral(self, titulo, opcoes):
        d = QDialog(self)
        d.setWindowTitle(titulo)
        v = QVBoxLayout(d)
        lista = QListWidget()
        lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for uid, nome in opcoes:
            i = QListWidgetItem(nome)
            i.setData(Qt.UserRole, uid)
            i.setCheckState(Qt.Unchecked)
            lista.addItem(i)
        v.addWidget(lista)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(d.accept)
        b.rejected.connect(d.reject)
        v.addWidget(b)
        if d.exec_() != QDialog.Accepted:
            return []
        return [i.data(Qt.UserRole) for j in range(lista.count()) if (i := lista.item(j)).checkState() == Qt.Checked]

    def _editar_integral(self, r, acao):
        if self.central.ocupado():
            return
        if acao.startswith('RENOMEAR'):
            valor, ok = QInputDialog.getText(self, 'Renomear', 'Novo nome', text=r['nome'])
        elif acao == 'DIVIDIR':
            valor = self._escolher_itens_integral('Segmentos do novo bloco', (
                (i, f"{self.originais[self.foto['arestas'][i]['tubo']].get('id') or 'Pipe'} · trecho {i}")
                for i in r['segmentos']))
            ok = bool(valor)
        else:
            if acao == 'AGRUPAR':
                vizinhos = {u for v in self.macro_integral['ligacoes'] if r['uid'] in v['blocos'] for u in v['blocos']}
                opcoes = [(b['uid'], b['nome']) for b in self.macro_integral['blocos']
                          if b['uid'] in vizinhos and b['uid'] != r['uid']]
            else:
                opcoes = [(u, self._nome_area(u)) for u in self.areas_foto]
            if not opcoes:
                self.status.setText('Nenhuma opção disponível para este ajuste.')
                return
            itens = {f'{nome} · {u[:8]}': u for u, nome in opcoes}
            chave, ok = QInputDialog.getItem(self, 'Organizar bloco', 'Escolha', list(itens), 0, False)
            valor = itens.get(chave)
        if not ok:
            return
        from .revisao_macro_gis import revisar
        d, pasta = self.dados, self._pasta_resultados()
        self.tarefa('Salvando revisão da visão macro',
                    lambda p, e: self._gravar(pasta, revisar(d, acao, r['uid'], valor, p), p, e), self._registrar)

    def _abrir_automatico_integral(self):
        antigo = (self.dados or {}).get('automatico_macro')
        if not antigo:
            self.status.setText('Este trabalho contém o agrupamento automático original.')
            return
        r = next((r for r in self._projeto()['bases'] if r['uuid'] == antigo and r['tipo'] == 'ESTRUTURA_GIS'), None)
        if r:
            self.central.ao_abrir_trabalho(self.reabrir(r), self, r, cartografar=True)
        else:
            self.status.setText('O trabalho automático não está disponível no projeto.')

    def _exportar_blocos_integral(self):
        bs = self._blocos_integral()
        ids = set(self._escolher_itens_integral('Exportar blocos', ((b['uid'], b['nome']) for b in bs)))
        if ids:
            self.exportar_integral(dict(uid=sorted(ids), segmentos=[i for b in bs if b['uid'] in ids
                                                                  for i in b['segmentos']]), 'BLOCOS')

    def exportar_integral(self, r, tipo, formato=None):
        if not self.macro_integral or self.central.ocupado():
            return
        d = self.dados
        origem = self.referencia_integral.currentData()
        m = self._macro_de_referencia(self.macro_integral, origem)
        if tipo == 'REDE':
            segmentos = [i for i in m['alcancaveis'] if not origem
                         or origem in m['componentes'][m['componente_segmento'][i]]['origens']]
        elif tipo == 'CORREDORES':
            visiveis = {i for b in self._blocos_integral() for i in b['segmentos']}
            segmentos = [i for c in m['corredores'] for i in c['segmentos'] if i in visiveis]
        else:
            segmentos = r['segmentos'] if r else []
        if not segmentos:
            self.status.setText('Escolha um escopo com segmentos para exportar.')
            return
        incluir = False
        if formato is None:
            d_opcoes = QDialog(self)
            d_opcoes.setWindowTitle('Exportar visão macro')
            v = QVBoxLayout(d_opcoes)
            f = QComboBox()
            for rotulo, k in (('GeoPackage', 'GPKG'), ('Shapefile', 'ESRI Shapefile'), ('Tabelas CSV', 'CSV')):
                f.addItem(rotulo, k)
            formulario(v).addRow('Formato', f)
            incluir_b = QCheckBox('Incluir segmentos de referência externos à seleção')
            incluir_b.setVisible(tipo not in ('CAMINHO', 'REDE'))
            v.addWidget(incluir_b)
            botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            v.addWidget(botoes)
            botoes.accepted.connect(d_opcoes.accept)
            botoes.rejected.connect(d_opcoes.reject)
            if d_opcoes.exec_() != QDialog.Accepted:
                return
            formato, incluir = f.currentData(), incluir_b.isChecked()
        pasta = QFileDialog.getExistingDirectory(self, 'Pasta de exportação')
        if not pasta:
            return
        from .exportar_macro_origem import exportar
        def salvar(p, e):
            ids = motor.caminho(d['foto'], m, segmentos, origem, p) if tipo == 'CAMINHO' else segmentos
            return exportar(d, pasta, formato, ids, tipo=tipo, alvo=r['uid'] if r else None,
                            incluir_referencia=incluir, origem=origem, cancelar=p, etapa=e)
        self.tarefa('Exportando visão macro', salvar, lambda path: self.status.setText('Exportado em ' + str(path)))

    def estado_macro_integral(self):
        return dict(cor=self._cor_integral, uniforme=self.uniforme_integral.isChecked(), vista=self.visao_integral.currentData(),
                    area=self.area_integral.currentData(), referencia=self.referencia_integral.currentData(),
                    nivel=self.nivel_integral.currentIndex(), aberto=self._resultado_integral.isChecked(),
                    mapa=self.mapa_integral.ativo(), alvo=self._alvo_integral, isolado=self._isolado_integral)

    def recuperar_estado_macro_integral(self, v):
        cor = QColor(v.get('cor', PADRAO))
        self._cor_integral = cor.name() if cor.isValid() else PADRAO
        self.uniforme_integral.setChecked(bool(v.get('uniforme', True)))
        for k, w in (('vista', self.visao_integral), ('area', self.area_integral), ('referencia', self.referencia_integral)):
            i = w.findData(v.get(k))
            if i >= 0:
                w.setCurrentIndex(i)
        nivel = v.get('nivel', 0)
        if isinstance(nivel, int) and 0 <= nivel < self.nivel_integral.count():
            self.nivel_integral.setCurrentIndex(nivel)
        self._resultado_integral.setChecked(v.get('aberto', True))
