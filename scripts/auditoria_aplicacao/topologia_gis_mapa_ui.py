"""Ferramentas de mapa vinculadas ao painel e ao contexto em edição."""

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QTimer, Qt
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsProject

from .complementos_gis_ui import _nome
from .investigacao_gis import geometria
from .mapa_topologia_gis import (
    FerramentaMapa, IndiceSelecao, _ponto, _transformar, escolher,
    fracao_clicada, geometria_referencia, pontos_portas,
)


class MapaGIS:
    def _configuracao_alterada(self,*_):
        self._resultado_historico=False
        self._atualizar_acoes()
        self._indicar_rascunho()
        self.agendar_mapa()

    def agendar_mapa(self,*_):
        if not self.uid_projeto:return
        self._timer_mapa.start(25)

    def _atualizar_mapa(self):
        if self.central.projetos.dados['ativo']!=self.uid_projeto:return
        self._com_erro(self.atualizar_mapa)

    def atualizar_mapa(self):
        hip=self._hip_ativa
        d=self.dados
        historico=self._resultado_historico and d
        controles_iguais=self._edicao_limpa is not None and self._assinatura_edicao()==self._edicao_limpa
        edicao_fixada=hip and hip.get('formato')==2 and controles_iguais
        if historico or edicao_fixada:
            data=d['data_utc'] if historico else hip['data_utc']
            registros={r['uuid']:r for r in self._historicas if r['data_utc']<=data}
        else:
            registros=dict(self.registros)
        if historico:
            crs=QgsCoordinateReferenceSystem(d['crs'])
            registros.update({r['uuid']:r for r in d.get('participantes',[])})
            resolucoes=d.get('resolucoes_conexoes',{})
            invalidas={r.get('origem') for r in d['diagnosticos'] if r['tipo']=='EQUIPAMENTO_PENDENTE'}
            ativos={r['uuid'] for r in d.get('participantes',[])
                    if r['tipo']=='CONEXAO' and r['uuid'] not in invalidas
                    and resolucoes.get(r['uuid'])!='REFERENCIA_ALTERADA'}|set(d['origens_validas'])|set(d.get('propostas_aplicadas',()))
            nome=d['nome']+' · '+d['uuid'][:8]
        else:
            crs=self.crs.crs()
            registros.update(self._pinos)
            ativos=set(self._selecionados())
            nome=(hip['nome'] if hip else 'Hipótese temporária')+(' · em edição' if not controles_iguais else '')
            if d and (QgsCoordinateReferenceSystem(d['crs'])!=crs or d['modelo_rev']!=self._revisao().get('uuid')
                    or set(self._redes_marcadas())!={f['uid'] for f in d['fontes'] if f['categoria']=='PIPE'}):
                d=None
            elif d and (not hip or (d.get('hipotese') or {}).get('rev')!=hip['rev'] or not controles_iguais):
                # Candidatas geométricas servem de referência. Os componentes da execução
                # anterior não representam a hipótese em edição.
                d=dict(d,componentes=[],diagnosticos=[x for x in d['diagnosticos'] if
                                                     x['tipo'] in ('CONEXAO_T','EXTREMIDADES_PROXIMAS','CRUZAMENTO')])
        if not crs.isValid():
            crs=QgsProject.instance().crs()
        preparados=[]
        for r in registros.values():
            if r['tipo'] not in ('ORIGEM','CONEXAO','PIPE') or r.get('excluido'):continue
            if not r.get('pontos_rede') and d:
                pontos=pontos_portas(r['portas'],self.tubos)
                r=dict(r,pontos_rede=pontos,crs_rede=d['crs'])
            preparados.append(r)
        self.mapa_gis.atualizar(self.uid_projeto,crs,preparados,ativos,d,nome)
        self._tem_conexoes_mapa=any(papel=='conexoes' for papel,_ in self.mapa_gis.registros)
        self._atualizar_acoes()

    def iniciar_ferramenta(self,clique,concluir=None,cancelar=None):
        canvas=self.app.iface.mapCanvas()
        if canvas is None:return False
        self.cancelar_captura()
        anterior=canvas.mapTool()
        def sair(sucesso):
            if self._ferramenta is not sessao:return
            self.cancelar_captura(reabrir=False)
            cb=concluir if sucesso else cancelar
            if cb:cb()
        def desativada():
            if self._ferramenta is not sessao:return
            # O QGIS ainda está trocando de ferramenta durante este sinal.
            self.cancelar_captura(reabrir=False,restaurar=False)
            if cancelar:
                QTimer.singleShot(0,lambda:cancelar() if self._ferramenta is None else None)
        def seguro(p):
            if self._ferramenta is not sessao:return
            try:
                clique(p,sair)
            except Exception as erro:
                sair(False)
                self.status.setText('Seleção cancelada. '+str(erro))
        ferramenta=FerramentaMapa(canvas,seguro,lambda:sair(True),lambda:sair(False))
        sessao=(canvas,ferramenta,anterior)
        self._ferramenta=sessao
        self._finalizar_ferramenta=cancelar
        ferramenta.deactivated.connect(desativada)
        try:
            canvas.setMapTool(ferramenta)
            if canvas.mapTool() is not ferramenta:
                raise RuntimeError('O QGIS não ativou a ferramenta do Auditor.')
            tela=canvas.window()
            tela.raise_()
            tela.activateWindow()
            canvas.setFocus(Qt.OtherFocusReason)
        except (RuntimeError,TypeError) as erro:
            sair(False)
            self.status.setText(str(erro))
            return False
        return True

    def cancelar_captura(self,reabrir=True,restaurar=True):
        t=self._ferramenta
        if not t:return
        canvas,ferramenta,anterior=t
        cb=self._finalizar_ferramenta
        self._ferramenta=None
        self._finalizar_ferramenta=None
        self._mensagem_captura()
        if not sip.isdeleted(canvas) and not sip.isdeleted(ferramenta):
            if restaurar and canvas.mapTool() is ferramenta:
                if anterior is not None and not sip.isdeleted(anterior):canvas.setMapTool(anterior)
                else:canvas.unsetMapTool(ferramenta)
            ferramenta.deleteLater()
        if reabrir and cb:cb()

    def _mensagem_captura(self,texto=''):
        barra=getattr(self.app.iface,'messageBar',lambda:None)()
        atual=getattr(self,'_aviso_captura',None)
        if barra is not None and not sip.isdeleted(barra):
            if atual is not None and not sip.isdeleted(atual):
                barra.popWidget(atual)
            self._aviso_captura=barra.pushMessage('Water Network Auditor',texto,duration=0) if texto else None
        if texto:self.status.setText(texto)

    def _clique_metricas(self,p,crs):
        canvas=self.app.iface.mapCanvas()
        origem=canvas.mapSettings().destinationCrs()
        g=_transformar(QgsGeometry.fromPointXY(p),origem,crs)
        raio=8*canvas.mapUnitsPerPixel()
        medidas=[_transformar(_ponto((p.x()+raio,p.y())),origem,crs),
                 _transformar(_ponto((p.x(),p.y()+raio)),origem,crs)]
        return g,max(g.distance(o) for o in medidas)

    def _destacar_tubos_editor(self,dlg,crs):
        if self.central.ocupado():return
        geoms=[]
        for uid in dict.fromkeys(u for u,_ in dlg.portas):
            t=dlg.tubos.get(uid,{})
            g=t.get('geom') or geometria(t.get('wkb'))
            if g is not None:geoms.append(g)
        pontos=pontos_portas(dlg.portas,dlg.tubos)
        itens=[('evento',QgsGeometry.fromMultiPointXY([QgsPointXY(*xy) for xy in pontos]))] if pontos else []
        if dlg.tipo=='CONEXAO' and len(pontos)>=2:
            itens.append(('vinculo',QgsGeometry.fromPolylineXY([QgsPointXY(*xy) for xy in pontos])))
        if geoms:
            itens.insert(0,('tubo',QgsGeometry.collectGeometry(geoms)))
        self.central.mapa.destacar_investigacao(itens,crs)

    def _destacar_tubo_editor(self,dlg,uid,crs,aproximar):
        t=dlg.tubos.get(uid,{})
        g=t.get('geom') or geometria(t.get('wkb'))
        if not self.central.mapa.destacar_investigacao([('tubo',g)],crs,aproximar,toda_extensao=True):
            dlg.info.setText('Geometria indisponível para a tubulação escolhida.')

    def selecionar_no_editor(self,dlg,wkt,origem=False):
        if self.central.ocupado():
            dlg.info.setText('Aguarde a conclusão da atividade antes de selecionar no mapa.')
            return
        crs=QgsCoordinateReferenceSystem(wkt)
        elementos=dlg.equipamentos.values() if origem else dlg.tubos.values()
        atributo='_indice_equipamentos' if origem else '_indice_tubos'
        indice=getattr(dlg,atributo,None)
        if indice is None:
            indice=IndiceSelecao(elementos)
            setattr(dlg,atributo,indice)
        if not indice.elementos:
            dlg.info.setText('Nenhuma feição disponível no escopo atual.')
            return
        portas=list(dlg.portas)
        geometria_janela=dlg.saveGeometry()
        conclusao=False
        def existe():
            return not sip.isdeleted(self) and not sip.isdeleted(dlg) and self._editor is dlg
        def mostrar():
            nonlocal conclusao
            if conclusao or not existe():return
            conclusao=True
            dlg.restoreGeometry(geometria_janela)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            dlg.info.setText(f'{len(dlg.portas)} ponto(s) de conexão escolhidos.')
        def cancelar():
            if not existe():return
            dlg.portas=portas
            dlg.listar_portas()
            try:self._com_erro(lambda:self._destacar_tubos_editor(dlg,crs))
            finally:
                mostrar()
                dlg.info.setText('Seleção cancelada. Os pontos anteriores foram preservados.')
        def clique(p,sair):
            if not existe():sair(False);return
            g,tol=self._clique_metricas(p,crs)
            rs=indice.consultar(g,tol)
            escolha=escolher(self,rs,lambda r:_nome(r[2]))
            if escolha is None:
                self.status.setText('Clique mais perto de uma feição do escopo. Botão direito conclui e Esc cancela.')
                return
            _,uid,_,linha=escolha
            if origem:
                dlg.equipamento.setCurrentIndex(dlg.equipamento.findData(uid))
                sair(True)
            else:
                dlg.adicionar_mapa(uid,fracao_clicada(linha,g,tol))
                self._mensagem_captura(f'{len(dlg.portas)} ponto(s). Clique para adicionar. Botão direito: concluir. Esc: cancelar.')
        if self.iniciar_ferramenta(clique,mostrar,cancelar):
            dlg.hide()
            self._mensagem_captura('Clique nas tubulações para adicioná-las. Botão direito: concluir. Esc: cancelar.'
                                   if not origem else 'Selecione a origem no mapa. Esc: cancelar.')
        else:
            mostrar()
            dlg.info.setText('Não foi possível iniciar a seleção no mapa.')

    def capturar(self,registro=None):
        if self.central.ocupado():return
        def clique(p,sair):
            crs=self.app.iface.mapCanvas().mapSettings().destinationCrs()
            sair(True)
            if crs.isValid():
                QTimer.singleShot(0,lambda:self.editar('ORIGEM',anterior=registro,ponto=dict(xy=[p.x(),p.y()],crs=crs.toWkt())))
        if self.iniciar_ferramenta(clique):
            self._mensagem_captura('Clique no mapa para posicionar a origem. Esc ou botão direito cancela.')

    def consultar_mapa(self,revisar=False):
        if self.central.ocupado() or not self.mapa_gis.camadas:return
        def clique(p,sair):
            projeto=QgsProject.instance()
            camada=next((projeto.mapLayer(u) for u in self.mapa_gis.camadas.values() if projeto.mapLayer(u)),None)
            if camada is None:return
            pt,tol=self._clique_metricas(p,camada.crs())
            opcoes=self.mapa_gis.consultar(pt,camada.crs(),tol)
            if revisar:
                opcoes=[o for o in opcoes if o[1].get('tipo') in ('PIPE','CONEXAO','CONEXAO_T','CRUZAMENTO','EXTREMIDADES_PROXIMAS')]
            escolha=escolher(self,opcoes,lambda r:r[0])
            if not escolha:return
            sair(True)
            QTimer.singleShot(0,lambda:self.abrir_registro_mapa(escolha[1],revisar))
        if self.iniciar_ferramenta(clique):
            self._mensagem_captura('Selecione uma conexão no mapa. Esc cancela.' if revisar
                                   else 'Selecione um elemento visível no mapa. Esc cancela.')

    def abrir_registro_mapa(self,r,revisar=False):
        if r.get('tipo') in ('ORIGEM','CONEXAO','PIPE'):
            origem=r['tipo']=='ORIGEM'
            secao=self.orig_b if origem else self.conexoes_b
            tabela=self.participantes if origem else self.conexoes_lista
            secao.setChecked(True)
            if not origem:self.filtro_conexoes.setCurrentIndex(0)
            for i in range(tabela.count()):
                if tabela.item(i).data(Qt.UserRole)==r['uuid']:
                    tabela.setCurrentCell(i,0)
                    if not origem:self.filtrar_conexoes()
                    self.ensureWidgetVisible(tabela)
                    break
            if origem:self.detalhar_relacao(r)
            else:self.detalhar_conexao()
            self.destacar_relacao(r=r)
            if revisar:
                self._editar_relacao(r)
            return
        if self.selecionar_resultado_uid(r['uid'],r.get('tipo','COMPONENTES')):
            self.destacar()
            if revisar:self.revisar_conexao()

    def destacar_relacao(self,aproximar=False,r=None,extensao=False):
        r=r or self._registro_selecionado()
        if not r or self.central.ocupado():
            self.status.setText('Selecione uma fonte de água ou conexão disponível.')
            return
        crs=QgsCoordinateReferenceSystem((self.dados or {}).get('crs') or r.get('crs_rede') or self.crs.crs().toWkt())
        tubos=getattr(self,'tubos',{})
        def mostrar():
            crs_rede=QgsCoordinateReferenceSystem(r.get('crs_rede') or r.get('crs') or '')
            gs=[]
            for uid in dict.fromkeys(u for u,_ in r['portas']):
                tubo=geometria(tubos.get(uid,{}).get('wkb'))
                if tubo is None and crs_rede.isValid():
                    historico=geometria(r.get('geometrias_rede',{}).get(uid))
                    if historico is not None:tubo=_transformar(historico,crs_rede,crs)
                if tubo is not None:gs.append(tubo)
            itens=[('tubo',QgsGeometry.collectGeometry(gs))] if gs else []
            g=geometria_referencia(r,crs)
            fonte=r['tipo']=='ORIGEM'
            proposta=r['tipo']=='PIPE'
            if g is not None:itens.append(('vinculo' if proposta else 'equipamento' if fonte else 'evento',g))
            pontos=[_transformar(_ponto(xy),crs_rede,crs)
                    for xy in r.get('pontos_rede',[])] if crs_rede.isValid() else []
            if pontos:itens.append(('evento',QgsGeometry.collectGeometry(pontos)))
            if fonte and g is not None and g.type()==0 and not g.isMultipart():
                vinculos=[[QgsPointXY(g.asPoint()),QgsPointXY(p.asPoint())] for p in pontos if p.distance(g)>1e-8]
            elif not (fonte or proposta) and len(pontos)==2 and pontos[0].distance(pontos[1])>1e-8:
                vinculos=[[QgsPointXY(p.asPoint()) for p in pontos]]
            else:vinculos=[]
            if vinculos:itens.append(('vinculo',QgsGeometry.fromMultiPolylineXY(vinculos)))
            foco=g if fonte and not extensao else None
            if not self.central.mapa.destacar_investigacao(itens,crs,aproximar,toda_extensao=extensao,foco=foco):
                self.status.setText('Geometria indisponível para a fonte ou conexão selecionada.')
            elif not gs and r['portas']:
                self.status.setText('Localização destacada. As geometrias das tubulações desta revisão estão indisponíveis.')
        self._com_erro(mostrar)
