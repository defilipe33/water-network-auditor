"""Seleção, navegação e exportação da visão macro sobre EstruturaGIS."""

from collections import defaultdict

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QInputDialog,
                                QMessageBox, QSpinBox, QTreeWidget, QTreeWidgetItem)
from qgis.core import QgsCategorizedSymbolRenderer, QgsExpression, QgsFeatureRequest, QgsProject

from .agrupamento_corredores_gis import FUNCOES, parametros
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import navegar_registros
from .persistencia_grafo_gis import revisoes, salvar_revisao
from .representacao_corredores_gis import CAMADA, CorredoresNoMapa, exportar_tracado


PAPEIS = {'REFERENCIA':'Referência', 'ALTERNATIVA':'Alternativa'}
SITUACOES = {'CONTINUO':'Contínuo', 'CIRCUITO':'Circuito fechado', 'SEM_ORIENTACAO':'Sem orientação de origem'}
ALTERNATIVAS = {
    'DISJUNTA_VERIFICADA':'Sem Pipe compartilhado','PARCIAL_VERIFICADA':'Com Pipe compartilhado',
    'NAO_TESTADA_LIMITE':'Não testada no orçamento','PIPE_OBRIGATORIO':'Pipe obrigatório para a origem',
    'CAMINHO_UNICO':'Caminho único','SEM_DISJUNTA_DA_ROTA_ESCOLHIDA':'Sem alternativa disjunta da referência',
    'NO_DA_ORIGEM':'Destino coincide com origem',
}


