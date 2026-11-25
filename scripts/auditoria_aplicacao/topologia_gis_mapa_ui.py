"""Ferramentas de mapa vinculadas ao painel e ao contexto em edição."""

from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsProject

from .complementos_gis_ui import _nome
from .grafo_gis import ROTULOS
from .investigacao_gis import geometria
from .mapa_topologia_gis import (
    FerramentaMapa, IndiceSelecao, _ponto, _transformar, escolher,
    fracao_clicada, geometria_referencia, pontos_portas,
)


class MapaGIS:
    def _configuracao_alterada(self,*_):
        self._resultado_historico=False
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
                    and resolucoes.get(r['uuid'])!='REFERENCIA_ALTERADA'}|set(d['origens_validas'])
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
            if r['tipo'] not in ('ORIGEM','CONEXAO'):continue
            if not r.get('pontos_rede') and d:
                pontos=pontos_portas(r['portas'],self.tubos)
                r=dict(r,pontos_rede=pontos,crs_rede=d['crs'])
            preparados.append(r)
        self.mapa_gis.atualizar(self.uid_projeto,crs,preparados,ativos,d,nome)

    def iniciar_ferramenta(self,clique,concluir=None,cancelar=None):
        canvas=self.app.iface.mapCanvas()
        if canvas is None:return False
        self.cancelar_captura()
        anterior=canvas.mapTool()
        def sair(sucesso):
            if self._ferramenta is None:return
            self.cancelar_captura(reabrir=False)
            cb=concluir if sucesso else cancelar
            if cb:QTimer.singleShot(0,cb)
        def seguro(p):
            self._com_erro(lambda:clique(p,sair))
        ferramenta=FerramentaMapa(canvas,seguro,lambda:sair(True),lambda:sair(False))
        self._ferramenta=(canvas,ferramenta,anterior)
        self._finalizar_ferramenta=cancelar
        ferramenta.deactivated.connect(lambda:sair(False))
        canvas.setMapTool(ferramenta)
        return True

    def cancelar_captura(self,reabrir=True):
        t=self._ferramenta
        if not t:return
        from qgis.PyQt import sip
        canvas,ferramenta,anterior=t
        cb=self._finalizar_ferramenta
        self._ferramenta=None
        self._finalizar_ferramenta=None
        if not sip.isdeleted(canvas) and not sip.isdeleted(ferramenta):
            if canvas.mapTool() is ferramenta:
                if anterior is not None and not sip.isdeleted(anterior):canvas.setMapTool(anterior)
                else:canvas.unsetMapTool(ferramenta)
            ferramenta.deleteLater()
        if reabrir and cb:cb()

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
            t=dlg.tubos[uid]
            g=t.get('geom') or geometria(t.get('wkb'))
            if g is not None:geoms.append(g)
        self.central.mapa.limpar()
        if geoms:
            self.central.mapa.destacar_investigacao([('tubo',QgsGeometry.collectGeometry(geoms))],crs)

    def selecionar_no_editor(self,dlg,wkt,origem=False):
        if self.central.ocupado():return
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
        editor=self._editor
        def mostrar():
            if self._editor is not editor:return
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        def cancelar():
            if self._editor is not editor:return
            dlg.portas=portas
            dlg.listar_portas()
            self._destacar_tubos_editor(dlg,crs)
            mostrar()
        def clique(p,sair):
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
        dlg.hide()
        if self.iniciar_ferramenta(clique,mostrar,cancelar):
            self.status.setText('Clique nas feições. Botão direito conclui a seleção. Esc restaura os vínculos anteriores.')
        else:mostrar()

    def capturar(self,registro=None):
        if self.central.ocupado():return
        def clique(p,sair):
            crs=self.app.iface.mapCanvas().mapSettings().destinationCrs()
            sair(True)
            if crs.isValid():
                QTimer.singleShot(0,lambda:self.editar('ORIGEM',anterior=registro,ponto=dict(xy=[p.x(),p.y()],crs=crs.toWkt())))
        if self.iniciar_ferramenta(clique):
            self.status.setText('Clique no mapa para posicionar a origem. Esc ou botão direito cancela.')

    def consultar_mapa(self,revisar=False):
        if self.central.ocupado() or not self.mapa_gis.camadas:return
        def clique(p,sair):
            projeto=QgsProject.instance()
            camada=next((projeto.mapLayer(u) for u in self.mapa_gis.camadas.values() if projeto.mapLayer(u)),None)
            if camada is None:return
            pt,tol=self._clique_metricas(p,camada.crs())
            opcoes=self.mapa_gis.consultar(pt,camada.crs(),tol)
            escolha=escolher(self,opcoes,lambda r:r[0])
            if not escolha:return
            sair(True)
            QTimer.singleShot(0,lambda:self.abrir_registro_mapa(escolha[1],revisar))
        if self.iniciar_ferramenta(clique):
            self.status.setText('Clique num símbolo visível. Esc cancela.')

    def abrir_registro_mapa(self,r,revisar=False):
        if r.get('tipo') in ('ORIGEM','CONEXAO'):
            self.orig_b.setChecked(True)
            for i in range(self.participantes.count()):
                if self.participantes.item(i).data(Qt.UserRole)==r['uuid']:
                    self.participantes.setCurrentCell(i,0)
                    self.ensureWidgetVisible(self.participantes)
                    break
            self.detalhar_relacao(r)
            self.destacar_relacao(r=r)
            if revisar:
                self.editar(r['tipo'],r,candidato=self._candidato_da_relacao(r))
            return
        if self.selecionar_resultado_uid(r['uid'],r.get('tipo','COMPONENTES')):
            self.destacar()
            if revisar:self.revisar_conexao()

    def destacar_relacao(self,aproximar=False,r=None):
        r=r or self._registro_selecionado()
        if not r or self.central.ocupado():return
        crs=QgsCoordinateReferenceSystem((self.dados or {}).get('crs') or self.crs.crs().toWkt())
        tubos=getattr(self,'tubos',{})
        gs=[]
        for uid in dict.fromkeys(u for u,_ in r['portas']):
            wkb=tubos.get(uid,{}).get('wkb')
            g=geometria(wkb)
            if g is not None:gs.append(g)
        def mostrar():
            itens=[('tubo',QgsGeometry.collectGeometry(gs))] if gs and not aproximar else []
            g=geometria_referencia(r,crs)
            if g is None and r.get('pontos_rede'):
                crs_portas=QgsCoordinateReferenceSystem(r.get('crs_rede') or '')
                g=QgsGeometry.collectGeometry([_transformar(_ponto(xy),crs_portas,crs)
                                              for xy in r['pontos_rede']])
            if g is not None:itens.append(('equipamento' if r['tipo']=='ORIGEM' else 'evento',g))
            if g is None and gs:itens=[('tubo',QgsGeometry.collectGeometry(gs))]
            if itens:self.central.mapa.destacar_investigacao(itens,crs,aproximar)
        self._com_erro(mostrar)
