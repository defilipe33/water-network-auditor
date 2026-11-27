"""Prévia do cadastro completo a partir do Modelo GIS e da análise de referência."""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QDialog, QFileDialog, QInputDialog, QMessageBox, QVBoxLayout
from qgis.core import QgsGeometry, QgsProject

from . import cadastro_exportavel as cadastro
from .entradas_grafo_gis import ler, preparar
from .modelo_gis import revisoes
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import acao_disponivel
from .conjuntos_modelagem_ui import CatalogoConjuntos


REGRAS={
    'A_DEFINIR':'Manter atividade a definir',
    'FORA_INATIVO':'Prever como inativos os Pipes fora da hipótese',
    'NA_HIPOTESE_ATIVO':'Prever como ativos os Pipes na hipótese',
}


class CadastroExportavelUI:
    def montar_exportacao_modelagem(self,layout):
        self.exportacoes_modelagem_b,v=expansivel(layout,'Exportar dados GIS para modelagem')
        v.addWidget(aviso('Prepare os Pipes e Junctions para conferência. O cadastro completo inclui redes isoladas e fontes fora da análise de referência.'))
        self.previa_cadastro_b=botao(v,'Prévia do cadastro completo…',lambda:self.prever_cadastro_completo())
        botao(v,'Exportar modelo para WaterGEMS…',lambda:self.prever_cadastro_completo(abrir_modelbuilder=True))
        botao(v,'Exportações ModelBuilder e conferência…',self.abrir_historico_modelbuilder)
        botao(v,'Exportar rede alcançável da visão macro…',lambda:self.exportar_integral(None,'REDE'))
        botao(layout,'Conjuntos para WaterGEMS…',lambda:self.prever_cadastro_completo(abrir_catalogo=True))

    def mostrar_comandos_modelbuilder(self):
        self.exportacoes_modelagem_b.setChecked(True)
        self.ensureWidgetVisible(self.execucoes if not self.foto else self.exportacoes_modelagem_b)

    def prever_cadastro_completo(self,*,abrir_catalogo=False,preselecao=None,abrir_modelbuilder=False,regra=None,ao_abrir=None):
        if not self.foto or self.central.ocupado():
            self.status.setText('Abra uma execução de conectividade e aguarde a atividade atual.')
            return
        foto=self.foto
        p=self._projeto()
        estado=self.central.estados_de_visualizacao().get(f"TOPOLOGIA_GIS:{foto['uuid']}",{}).get('exportacao_cadastro',{})
        if regra is None:
            chaves=list(REGRAS)
            rotulos=list(REGRAS.values())
            i=chaves.index(estado['regra']) if estado.get('regra') in REGRAS else 0
            rotulo,ok=QInputDialog.getItem(self,'Prévia do cadastro completo','Atividade pretendida no WaterGEMS',
                                          rotulos,i,False)
            if not ok:return
            regra=chaves[rotulos.index(rotulo)]
        modelos=revisoes(p)
        atual=next(reversed(modelos),{})
        if abrir_modelbuilder:
            atual=next((r for r in modelos if r['uuid']==foto.get('modelo_rev')),None)
            if atual is None:
                self.status.setText('A revisão do Modelo GIS usada pela execução não está disponível.')
                return
        fontes=atual.get('fontes',())
        if not any(f['categoria']=='PIPE' for f in fontes):
            self.status.setText('Inclua fontes de tubulação no Modelo GIS antes de gerar a prévia.')
            return
        origens=self._com_erro(self.fontes_marcadas)
        if origens is None:return
        def iniciar():
            prep=preparar(fontes,self.central.modelo_gis.camadas(),foto['crs'],
                          QgsProject.instance().transformContext(),unidades=foto.get('unidades'),
                          exigir_rede=False,inventario_completo=True)
            def conferir(cancelar,etapa):
                detalhes={}
                inv=ler(prep,cancelar,etapa,cadastro=detalhes)
                from .executar_grafo_gis import _declaracoes_existentes
                _declaracoes_existentes([f for f,_,_ in prep[0]],inv[0],inv[2])
                presentes={f['uid'] for f,_,_ in prep[0]}
                for f in fontes:
                    u=f['uid']
                    if u in presentes:
                        detalhes.setdefault(u,dict(lidas=0,descartes=[])).update(nome=f['nome'],situacao='LIDA')
                    elif abrir_modelbuilder or f['categoria']=='PIPE':
                        detalhes[u]=dict(nome=f['nome'],situacao='INDISPONIVEL')
                previa=cadastro.preparar(foto,inv,modo_atividade=regra,atividades=estado.get('atividades'),
                                         contagem=detalhes,origens=origens,cancelar=cancelar)
                previa['manifesto']['modelo_cadastral_rev']=atual.get('uuid')
                return previa
            def mostrar(previa):
                if self._projeto()['uuid']!=p['uuid'] or self.foto is not foto:return
                if abrir_modelbuilder:
                    from .modelbuilder_ui import AssistenteModelBuilder
                    self._dialogo_modelbuilder=AssistenteModelBuilder(self,previa)
                    self._dialogo_modelbuilder.show()
                    if ao_abrir:ao_abrir(self._dialogo_modelbuilder)
                elif abrir_catalogo:
                    self._abrir_catalogo_conjuntos(previa,estado,preselecao)
                else:
                    self._mostrar_previa_cadastro(previa,estado,p)
            self._tarefa_cartografica('Preparando inventário cadastral e derivados',conferir,mostrar)
        self._com_erro(iniciar)

    def abrir_historico_modelbuilder(self):
        from .modelbuilder_ui import HistoricoModelBuilder
        def mostrar():
            self._historico_modelbuilder=HistoricoModelBuilder(self)
            self._historico_modelbuilder.open()
        self._com_erro(mostrar)

    def _abrir_catalogo_conjuntos(self,previa,estado,preselecao=None,parent=None):
        dlg=CatalogoConjuntos(self,previa,estado,preselecao,parent)
        dlg.open()
        if preselecao:dlg.editar()

    def criar_conjunto_do_resultado(self,r,categoria):
        from .conjuntos_modelagem import por_segmentos
        chaves=por_segmentos(self.foto,r['segmentos'])
        self.prever_cadastro_completo(abrir_catalogo=True,preselecao=(chaves,categoria,
            dict(modo='Resultado estrutural',referencias=[r['uid']],nome=r.get('nome'))))

    def _mostrar_previa_cadastro(self,previa,estado,p):
        if self._projeto()['uuid']!=p['uuid']:return
        m=previa['manifesto']
        c=m['contagens']
        dlg=QDialog(self)
        dlg.setWindowTitle('Cadastro completo · prévia GIS')
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        v=QVBoxLayout(dlg)
        titulo='Prévia com lacunas ou pendências' if m['lacunas'] else 'Inventário cadastral conciliado'
        hip=(m.get('hipotese') or {}).get('nome','Hipótese temporária')
        v.addWidget(aviso(f"{titulo} · {hip} · {m['execucao'][:8]}\n"
                          f"{c['originais_materializados']} de {c['pipes_originais']} Pipes originais · "
                          f"{c['pipes_divididos']} divididos · {c['segmentos']} segmentos · "
                          f"{c['complementares']} propostas materializadas.\n"
                          f"{c['fora_da_hipotese']} segmentos fora da hipótese · {c['sem_origem']} sem origem · "
                          f"{c['junctions']} Junctions · {c['equipamentos']} equipamentos no inventário.\n"
                          f"{c['conexoes_aplicadas']} conexões aplicadas · {c['conexoes_pendentes']} pendentes · "
                          f"{c['sem_diametro']} segmentos sem diâmetro."))
        info=aviso()
        v.addWidget(info)
        ajustes=dict(estado.get('atividades',{}))
        def atualizar():
            a={x:sum(r['atividade']==x for r in previa['pipes']) for x in cadastro.ATIVIDADES}
            c['atividade']=a
            info.setText('Atividade pretendida · '+', '.join(f'{x.lower().replace("_"," ")} {a[x]}' for x in a))
        atualizar()
        def editar():
            termo,ok=QInputDialog.getText(dlg,'Definir atividade pretendida','ID GIS, Label ou prefixo da identidade técnica')
            if not ok or not termo.strip():return
            unicos={r['original']:r for r in previa['pipes'] if termo.casefold().strip() in (
                str(r.get('gis_id')).casefold(),str(r.get('label')).casefold()) or
                r['original'].casefold().startswith(termo.casefold().strip())}
            if not unicos:
                QMessageBox.information(dlg,'Atividade pretendida','Nenhum Pipe encontrado.')
                return
            opcoes={f"{r.get('gis_id')} · {r.get('camada') or 'Complemento'} · {u[:12]}":u
                    for u,r in unicos.items()}
            nome,ok=QInputDialog.getItem(dlg,'Identificar Pipe','Pipe físico',list(opcoes),0,False)
            if not ok:return
            atividade,ok=QInputDialog.getItem(dlg,'Atividade pretendida','Estado para preparar o modelo',
                                              list(cadastro.ATIVIDADES),0,False)
            if ok:
                u=opcoes[nome]
                ajustes[u]=atividade
                for r in previa['pipes']:
                    if r['original']==u:r['atividade']=atividade
                atualizar()
        botao(v,'Editar atividade de um Pipe…',editar)
        def guardar(formato):
            self.central._guardar_visual(p,'TOPOLOGIA_GIS',m['execucao'],estrito=True,visual={
                'exportacao_cadastro':dict(regra=m['regra_atividade'],atividades=ajustes,formato=formato)})
        botao(v,'Salvar preferências da prévia',lambda:self._com_erro(lambda:guardar(opcoes_formato.currentData())))
        def detalhes():
            textos=[f"{d['nome']} · {d['situacao']} · {d.get('lidas',0)} lidas · {len(d.get('descartes',()))} descartes"
                    for d in m['fontes'].values()]
            textos.extend(m['avisos'])
            textos.extend(f"{r.get('parte',r.get('segmento',''))[:12]} · {r['motivo']}" for r in m['pendencias'][:30])
            if len(m['pendencias'])>30:textos.append('Lista completa em validacao.json.')
            QMessageBox.information(dlg,'Conferência do cadastro','\n'.join(textos))
        botao(v,'Consultar fontes e pendências…',detalhes)
        def destacar():
            def operacao(p,_):
                from auditoria_fronteiras.modelos import verificar_cancelamento
                gs=[]
                for r in previa['pipes']:
                    verificar_cancelamento(p)
                    g=QgsGeometry()
                    g.fromWkb(r['wkb'])
                    gs.append(g)
                return QgsGeometry.collectGeometry(gs)
            self._tarefa_cartografica('Preparando destaque cadastral',operacao,
                lambda g:self.central.mapa.destacar_investigacao([('tubo',g)],self.crs_foto,True,toda_extensao=True))
        botao(v,'Destacar Pipes da prévia',destacar)
        opcoes_formato=QComboBox()
        opcoes_formato.addItem('GeoPackage','GPKG')
        opcoes_formato.addItem('Shapefile e tabelas','ESRI Shapefile')
        opcoes_formato.setCurrentIndex(max(0,opcoes_formato.findData(estado.get('formato'))))
        formulario(v).addRow('Formato',opcoes_formato)
        botao(v,'Conjuntos para WaterGEMS…',lambda:self._abrir_catalogo_conjuntos(previa,estado,parent=dlg))
        def salvar():
            pasta=QFileDialog.getExistingDirectory(dlg,'Pasta de destino')
            if not pasta:return
            formato=opcoes_formato.currentData()
            base=self._complementos(True)
            dlg.accept()
            self.tarefa('Exportando cadastro para conferência',
                        lambda p,e:cadastro.exportar(previa,Path(pasta),formato,p,e,base_labels=base),
                        lambda arq:self.status.setText('Prévia exportada em '+str(arq)))
        b=botao(v,'Exportar prévia…',salvar)
        acao_disponivel(b,'' if previa['pipes'] else 'Nenhum Pipe materializado. Consulte as pendências.')
        botao(v,'Fechar',dlg.reject)
        self._dialogo_cadastro=dlg
        dlg.open()