class CorredoresAgrupadosUI:
    def montar_configuracao_macro(self, layout):
        _, opcoes = expansivel(layout, 'Destinos representativos')
        campos = formulario(opcoes)
        self.modo_macro = QComboBox()
        self.modo_macro.addItem('Regiões distantes · selecionar automaticamente', 'AUTOMATICO')
        self.modo_macro.addItem('Destinos selecionados no mapa ou associados a zonas', 'MANUAL')
        self.modo_macro.addItem('Combinar destinos manuais e automáticos', 'COMBINADO')
        campos.addRow('Destinos', self.modo_macro)
        self.max_macro = QSpinBox()
        self.max_macro.setRange(1,200)
        self.max_macro.setValue(24)
        campos.addRow('Limite de destinos no modo automático ou combinado', self.max_macro)
        self.dist_macro = QDoubleSpinBox()
        self.dist_macro.setRange(0,10_000_000)
        self.dist_macro.setSuffix(' m')
        campos.addRow('Distância mínima pela rede', self.dist_macro)
        opcoes.addWidget(aviso('A seleção automática usa a distância à origem alcançável mais próxima pelo grafo. '
                              'Use destinos manuais para estudar pontos ou zonas específicos.'))
        self.modo_macro.currentIndexChanged.connect(self.mudar_modo_macro)
        self.executar_macro_b = botao(layout, 'Identificar corredores agrupados', lambda:self.calcular(agrupado=True))
        self.executar_macro_b.setObjectName('Principal')
        self.agrupar_salvo_b = botao(layout,'Agrupar trajetos deste trabalho…',self.agrupar_salvo)
        self.agrupar_salvo_b.hide()

    def mudar_modo_macro(self):
        usar = self.modo_macro.currentData()!='MANUAL'
        self.max_macro.setEnabled(usar)
        self.dist_macro.setEnabled(usar)

    def montar_resultados_macro(self, layout):
        self.macro = None
        self.camada_macro = None
        self.nomes_macro = {}
        self.macro_b, area = expansivel(layout, 'Visão macro e árvore de percursos')
        self.macro_info = aviso()
        area.addWidget(self.macro_info)
        campos = formulario(area)
        self.fonte_macro = QComboBox()
        self.nivel_macro = QComboBox()
        self.visao_macro = QComboBox()
        for nome, valor in [('Resumido',1),('Intermediário',2),('Detalhado',3)]:
            self.nivel_macro.addItem(nome,valor)
        for nome, valor in [('Todos os corredores',None),('Críticos','CRITICO'),('Alternativas','ALTERNATIVO')]:
            self.visao_macro.addItem(nome,valor)
        self.ramais_macro = QCheckBox('Mostrar ramais secundários')
        self.ramais_macro.setChecked(True)
        campos.addRow('Fonte', self.fonte_macro)
        campos.addRow('Nível da visualização', self.nivel_macro)
        campos.addRow('Exibir', self.visao_macro)
        area.addWidget(self.ramais_macro)
        for combo in (self.fonte_macro,self.nivel_macro,self.visao_macro):
            combo.currentIndexChanged.connect(self.atualizar_macro)
        self.ramais_macro.toggled.connect(self.atualizar_macro)
        botao(area,'Mostrar camada dos corredores', self.mostrar_macro)
        self.arvore_macro = QTreeWidget()
        self.arvore_macro.setHeaderHidden(True)
        self.arvore_macro.setMinimumHeight(113)
        self.arvore_macro.setMaximumHeight(210)
        self.arvore_macro.setUniformRowHeights(True)
        self.arvore_macro.itemExpanded.connect(self.expandir_macro)
        self.arvore_macro.currentItemChanged.connect(self.selecionar_arvore_macro)
        area.addWidget(self.arvore_macro)
        navegar_registros(self.arvore_macro,self.localizar_arvore_macro,self.menu_arvore_macro,
                          limpar=self.limpar_macro_mapa,
                          elegivel=lambda i: i.data(Qt.UserRole) is not None)
        area.addWidget(aviso('Quadrado verde e losango laranja marcam os extremos da sequência. '
                              'A cruz roxa indica ramificação. Linhas tracejadas mostram trechos apenas de alternativas.'))
        self.macro_b.hide()

    def configuracao_macro(self):
        return parametros(self.modo_macro.currentData(), self.max_macro.value(), self.dist_macro.value())

    def carregar_macro(self, resultado):
        self.restaurar_opacidade_macro()
        self.camada_macro = None
        self._chave_arvore = None
        self._alvo_macro=None
        self.nomes_macro = {}
        self.macro = None
        self.agrupar_salvo_b.setVisible(bool(resultado and 'agrupamento' not in resultado and
                                            (resultado['rotas'] or not resultado['fontes'])))
        if not resultado or 'agrupamento' not in resultado:
            self.macro_b.hide()
            return
        ids = {c['uid'] for c in resultado['agrupamento']['corredores']}
        anterior = self._projeto().get('arquivo_complementos')
        if anterior:
            def ler_nomes():
                regs = revisoes(anterior, self.projeto_uid, tipo='CORREDOR_NOME')
                self.nomes_macro = {r['uuid']:r for r in regs if r['uuid'] in ids and
                                    r['analise_uid']==resultado['agrupamento']['analise_uid']}
            self._com_erro(ler_nomes)
        self.macro = CorredoresNoMapa(self.geo, self.nomes_macro)
        self.fonte_macro.blockSignals(True)
        self.fonte_macro.clear()
        self.fonte_macro.addItem('Todas as fontes',None)
        for u in resultado['fontes']:
            self.fonte_macro.addItem(self._nomes([u]),u)
        self.fonte_macro.blockSignals(False)
        self.macro_b.show()
        self.atualizar_macro(recarregar_tabela=False)

    def atualizar_macro(self, *_, recarregar_tabela=True):
        if self.macro is None:
            return
        fonte = self.fonte_macro.currentData()
        nivel = self.nivel_macro.currentData()
        funcao = self.visao_macro.currentData()
        ps = [p for p in self.macro.percursos.values() if not fonte or p['origem']==fonte]
        vistos = {}
        for p in ps:
            if p['papel']=='REFERENCIA':
                vistos[p['destino']] = max(vistos.get(p['destino'],0),p['comprimento_m'])
        alvos = sorted(vistos,key=lambda u:(-vistos[u],u))
        if nivel != 3 and not funcao:
            alvos = alvos[:max(1,(len(alvos)*nivel+2)//3)]
        alvos = set(alvos)
        ps = [p for p in ps if p['destino'] in alvos]
        ids = {u for p in ps for u in p['corredores']}
        if not self.macro.percursos:
            ids = self.macro.corredores.keys()
        self.visiveis_macro = {u for u in ids if self._aceitar_corredor(self.macro.corredores[u],funcao)}
        amostra = self.macro.dados.get('amostra')
        mensagem = f'{len(self.visiveis_macro)}/{len(self.macro.corredores)} corredores visíveis. '
        if not self.dados['fontes']:
            mensagem += 'Sem origens topológicas. As sequências mostram a estrutura não orientada.'
        elif amostra is not None:
            mensagem += (f"{len(self.dados['destinos'])} destinos representativos de {amostra['elegiveis']} "
                         "folhas elegíveis da floresta de referência.")
        elif not self.macro.percursos:
            mensagem += 'Escolha destinos manuais ou use o modo automático para gerar percursos.'
        self.macro_info.setText(mensagem)
        self.carregar_arvore_macro(ps, fonte, nivel, funcao)
        self.aplicar_filtro_macro()
        if recarregar_tabela and self.categoria.currentData()=='AGRUPADOS':
            self.atualizar_tabela()

    def _aceitar_corredor(self, c, funcao):
        if funcao:
            return funcao in c['funcoes']
        return (self.ramais_macro.isChecked() or not c['percursos'] or
                c['referencias']>1 or 'CRITICO' in c['funcoes'] or not c['referencias'])

    def carregar_arvore_macro(self, ps, fonte, nivel, funcao):
        chave = (fonte,nivel,funcao,self.ramais_macro.isChecked())
        if chave==self._chave_arvore:
            return
        self._chave_arvore = chave
        self.arvore_macro.clear()
        raizes = defaultdict(list)
        for p in ps:
            if not funcao or set(p['corredores']) & self.visiveis_macro:
                raizes[p['origem']].append((p['uid'],0))
        for u, registros in raizes.items():
            item = QTreeWidgetItem(self.arvore_macro,[self._nomes([u])])
            self.adicionar_futuras_macro(item,registros)
        if not self.macro.percursos and self.visiveis_macro:
            pai = QTreeWidgetItem(self.arvore_macro,['Estrutura sem orientação · consulte também a tabela'])
            pai.setData(0,Qt.UserRole+1,('ESTRUTURA',0))
            QTreeWidgetItem(pai,['…'])

    def adicionar_futuras_macro(self,item,registros):
        item.setData(0,Qt.UserRole+1,('PERCURSOS',registros))
        QTreeWidgetItem(item,['…'])

    def expandir_macro(self,item):
        pendente = item.data(0,Qt.UserRole+1)
        if pendente is None:
            return
        item.setData(0,Qt.UserRole+1,None)
        item.takeChildren()
        modo, dados = pendente
        if modo=='ESTRUTURA':
            ids = sorted(self.visiveis_macro,key=lambda u:self.macro.corredores[u]['codigo'])
            for u in ids[dados:dados+200]:
                self.item_corredor(item,u)
            if dados+200 < len(ids):
                resto=QTreeWidgetItem(item,['Mais corredores…'])
                resto.setData(0,Qt.UserRole+1,(modo,dados+200))
                QTreeWidgetItem(resto,['…'])
            return
        ramais = defaultdict(list)
        for uid, pos in dados:
            p = self.macro.percursos[uid]
            itens = p['corredores']
            if pos<len(itens):
                ramais[itens[pos]].append((uid,pos+1))
            else:
                d = self.geo.destinos[p['destino']]
                a = QTreeWidgetItem(item,[f"{d['nome']} · {PAPEIS[p['papel']]}"])
                a.setData(0,Qt.UserRole,('PERCURSO',uid))
        for u, registros in ramais.items():
            self.adicionar_futuras_macro(self.item_corredor(item,u),registros)

    def item_corredor(self,item,u):
        c = self.macro.corredores[u]
        no = QTreeWidgetItem(item,[c['nome']])
        no.setData(0,Qt.UserRole,('CORREDOR',u))
        return no

    def selecionar_arvore_macro(self,item,_):
        if item is not None and item.data(0,Qt.UserRole):
            tipo,u = item.data(0,Qt.UserRole)
            self.localizar_macro(tipo,u,False)
            if tipo=='CORREDOR':
                self.detalhe.setText(self.detalhe_corredor(self.macro.corredores[u]))

    def localizar_arvore_macro(self,indice,aproximar):
        self.localizar_macro(*indice.data(Qt.UserRole),aproximar)

    def menu_arvore_macro(self,indice):
        tipo,u = indice.data(Qt.UserRole)
        if tipo=='CORREDOR':
            return self.menu_corredor(self.macro.corredores[u])
        return [('Exportar percurso completo…',lambda:self.exportar_macro(tipo,u))]

    def mostrar_macro(self,checked=False,*,ao_mostrar=None):
        if not self.macro or not self.macro.corredores:
            self.status.setText('Calcule corredores agrupados antes de mostrar a camada.')
            return
        projeto = QgsProject.instance()
        uid = self.dados['uuid']
        existente = next((c for c in projeto.mapLayers().values() if c.customProperty('wna/tecnico')==CAMADA and
                         c.customProperty('wna/uid')==uid),None)
        if existente is not None:
            existente.setSubsetString('')
            if existente.featureCount():
                self.camada_macro = existente
                for u in self.nomes_macro:
                    self.atualizar_nome_na_camada(u)
                self.ativar_camada_macro()
                self.central.agendar_estado_visual()
                if ao_mostrar:ao_mostrar()
                return
        macro = self.macro
        def publicar(registros):
            self.camada_macro = macro.publicar(registros)
            self.ativar_camada_macro()
            self.central.agendar_estado_visual()
            if ao_mostrar:ao_mostrar()
        self.tarefa('Preparando geometrias dos corredores',lambda parar,_:macro.preparar_camada(parar),publicar)

    def ativar_camada_macro(self):
        projeto=QgsProject.instance()
        raiz=projeto.layerTreeRoot()
        for c in projeto.mapLayers().values():
            if c.customProperty('wna/tecnico')==CAMADA and (n:=raiz.findLayer(c.id())) is not None:
                n.setItemVisibilityChecked(c.id()==self.camada_macro.id())
        raiz.findLayer(self.camada_macro.id()).setItemVisibilityCheckedParentRecursive(True)
        self.aplicar_filtro_macro()

    def atualizar_nome_na_camada(self,u):
        camada=self.camada_macro_ativa()
        if camada is None:
            return
        nome=self.macro.corredores[u]['nome']
        renderer=camada.renderer()
        if isinstance(renderer,QgsCategorizedSymbolRenderer):
            i=renderer.categoryIndexForValue(u)
            if i>=0:renderer.updateCategoryLabel(i,nome)
        expressao='"UUID" = '+QgsExpression.quotedString(u)
        req=QgsFeatureRequest().setFilterExpression(expressao).setFlags(QgsFeatureRequest.NoGeometry)
        f=next(camada.getFeatures(req),None)
        if f is not None:
            idx=camada.fields().indexFromName('Nome')
            camada.dataProvider().changeAttributeValues({f.id():{idx:nome}})
        visao=getattr(self.app.iface,'layerTreeView',lambda:None)()
        if visao is not None:
            visao.refreshLayerSymbology(camada.id())

    def camada_macro_ativa(self):
        from qgis.PyQt import sip
        return self.camada_macro if self.camada_macro is not None and not sip.isdeleted(self.camada_macro) else None

    def aplicar_filtro_macro(self):
        camada = self.camada_macro_ativa()
        if camada is None:
            return
        ids = self.visiveis_macro
        filtro = '' if len(ids)==len(self.macro.corredores) else (
            '"UUID" IN ('+','.join(QgsExpression.quotedString(u) for u in sorted(ids))+')' if ids else 'FALSE')
        camada.setOpacity(1.)
        if not camada.setSubsetString(filtro) and camada.subsetString()!=filtro:
            self.status.setText('O provedor não aplicou o filtro da camada. A tabela continua filtrada.')
        camada.triggerRepaint()

    def restaurar_opacidade_macro(self):
        camada = self.camada_macro_ativa()
        if camada is not None and camada.opacity()!=1.:
            camada.setOpacity(1.)
            camada.triggerRepaint()

    def limpar_macro_mapa(self):
        self.restaurar_opacidade_macro()
        self.central.mapa.limpar()

    def localizar_macro(self,tipo,u,aproximar,ramais=False):
        if not self.macro or self.central.ocupado():
            return
        def mostrar():
            itens = (self.macro.destaque(self.macro.corredores[u],ramais) if tipo=='CORREDOR' else
                     self.macro.destaque_percurso(self.macro.percursos[u]))
            if self.central.mapa.destacar_investigacao(itens,self.geo.crs,aproximar,toda_extensao=True):
                self._alvo_macro=(tipo,u)
                camada = self.camada_macro_ativa()
                if camada is not None:
                    camada.setOpacity(.24)
                    camada.triggerRepaint()
            else:
                self.status.setText('Geometria cartográfica indisponível para esta seleção.')
        self._com_erro(mostrar)

    def tabela_corredores(self):
        colunas = ('Código','Nome','Função','Fonte da rota','Destinos','Comprimento (m)','Pipes','Diâmetros (mm)',
                   'Destinos dependentes','Conectados','Alternativas','Situação')
        rs = (c for c in self.macro.corredores.values() if c['uid'] in self.visiveis_macro) if self.macro else []
        def valores(c):
            return (c['codigo'], c['nome'], ', '.join(FUNCOES[f] for f in c['funcoes']), self._nomes(c['origens']),
                    len(c['destinos']), c['comprimento_m'], len(c['tubos']), ', '.join(map(str,c['diametros_mm'])),
                    len(c['dependentes']),c['conectados_n'],sum(
                        self.macro.percursos[u]['papel']=='ALTERNATIVA' for u in c['percursos']),
                    SITUACOES[c['estado']])
        return 'AGRUPADOS', colunas, rs, valores

    def detalhe_corredor(self,c):
        nomes = [self.geo.destinos[u]['nome'] for u in c['destinos']]
        return (f"{c['nome']} · {len(c['segmentos'])} segmentos · {len(c['tubos'])} Pipes físicos · "
                f"{c['referencias']} percursos de referência. Extremos {c['nos'][0][:8]} / {c['nos'][-1][:8]}. "
                f"Destinos {', '.join(nomes[:8]) or '—'}{'…' if len(nomes)>8 else ''}. "
                f"Fontes exclusivas de algum destino {self._nomes(c['fontes_exclusivas'])}. "
                f"Fontes alcançáveis {self._nomes(c['fontes_alcancaveis'])}. "
                f"{len(c['anteriores'])} anteriores e {len(c['posteriores'])} posteriores nas rotas. "
                f"Redundância {', '.join(ALTERNATIVAS.get(a,a) for a in c['alternativas']) or 'indeterminada'}. "
                f"Cortes fora do limite {c['cortes_indeterminados']}.")

    def agrupar_salvo(self):
        from datetime import datetime, timezone
        from uuid import uuid4
        from .agrupamento_corredores_gis import agrupar
        if self.central.ocupado() or not self.dados or self.macro:
            return
        d = dict(self.dados, uuid=uuid4().hex, referencia=self.dados['uuid'],
                 nome=self.dados['nome']+' · corredores agrupados',data_utc=datetime.now(timezone.utc).isoformat())
        pasta = self._pasta_resultados()
        def trabalho(parar,etapa):
            etapa(0,'Agrupando os trajetos já salvos')
            d['agrupamento'] = agrupar(d,parametros(),cancelar=parar)
            return self._gravar(pasta,d,parar,etapa)
        self.tarefa('Agrupando trajetos salvos',trabalho,self._registrar)

    def menu_corredor(self,c):
        u=c['uid']
        return [
            ('Ver corredor e ramais',lambda:self.localizar_macro('CORREDOR',u,True,True),
             '' if c['posteriores'] else 'A sequência não tem ramais posteriores registrados.'),
            ('Ver percurso completo até o destino…',lambda:self.escolher_percurso(c),'' if c['percursos'] else 'Sem percurso.'),
            ('Consultar Pipes participantes',lambda:self.consultar_pipes_corredor(c)),
            ('Renomear corredor…',lambda:self.renomear_corredor(c)),
            ('Histórico de nomes',lambda:self.historico_corredor(c)),
            ('Exportar corredor selecionado…',lambda:self.exportar_macro('CORREDOR',u)),
            ('Criar conjunto para WaterGEMS…',lambda:self.criar_conjunto_do_resultado(c,'CORREDORES')),
            ('Exportar percurso completo…',lambda:self.escolher_percurso(c,exportar=True),
             '' if c['percursos'] else 'Sem percurso.'),
        ]

    def consultar_pipes_corredor(self,c):
        linhas = [f"{self.geo.pipes[u]['id'] or u[:8]} · {self.geo.pipes[u]['camada']}" for u in c['tubos']]
        msg = QMessageBox(self)
        msg.setWindowTitle('Pipes de '+c['nome'])
        msg.setText(f"{len(linhas)} tubulações físicas nesta sequência.")
        msg.setDetailedText('\n'.join(linhas))
        msg.exec_()

    def escolher_percurso(self,c,exportar=False):
        ps = [self.macro.percursos[u] for u in c['percursos']]
        nomes = [f"{self._nomes([p['origem']])} → {self.geo.destinos[p['destino']]['nome']} · "
                 f"{PAPEIS[p['papel']]} · {p['rota'][:8]}" for p in ps]
        nome,ok = QInputDialog.getItem(self,'Percurso completo','Origem e destino',nomes,editable=False)
        if ok:
            u = ps[nomes.index(nome)]['uid']
            if exportar:self.exportar_macro('PERCURSO',u)
            else:self.localizar_macro('PERCURSO',u,True)

    def renomear_corredor(self,c):
        nome,ok = QInputDialog.getText(self,'Renomear corredor','Nome',text=c['nome'])
        if not ok or not nome.strip() or nome.strip()==c['nome']:
            return
        def salvar():
            base=self._complementos(True)
            u=c['uid']
            antigo=self.nomes_macro.get(u,{}).get('rev')
            r=salvar_revisao(base,self.projeto_uid,'CORREDOR_NOME',
                             dict(analise_uid=self.macro.dados['analise_uid'],nome=nome.strip()),u,antigo)
            self.nomes_macro[u]=r
            self.macro.corredores[u]=dict(c,nome=r['nome'])
            self.atualizar_nome_na_camada(u)
            self._chave_arvore=None
            self.atualizar_macro()
            self.status.setText('Nome do corredor salvo em nova revisão.')
        self._com_erro(salvar)

    def historico_corredor(self,c):
        def mostrar():
            rs=revisoes(self._projeto().get('arquivo_complementos'),self.projeto_uid,c['uid'],tipo='CORREDOR_NOME')
            original=next(r['nome'] for r in self.macro.dados['corredores'] if r['uid']==c['uid'])
            linhas=['Nome original · '+original]+[r['data_utc'][:19]+' UTC · '+r['nome'] for r in rs]
            QMessageBox.information(self,'Histórico de nomes','\n'.join(linhas))
        self._com_erro(mostrar)

    def exportar_macro(self,tipo,u):
        if self.central.ocupado():
            return
        formatos={'GeoPackage':'GPKG','Shapefile':'ESRI Shapefile','CSV com relações':'CSV'}
        escolha,ok=QInputDialog.getItem(self,'Exportar '+tipo.lower(),'Formato',list(formatos),editable=False)
        if not ok:
            return
        modos={'Segmentos efetivamente usados':'SEGMENTOS','Pipes físicos completos':'PIPES'}
        modo,ok=QInputDialog.getItem(self,'Exportar '+tipo.lower(),'Representação',list(modos),editable=False)
        if not ok:
            return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de exportação')
        if pasta:
            d,nomes=self.dados,dict(self.nomes_macro)
            self.tarefa('Exportando '+tipo.lower(),
                        lambda p,e:exportar_tracado(d,tipo,u,pasta,formatos[escolha],modos[modo],p,e,nomes=nomes),
                        lambda destino:self.status.setText('Exportado em '+str(destino)))
