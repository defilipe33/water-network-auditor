"""Retomada de seleção, filtros, camadas e extensão sem editar a análise."""

from qgis.PyQt.QtCore import QTimer, Qt
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle

from . import estado_projeto as estado


CONTROLES_GIS=('busca','filtro_situacao','filtro_tipo','filtro_categoria','filtro_relevancia','filtro_regiao')


class VisualProjetoUI:
    def iniciar_estado_visual(self):
        self._timer_visual = QTimer(self)
        self._timer_visual.setSingleShot(True)
        self._timer_visual.setInterval(240)
        self._timer_visual.timeout.connect(self.salvar_estado_atual)
        canvas = self.app.iface.mapCanvas()
        if canvas is not None:
            canvas.extentsChanged.connect(self.agendar_estado_visual)
        QgsProject.instance().layerTreeRoot().visibilityChanged.connect(self.agendar_estado_visual)

    def agendar_estado_visual(self, *_):
        if self.paginas.isVisible():
            self._timer_visual.start()

    def estados_de_visualizacao(self):
        p=self.projetos.atual()
        if not p:return {}
        try:return estado.ler(self.app.catalogo.raiz,p,estado.VISUAL)
        except (OSError,ValueError,TypeError):return {}

    def _camadas_trabalho(self,pagina,tipo,uid):
        projeto=QgsProject.instance()
        if tipo=='TOPOLOGIA_GIS':
            camadas=pagina.mapa_gis.camadas
            return {k:projeto.mapLayer(i) for k,i in camadas.items() if projeto.mapLayer(i) is not None}
        gl={'ESTRUTURA_GIS':'estrutura','AUDITORIA_GIS':'gis'}.get(tipo)
        return {c.customProperty('wna/tecnico'):c for c in projeto.mapLayers().values()
                if gl and c.customProperty('wna/categoria')==gl and c.customProperty('wna/uid')==uid}

    def salvar_estado_atual(self, *, estrito=False):
        p=self.projetos.atual()
        if not p or not self.paginas.isVisible() or self.ocupado():return
        pagina=self.paginas.currentWidget()
        if pagina is None:return
        geo=self.__dict__
        if pagina is geo.get('conectividade_gis') and pagina.dados:
            tipo='TOPOLOGIA_GIS';d=pagina.dados;uid=d['uuid']
            item=pagina._selecionado()
            visual=dict(categoria=pagina.categoria.currentData(),filtro=pagina.busca.text(),
                        ordem=pagina.ordem.currentIndex(),coluna=pagina._ordem_coluna,
                        selecionado=item['uid'] if item else None,
                        comparacao=pagina._comparadas[0]['uuid'] if pagina.comparacao.isVisible()
                        and getattr(pagina,'_comparadas',None) else None)
        elif pagina is geo.get('estrutura_gis') and pagina.dados:
            tipo='ESTRUTURA_GIS';d=pagina.dados;uid=d['uuid']
            item=pagina.registro()
            visual=dict(categoria=pagina.categoria.currentData(),filtro=pagina.filtro.text(),
                        modalidade=pagina.modalidade.currentData(),area=pagina.areas.currentData(),
                        areas=sorted(pagina.escopo_areas() or ()),
                        coluna=pagina._ordem,selecionado=item['uid'] if item else None,
                        comparacao=pagina.anterior_geo.d['uuid'] if pagina.diferencas
                        and getattr(pagina,'anterior_geo',None) else None)
            if pagina.macro:
                visual.update(nivel=pagina.nivel_macro.currentData(),fonte=pagina.fonte_macro.currentData(),
                              funcao=pagina.visao_macro.currentData(),ramais=pagina.ramais_macro.isChecked(),
                              arvore=pagina.macro_b.isChecked(),alvo_macro=pagina._alvo_macro)
            if pagina.macro_integral:
                visual['macro_integral']=pagina.estado_macro_integral()
            if d.get('blocos'):
                visual['blocos']=dict(fonte=pagina.fonte_blocos.currentData(),
                    corredor=pagina.corredor_blocos.currentData(),indisponivel=pagina.fonte_indisponivel.currentData(),
                    areas=[i.data(Qt.UserRole) for j in range(pagina.areas_blocos.count())
                           if (i:=pagina.areas_blocos.item(j)).checkState()==Qt.Checked])
        elif pagina is geo.get('analise_gis') and pagina.dossie and pagina.base:
            tipo='AUDITORIA_GIS';d={};uid=pagina.dossie['execucao_uid']
            visual=dict(filtros={k:self._valor_visual(getattr(pagina,k)) for k in CONTROLES_GIS},
                        selecionado=(pagina.selecionado or {}).get('uid'),evento=pagina._evento_uid)
        else:return
        if (d.get('projeto_uid') or p['uuid'])!=p['uuid'] or not self.projetos.contem(tipo,uid):return
        raiz=QgsProject.instance().layerTreeRoot()
        camadas=self._camadas_trabalho(pagina,tipo,uid)
        visibilidades = {k:n.isVisible() for k,c in camadas.items()
                         if (n:=raiz.findLayer(c.id())) is not None}
        if visibilidades:
            visual['camadas'] = visibilidades
        canvas=self.app.iface.mapCanvas()
        if canvas is not None:
            e=canvas.extent()
            visual['extensao']=[e.xMinimum(),e.yMinimum(),e.xMaximum(),e.yMaximum()]
            visual['crs_mapa']=canvas.mapSettings().destinationCrs().toWkt()
        visual['destaque']=bool(self.mapa.itens)
        self._guardar_visual(p,tipo,uid,estrito=estrito,visual=visual)

    @staticmethod
    def _valor_visual(w):
        return w.currentData() if hasattr(w,'currentData') else w.text()

    def _guardar_visual(self,p,tipo,uid,*,estrito=False,**dados):
        try:return estado.guardar_trabalho(self.app.catalogo.raiz,p,tipo,uid,**dados)
        except (OSError,ValueError,TypeError) as e:
            if estrito:raise
            self.pendencias.setText('Preferências de consulta indisponíveis. '+str(e))
            return {}

    def ao_abrir_trabalho(self,worker,pagina,r,cartografar=False,aproximar=False,comparar=False):
        if not worker:return
        operacao=self.app.atividades.atual
        projeto=self.projetos.dados['ativo']
        def depois():
            if operacao.estado!='CONCLUIDO' or projeto!=self.projetos.dados['ativo']:return
            if self.paginas.currentWidget() is not pagina:return
            self.restaurar_estado_trabalho(pagina,r,cartografar,aproximar,comparar)
        worker.finished.connect(lambda:QTimer.singleShot(0,depois))

    @staticmethod
    def _restaurar_widget(w,valor):
        if hasattr(w,'findData'):
            i=w.findData(valor)
            if i>=0:w.setCurrentIndex(i)
        elif isinstance(valor,str):w.setText(valor)

    @staticmethod
    def _ordem_validada(v,n):
        if isinstance(v,(tuple,list)) and len(v)==2 and isinstance(v[0],int) and 0<=v[0]<n:
            return v[0],bool(v[1])
        return None

    @staticmethod
    def _indicador(tabela,ordem):
        h=tabela.horizontalHeader()
        h.setSortIndicatorShown(bool(ordem))
        if ordem:h.setSortIndicator(ordem[0],Qt.DescendingOrder if ordem[1] else Qt.AscendingOrder)

    def restaurar_estado_trabalho(self,pagina,r,cartografar=False,aproximar=False,comparar=False):
        p=self.projetos.atual()
        if not p:return
        tipo,uid=r['tipo'],r['uuid']
        v=self.estados_de_visualizacao().get(f'{tipo}:{uid}',{})
        self._guardar_visual(p,tipo,uid,aberto=True)
        if v:
            if tipo=='TOPOLOGIA_GIS':
                self._restaurar_widget(pagina.categoria,v.get('categoria'))
                pagina.busca.setText(v.get('filtro',''))
                n=v.get('ordem')
                if isinstance(n,int) and 0<=n<pagina.ordem.count():pagina.ordem.setCurrentIndex(n)
                pagina._ordem_coluna=self._ordem_validada(v.get('coluna'),len(pagina._colunas_resultados()))
                self._indicador(pagina.resultados,pagina._ordem_coluna)
                pagina.mudar_resultados()
                pos=next((i for i,x in enumerate(pagina._lista_resultados) if x['uid']==v.get('selecionado')),None)
                if pos is not None:
                    pagina.paginar(pos//200)
                    pagina.resultados.setCurrentCell(pos%200,0)
            elif tipo=='ESTRUTURA_GIS':
                if 'modalidade' in v:self._restaurar_widget(pagina.modalidade,v['modalidade'])
                if 'area' in v:pagina.recuperar_areas_escopo(v)
                if pagina.macro_integral:
                    pagina.recuperar_estado_macro_integral(v.get('macro_integral', {}))
                if pagina.macro:
                    for k,w in [('nivel',pagina.nivel_macro),('fonte',pagina.fonte_macro),('funcao',pagina.visao_macro)]:
                        if k in v:self._restaurar_widget(w,v[k])
                    pagina.ramais_macro.setChecked(bool(v.get('ramais',True)))
                    pagina.macro_b.setChecked(bool(v.get('arvore')))
                if estado_blocos:=v.get('blocos'):
                    for chave,w in [('fonte',pagina.fonte_blocos),('corredor',pagina.corredor_blocos),
                                    ('indisponivel',pagina.fonte_indisponivel)]:
                        self._restaurar_widget(w,estado_blocos.get(chave))
                    areas=set(estado_blocos.get('areas',()))
                    for j in range(pagina.areas_blocos.count()):
                        i=pagina.areas_blocos.item(j)
                        i.setCheckState(Qt.Checked if i.data(Qt.UserRole) in areas else Qt.Unchecked)
                categoria=v.get('categoria')
                if categoria!='COMPARAR':
                    pagina.exibir_categoria(categoria)
                pagina.filtro.setText(v.get('filtro',''))
                pagina._ordem=self._ordem_validada(v.get('coluna'),len(pagina.dados_tabela()[1]))
                self._indicador(pagina.tabela,pagina._ordem)
                pagina.atualizar_tabela()
                pos=next((i for i,(x,_) in enumerate(pagina._linhas) if x['uid']==v.get('selecionado')),None)
                if pos is not None:
                    pagina.paginar(pos//200)
                    pagina.tabela.setCurrentCell(pos%200,0)
            elif tipo=='AUDITORIA_GIS':
                for k,valor in v.get('filtros',{}).items():
                    if k in CONTROLES_GIS:self._restaurar_widget(getattr(pagina,k),valor)
                pagina.listar(v.get('selecionado'))
                self._restaurar_widget(pagina.alvo,v.get('evento'))
        if tipo=='ESTRUTURA_GIS' and pagina.macro_integral:
            integral=v.get('macro_integral', {})
            alvo=integral.get('alvo')
            registro=pagina._grupos_macro.get(tuple(alvo[:2])) if isinstance(alvo,list) and len(alvo)==3 else None
            if integral.get('mapa') or cartografar:
                pagina.mostrar_mapa_integral(aproximar=aproximar and registro is None,
                                             isolado=integral.get('isolado'),
                                             ao_mostrar=lambda:pagina.localizar_macro_integral(registro, aproximar, alvo[2])
                                             if registro else None)
            elif registro and v.get('destaque'):
                pagina.localizar_macro_integral(registro, aproximar, alvo[2])
            if not aproximar:self._restaurar_extensao(v)
            return
        if cartografar or v.get('destaque'):
            if tipo=='ESTRUTURA_GIS':
                alvo=v.get('alvo_macro')
                if (pagina.categoria.currentData() not in ('BLOCOS','LIGACOES_BLOCOS') and
                        pagina.macro and isinstance(alvo,list) and len(alvo)==2 and
                        (alvo[0]=='CORREDOR' and alvo[1] in pagina.macro.corredores or
                         alvo[0]=='PERCURSO' and alvo[1] in pagina.macro.percursos)):
                    pagina.localizar_macro(alvo[0],alvo[1],aproximar)
                else:pagina.localizar_linha(pagina.tabela.currentIndex(),aproximar)
            elif tipo in ('TOPOLOGIA_GIS','AUDITORIA_GIS'):
                pagina.destacar(aproximar=aproximar)
        if not aproximar:self._restaurar_extensao(v)
        camadas=v.get('camadas',{})
        def visibilidade():
            if self.paginas.currentWidget() is not pagina:return
            raiz=QgsProject.instance().layerTreeRoot()
            for k,c in self._camadas_trabalho(pagina,tipo,uid).items():
                if k in camadas and (n:=raiz.findLayer(c.id())) is not None:
                    n.setItemVisibilityChecked(bool(camadas[k]))
            if tipo=='ESTRUTURA_GIS' and getattr(pagina,'_alvo_macro',None):
                if camada:=pagina.camada_macro_ativa():
                    camada.setOpacity(.24)
                    camada.triggerRepaint()
        if camadas and tipo=='ESTRUTURA_GIS':
            from .representacao_corredores_gis import CAMADA
            from .representacao_blocos_gis import CAMADA as CAMADA_BLOCOS
            if any(k not in (CAMADA,CAMADA_BLOCOS) for k in camadas):
                from .representacao_estrutura_gis import carregar_camadas
                pagina._com_erro(lambda:carregar_camadas(pagina.dados,pagina.geo))
            restaurar=[]
            if CAMADA in camadas and pagina.macro:
                restaurar.append(pagina.mostrar_macro)
            if CAMADA_BLOCOS in camadas and pagina.dados.get('blocos'):
                restaurar.append(pagina.mostrar_blocos_mapa)
            def proxima():
                if restaurar:
                    metodo=restaurar.pop(0)
                    QTimer.singleShot(0,lambda:metodo(ao_mostrar=proxima)
                                      if self.paginas.currentWidget() is pagina else None)
                else:visibilidade()
            proxima()
        elif camadas:
            QTimer.singleShot(80,visibilidade)
        comp=next((x for x in p['bases'] if x['tipo']==tipo and x['uuid']==v.get('comparacao')),None)
        if comparar or comp:
            def abrir_comparacao():
                if self.paginas.currentWidget() is not pagina:return
                if self.ocupado():
                    QTimer.singleShot(90,abrir_comparacao)
                elif comp:pagina.comparar(referencia=comp)
                else:pagina.comparar()
            QTimer.singleShot(90,abrir_comparacao)

    def _restaurar_extensao(self,v):
        canvas=self.app.iface.mapCanvas()
        e=v.get('extensao')
        if canvas is None or not estado.extensao_valida(e) or not v.get('crs_mapa'):return
        crs=QgsCoordinateReferenceSystem(v['crs_mapa'])
        alvo=canvas.mapSettings().destinationCrs()
        if not crs.isValid() or not alvo.isValid():return
        try:
            ret=QgsRectangle(*e)
            if crs!=alvo:
                trans=QgsCoordinateTransform(crs,alvo,QgsProject.instance())
                ret=trans.transformBoundingBox(ret)
            if not ret.isEmpty() and ret.isFinite():
                canvas.setExtent(ret)
                canvas.refresh()
        except (RuntimeError,ValueError):
            return
