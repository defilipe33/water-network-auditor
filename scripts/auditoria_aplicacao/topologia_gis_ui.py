"""Fluxo QGIS para construir, revisar e recuperar topologias GIS."""

import json
from pathlib import Path
from uuid import uuid4

from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsProject
from qgis.gui import QgsProjectionSelectionWidget

from . import persistencia_grafo_gis as pg
from .complementos_gis_ui import EditarComplemento
from . import hipoteses_gis as hg
from .entradas_grafo_gis import ORIGENS, ler, preparar
from .executar_grafo_gis import executar, _declaracoes_existentes
from .grafo_gis import ROTULOS
from .investigacao_gis import geometria
from .modelo_gis import revisoes, identificar, descrever
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .mapa_topologia_gis import MapaTopologiaGIS, pontos_portas
from .tabelas_topologia_gis import TabelaRelacoes, TabelaGIS, ACOMPANHAMENTO, ESTADO_COMPONENTE
from .topologia_gis_hipoteses_ui import HipotesesGIS
from .topologia_gis_mapa_ui import MapaGIS


def _itens(lista):
    return [lista.item(i) for i in range(lista.count())]


def _marcados(lista):
    return [i.data(Qt.UserRole) for i in _itens(lista) if i.checkState()==Qt.Checked]


def _inserir(lista, titulo, uid, marcado=None):
    item=QListWidgetItem(titulo)
    item.setData(Qt.UserRole,uid)
    if marcado is not None:item.setCheckState(Qt.Checked if marcado else Qt.Unchecked)
    lista.addItem(item)
    return item


class TopologiaGIS(QScrollArea,HipotesesGIS,MapaGIS):
    def __init__(self, central):
        super().__init__(central)
        self.central=central
        self.app=central.app
        self.uid_projeto=None
        self.dados=None
        self.registros={}
        self._historicas=[]
        self._por_revisao={}
        self._hip_ativa=None
        self._pinos={}
        self._edicao_limpa=None
        self._resultado_historico=False
        self._editor=None
        self._finalizar_ferramenta=None
        self._ordem_coluna=None
        self._filtro_relacao=None
        self.mapa_gis=MapaTopologiaGIS()
        self._timer_mapa=QTimer(self)
        self._timer_mapa.setSingleShot(True)
        self._timer_mapa.timeout.connect(self._atualizar_mapa)
        self._ferramenta=None
        self._lista_resultados=[]
        self._pagina=0
        self.setWidgetResizable(True)
        w=QWidget()
        self.setWidget(w)
        v=QVBoxLayout(w)
        botao(v,'‹ Investigar minha rede',self.voltar)
        self.status=aviso('Topologia GIS · conectividade estrutural')
        v.addWidget(self.status)
        self.config_b, cfg=expansivel(v,'Configuração da análise')
        self.config_b.setChecked(True)
        self.nome=QLineEdit('Conectividade GIS')
        f=formulario(cfg)
        f.addRow('Nome do trabalho',self.nome)
        self.crs=QgsProjectionSelectionWidget()
        f.addRow('CRS projetado em metros',self.crs)
        self.tolerancia=QDoubleSpinBox()
        self.tolerancia.setRange(0,100)
        self.tolerancia.setDecimals(3)
        self.tolerancia.setValue(.20)
        self.tolerancia.setSuffix(' m')
        f.addRow('Tolerância de conexão',self.tolerancia)
        self.aproximadas=QCheckBox('Inferir união de pontas próximas quando inequívoca')
        cfg.addWidget(self.aproximadas)
        self.limite=QDoubleSpinBox()
        self.limite.setRange(1,100000)
        self.limite.setValue(200)
        self.limite.setSuffix(' mm')
        f.addRow('Diâmetro mínimo para destacar redes principais (mm)',self.limite)
        self.limite.setToolTip('Critério de diagnóstico e prioridade. A topologia usa todos os trechos do escopo. A classificação de adução é um critério cadastral separado.')
        self.estrategia=aviso()
        cfg.addWidget(self.estrategia)
        cfg.addWidget(aviso('Redes consideradas. Marque as fontes conforme as classificações do Modelo GIS.'))
        self.redes=QListWidget()
        self.redes.setMaximumHeight(120)
        cfg.addWidget(self.redes)
        self.redes.itemChanged.connect(self._configuracao_alterada)
        self.crs.crsChanged.connect(self._configuracao_alterada)
        self.tolerancia.valueChanged.connect(self._configuracao_alterada)
        self.limite.valueChanged.connect(self._configuracao_alterada)
        self.aproximadas.toggled.connect(self._configuracao_alterada)
        self.unidades={}
        self.unidade=QComboBox()
        for k,n in [(None,'Não confirmada'),('mm','mm'),('cm','cm'),('m','m'),('pol','polegadas')]:
            self.unidade.addItem(n,k)
        f2=formulario(cfg)
        f2.addRow('Unidade do diâmetro da fonte selecionada',self.unidade)
        self.unidade.activated.connect(self.salvar_unidade)
        self.redes.currentItemChanged.connect(self.mostrar_unidade)
        self.tipo_escopo=QComboBox()
        for n,k in [('Todos os tipos',''),('Adução','ADUCAO'),('Distribuição','DISTRIBUICAO'),
                    ('Complementar','COMPLEMENTAR'),('Outra','OUTRA')]:
            self.tipo_escopo.addItem(n,k)
        self.tipo_escopo.activated.connect(self.selecionar_tipo)
        f2.addRow('Marcar redes por tipo',self.tipo_escopo)
        self.orig_b, orig=expansivel(v,'Definir fontes de água e conexões')
        orig.addWidget(aviso('Marque os elementos que participarão desta execução. Origens marcadas indicam acesso topológico na hipótese selecionada.'))
        self.participantes=TabelaRelacoes()
        self.participantes.setMaximumHeight(145)
        self.participantes.itemChanged.connect(self.alterou_participacao)
        self.participantes.currentCellChanged.connect(lambda *_:self.detalhar_relacao())
        orig.addWidget(self.participantes)
        self.relacao_info=aviso()
        orig.addWidget(self.relacao_info)
        botao(orig,'Adicionar origem cadastrada…',lambda:self.editar('ORIGEM'))
        botao(orig,'Adicionar origem no mapa',lambda:self.capturar())
        botao(orig,'Adicionar conexão entre tubulações…',lambda:self.editar('CONEXAO'))
        botao(orig,'Editar elemento selecionado…',self.editar_selecionado)
        botao(orig,'Reposicionar origem complementar selecionada',self.reposicionar)
        _, mais_rel=expansivel(orig,'Opções do elemento')
        botao(mais_rel,'Ativar ou desativar no cadastro…',self.alternar_elemento)
        botao(mais_rel,'Usar revisão mais recente nesta hipótese',self.adotar_revisao_atual)
        botao(mais_rel,'Destacar tubulações da relação',lambda:self.destacar_relacao())
        botao(mais_rel,'Aproximar origem ou conexão',lambda:self.destacar_relacao(aproximar=True))
        botao(orig,'Histórico do elemento selecionado',self.historico_elemento)
        self.relocalizar_b=botao(orig,'Localizar GeoPackage de complementos…',self.relocalizar_complementos)
        self.relocalizar_b.hide()
        self.hipoteses=QComboBox()
        _, hip=expansivel(v,'Hipóteses e reexecução')
        formulario(hip).addRow('Hipótese e revisão',self.hipoteses)
        self.hipoteses.activated.connect(self.aplicar_hipotese)
        botao(hip,'Salvar revisão da hipótese…',lambda:self.salvar_hipotese())
        botao(hip,'Salvar como nova hipótese…',lambda:self.salvar_hipotese(nova=True))
        botao(hip,'Reexecutar análise com estas alterações…',self.reexecutar)
        botao(hip,'Comparar duas execuções…',self.comparar)
        botao(v,'Executar análise de conectividade',lambda:self.iniciar()).setObjectName('Principal')
        self.resumo=aviso()
        v.addWidget(self.resumo)
        self.categoria=QComboBox()
        self.categoria.currentIndexChanged.connect(self.mudar_resultados)
        self.ordem=QComboBox()
        self.ordem.setToolTip('Prioridade: primeiro os sem origem alcançável, depois comprimento, diâmetro, candidatas e quantidade de trechos.')
        for chave in ('Prioridade', 'Comprimento', 'Diâmetro', 'Categoria'):
            self.ordem.addItem(chave)
        self.ordem.activated.connect(self.mudar_resultados)
        f3=formulario(v)
        f3.addRow('Categoria',self.categoria)
        f3.addRow('Ordenar',self.ordem)
        self.busca=QLineEdit()
        self.busca.setPlaceholderText('Filtrar por ID, situação, setor ou zona')
        self.busca.editingFinished.connect(self.mudar_resultados)
        v.addWidget(self.busca)
        self.resultados=TabelaGIS()
        self.resultados.setMaximumHeight(210)
        self.resultados.currentCellChanged.connect(self.detalhar)
        self.resultados.horizontalHeader().sectionClicked.connect(self.ordenar_resultados)
        v.addWidget(self.resultados)
        botao(v,'Página anterior',lambda:self.paginar(-1))
        botao(v,'Próxima página',lambda:self.paginar(1))
        self.detalhes=aviso()
        v.addWidget(self.detalhes)
        _, mapa=expansivel(v,'Mapa e legenda')
        mapa.addWidget(aviso('Use a árvore de camadas para ajustar a visibilidade. Fontes são triângulos, pentágonos ou losangos. Círculo verde indica conexão confirmada. Contornos tracejados representam hipóteses ou propostas. As linhas auxiliares representam vínculos topológicos.'))
        botao(mapa,'Consultar símbolo no mapa',lambda:self.consultar_mapa())
        botao(mapa,'Revisar conexão no mapa',lambda:self.consultar_mapa(revisar=True))
        botao(mapa,'Destacar seleção',self.destacar)
        botao(mapa,'Aproximar seleção',lambda:self.destacar(aproximar=True))
        _, decisoes=expansivel(v,'Decisões e acompanhamento')
        self.acompanhamento=QComboBox()
        for k,n in ACOMPANHAMENTO.items():self.acompanhamento.addItem(n,k)
        formulario(decisoes).addRow('Situação',self.acompanhamento)
        botao(decisoes,'Salvar situação e observação…',self.anotar)
        botao(decisoes,'Revisar conexão selecionada…',self.revisar_conexao)
        _, historico=expansivel(v,'Histórico')
        botao(historico,'Histórico do resultado selecionado',self.historico_resultado)
        _, av=expansivel(v,'Exportações')
        botao(av,'Exportar GeoPackage e tabelas…',lambda:self.exportar('GPKG'))
        botao(av,'Exportar Shapefile e tabelas…',lambda:self.exportar('ESRI Shapefile'))
        self.historico=QPlainTextEdit()
        self.historico.setReadOnly(True)
        self.historico.setMaximumHeight(160)
        self.historico.hide()
        historico.addWidget(self.historico)
        self.comparacao=TabelaGIS()
        self.comparacao.colunas(('Diferença','Antes','Depois','Trechos'))
        self.comparacao.setMaximumHeight(150)
        self.comparacao.currentCellChanged.connect(self.destacar_diferenca)
        hip.addWidget(self.comparacao)
        self.comparacao.hide()

    def _projeto(self):
        return self.central.projetos.atual()

    def _revisao(self):
        return next(reversed(revisoes(self._projeto())),{})

    def _revisao_operacional(self,hip=None):
        hip=hip or self._hip_ativa
        if not hip or hip.get('formato')!=hg.FORMATO:return self._revisao()
        uid=hip['configuracao']['modelo_rev']
        modelo=next((r for r in revisoes(self._projeto()) if r['uuid']==uid),None)
        if modelo is None:
            raise ValueError('A revisão do Modelo GIS fixada nesta hipótese está indisponível.')
        return modelo

    def _listar_redes(self,revisao):
        fontes=[f for f in revisao.get('fontes',[]) if f['categoria']=='PIPE']
        self.estrategia.setText('Estratégia de Junctions do Modelo GIS: '+revisao.get('estrategia','COMBINAR').lower()+'.')
        self.por_fonte={f['uid']:f for f in fontes}
        anteriores={i.data(Qt.UserRole):i.checkState()==Qt.Checked for i in _itens(self.redes)}
        bloqueado=self.redes.blockSignals(True)
        try:
            self.redes.clear()
            for f in fontes:
                _inserir(self.redes,f["nome"]+' · '+(f['classificacao'] or 'Sem classificação'),f['uid'],
                         anteriores.get(f['uid'],True))
        finally:self.redes.blockSignals(bloqueado)
        if fontes:self.redes.setCurrentRow(0)

    def _pasta(self):
        p=self._projeto()
        return (Path(p['manifesto_wna']).parent if p.get('manifesto_wna')
                else self.app.catalogo.raiz/'topologia_gis'/p['uuid'])

    def _base_complementos(self, criar=False):
        p=self._projeto()
        if p.get('arquivo_complementos'):
            return Path(p['arquivo_complementos'])
        if not criar:
            return None
        pasta=self._pasta()
        pasta.mkdir(parents=True,exist_ok=True)
        arq=pasta/('complementos_'+p['uuid'][:12]+'.gpkg')
        if not arq.exists():
            pg.criar_complementos(arq,p['uuid'])
        pg.revisoes(arq,p['uuid'])
        p['arquivo_complementos']=str(arq.resolve())
        self.central.projetos.salvar()
        return arq

    def abrir(self, origens=False):
        p=self._projeto()
        if p['uuid']!=self.uid_projeto:
            self.uid_projeto=p['uuid']
            self.dados=None
            self._hip_ativa=None
            self._pinos={}
            self._edicao_limpa=None
            self._resultado_historico=False
            self.comparacao.limpar()
            self.comparacao.hide()
            self.unidades={}
            self.redes.clear()
            self.participantes.clear()
            self.hipoteses.clear()
            self.crs.setCrs(QgsProject.instance().crs())
            self.resumo.clear()
            self.status.setText('Topologia GIS · conectividade estrutural')
            self.config_b.setChecked(True)
            self.historico.hide()
            self.listar_categorias()
        r=self._com_erro(self._revisao_operacional) or self._revisao()
        self._listar_redes(r)
        fontes=self.por_fonte.values()
        if self._edicao_limpa is None:
            from auditoria_fronteiras import Parametros
            from auditoria_fronteiras.entradas import crs_processamento
            for crs in (self.crs.crs(), *(QgsCoordinateReferenceSystem(f['crs_wkt']) for f in fontes)):
                try:
                    self.crs.setCrs(crs_processamento(Parametros(crs=crs.toWkt())))
                    break
                except ValueError:
                    continue
        self.atualizar_complementos()
        if self._edicao_limpa is None:self._edicao_limpa=self._assinatura_edicao()
        self.orig_b.setChecked(origens or self.orig_b.isChecked())
        self.mostrar_contexto()

    def voltar(self):
        if not self.resolver_edicao():return
        self.cancelar_captura()
        self.central.mudar_area()

    def selecionar_tipo(self):
        escolha=self.tipo_escopo.currentData()
        for i in _itens(self.redes):
            f=self.por_fonte[i.data(Qt.UserRole)]
            i.setCheckState(Qt.Checked if not escolha or f['classificacao']==escolha else Qt.Unchecked)

    def mostrar_unidade(self,item,*_):
        chave=item.data(Qt.UserRole) if item else None
        fonte=self.por_fonte.get(chave,{})
        self.unidade.setEnabled(bool(fonte.get('campos_mapeados',{}).get('diametro')))
        self.unidade.setCurrentIndex(max(0,self.unidade.findData(self.unidades.get(chave))))

    def salvar_unidade(self):
        item=self.redes.currentItem()
        if item:self.unidades[item.data(Qt.UserRole)]=self.unidade.currentData()
        self._resultado_historico=False
        self.agendar_mapa()

    def _selecionados(self):
        return _marcados(self.participantes)

    def _redes_marcadas(self):
        return _marcados(self.redes)

    def atualizar_complementos(self,escolhidos=None):
        marcados=set(self._selecionados() if escolhidos is None else escolhidos)
        preferida=self._hip_ativa['rev'] if self._hip_ativa else None
        anterior=self._registro_selecionado()
        self.participantes.blockSignals(True)
        self.participantes.clear()
        self.hipoteses.clear()
        self.hipoteses.addItem('Hipótese temporária',None)
        self.relocalizar_b.hide()
        try:
            self._historicas=pg.revisoes(self._base_complementos(),self.uid_projeto)
        except (OSError,ValueError,__import__('sqlite3').Error) as e:
            self._historicas=[]
            self.relocalizar_b.show()
            self.status.setText('Cadastro de complementos indisponível. '+str(e))
        self._por_revisao={r['rev']:r for r in self._historicas}
        self.registros={r['uuid']:r for r in self._historicas}
        participacoes={}
        for r in reversed(self._historicas):
            if r['tipo']!='HIPOTESE':continue
            rotulo=' · revisão '+r['rev'][:8] if r.get('formato')==hg.FORMATO else ' · 1.16.0'
            self.hipoteses.addItem(r['nome']+rotulo,r['rev'])
            for uid,rev in r.get('vinculos',{}).items():
                participacoes.setdefault((uid,rev),set()).add(r['nome'])
        self._participacoes=participacoes
        for r in {**self.registros,**self._pinos}.values():
            if r['tipo'] not in ('ORIGEM','CONEXAO'):continue
            ativo=r.get('habilitado',True)
            titulo=r.get('nome') or r.get('categoria') or 'Conexão '+r['uuid'][:8]
            if not ativo:titulo+=' · desativado'
            interpretacao=pg.DECISOES.get(r.get('decisao'),'—')
            nomes=', '.join(sorted(participacoes.get((r['uuid'],r['rev']),())))
            item=self.participantes.inserir((titulo,pg.SITUACOES[r['situacao']],interpretacao,nomes),r['uuid'])
            item.setCheckState(Qt.Checked if ativo and r['uuid'] in marcados else Qt.Unchecked)
            if not ativo:item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            if anterior and anterior['uuid']==r['uuid']:self.participantes.setCurrentCell(item.row(),0)
        self.participantes.blockSignals(False)
        self.hipoteses.setCurrentIndex(max(0,self.hipoteses.findData(preferida)))
        self.detalhar_relacao()
        self.agendar_mapa()

    def alterou_participacao(self,item):
        if item.column()!=0:return
        self._resultado_historico=False
        self.detalhar_relacao()
        self.agendar_mapa()

    def detalhar_relacao(self,r=None):
        r=r or self._registro_selecionado()
        if not r:
            self.relacao_info.clear()
            return
        ids=getattr(self,'tubos',{})
        vinculos=', '.join(str(ids.get(uid,{}).get('id') or uid[:8])+f' ({pos*100:g}%)' for uid,pos in r['portas'])
        nomes=', '.join(sorted(self._participacoes.get((r['uuid'],r['rev']),()))) or 'Nenhuma revisão salva'
        estado='Incluída' if r['uuid'] in self._selecionados() else 'Fora da hipótese em edição'
        self.relacao_info.setText(f"{r.get('nome') or r.get('categoria') or 'Conexão'} · {estado} · revisão {r['rev'][:8]}"
                                 f"\nTubulações: {vinculos}\nHipóteses: {nomes}")

    def relocalizar_complementos(self):
        if self.central.ocupado():return
        path,_=QFileDialog.getOpenFileName(self,'Localizar complementos GIS','','GeoPackage (*.gpkg)')
        if not path:return
        def localizar():
            pg.revisoes(path,self.uid_projeto)
            self._projeto()['arquivo_complementos']=str(Path(path).resolve())
            self.central.projetos.salvar()
            self.atualizar_complementos()
            self.mostrar_contexto()
        self._com_erro(localizar)



    def _salvar(self,tipo,dados,anterior=None):
        anterior=anterior or {}
        r=pg.salvar_revisao(self._base_complementos(True),self.uid_projeto,tipo,dados,
                            anterior.get('uuid'),anterior.get('rev'))
        self.atualizar_complementos()
        self.mostrar_contexto()
        return r



    def _com_erro(self,fn):
        import sqlite3
        try:return fn()
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as e:self.status.setText(str(e))

    def _preparacao(self):
        return preparar(self._revisao_operacional().get('fontes',[]),list(self.central.modelo_gis.camadas()),
                        self.crs.crs().toWkt(),QgsProject.instance().transformContext(),
                        set(_marcados(self.redes)),self.unidades)

    def _inventario_para_editar(self,pronto):
        prep=self._com_erro(self._preparacao)
        if prep is None:return
        def trabalho(parar,etapa):
            tubos,_,eq,_,_=ler(prep,parar,etapa)
            _declaracoes_existentes([f for f,_,_ in prep[0]],tubos,eq)
            return tubos,[e for e in eq if e['categoria'] in ORIGENS],prep[1].toWkt()
        # A seleção/cartografia permanece no thread principal.
        self.app.atividades.executar_thread('Carregar elementos GIS',self._projeto()['nome'],trabalho,pronto,self.status.setText)

    def editar(self,tipo,anterior=None,ponto=None,candidato=None):
        if self.central.ocupado():return
        if self._editor is not None:
            self._editor.show()
            self._editor.raise_()
            return
        def dialogo(tubos,eq,crs):
            atual=self.registros.get(anterior['uuid']) if anterior else None
            local=ponto
            if local is None and anterior and anterior.get('xy'):
                local={k:anterior[k] for k in ('xy','crs')}
            dlg=EditarComplemento(self,tipo,tubos,eq,local,anterior,candidato)
            self._editor=dlg
            crs_editor=QgsCoordinateReferenceSystem(crs)
            dlg.escolher_tubos.connect(lambda:self.selecionar_no_editor(dlg,crs))
            dlg.escolher_origem.connect(lambda:self.selecionar_no_editor(dlg,crs,origem=True))
            dlg.portas_alteradas.connect(lambda:self._destacar_tubos_editor(dlg,crs_editor))
            def salvar(dados):
                if tipo=='ORIGEM' and dados.get('equipamento'):dados['crs']=crs
                if tipo=='CONEXAO':
                    dados['crs']=crs
                    if candidato and candidato.get('wkb'):dados['wkb']=candidato['wkb']
                dados['pontos_rede']=pontos_portas(dados['portas'],dlg.tubos)
                dados['crs_rede']=crs
                novo=self._salvar(tipo,dados,atual)
                escolhidos=set(self._selecionados())
                if novo['uuid'] in escolhidos:self._pinos[novo['uuid']]=novo
                self._resultado_historico=False
                self.atualizar_complementos(escolhidos=escolhidos)
                self.status.setText('Revisão salva. Marque a relação para reexecutar. Hipóteses anteriores preservam suas revisões.')
            def terminou(_):
                self._editor=None
                self.cancelar_captura(reabrir=False)
                self.central.mapa.limpar()
                dlg.deleteLater()
            dlg.antes_salvar=salvar
            dlg.finished.connect(terminou)
            dlg.show()
        if candidato and self.dados:
            dialogo(self.dados['tubos'],[],self.dados['crs'])
        else:
            self._inventario_para_editar(lambda inventario:dialogo(*inventario))

    def _registro_selecionado(self):
        i=self.participantes.currentItem()
        if not i:return None
        uid=i.data(Qt.UserRole)
        return self._pinos.get(uid,self.registros.get(uid))

    def _candidato_da_relacao(self,r):
        if not r.get('candidato'):return None
        return dict(uid=r['candidato'],portas=r['portas'],tipo=r.get('categoria_candidata'),wkb=r.get('wkb'))

    def editar_selecionado(self):
        r=self._registro_selecionado()
        if r:self.editar(r['tipo'],r,candidato=self._candidato_da_relacao(r))

    def alternar_elemento(self):
        r=self._registro_selecionado()
        if r and not self.central.ocupado():
            atual=self.registros.get(r['uuid'])
            if atual and atual['rev']!=r['rev']:
                self.status.setText('A hipótese fixou uma revisão anterior. Adote a revisão atual antes de editar o cadastro.')
                return
            novo=self._com_erro(lambda:self._salvar(r['tipo'],dict(r,habilitado=not r.get('habilitado',True)),r))
            if novo:
                self._pinos.pop(r['uuid'],None)
                self._resultado_historico=False
                self.atualizar_complementos()

    def reposicionar(self):
        r=self._registro_selecionado()
        if r and r['tipo']=='ORIGEM' and not r.get('equipamento'):
            self.capturar(r)



    def iniciar(self,modo=None):
        if self.central.ocupado() or self._editor is not None or not self.central.modelo_gis.resolver():return
        self.cancelar_captura()
        def iniciar():
            prep=self._preparacao()
            p=self._projeto()
            projeto_uid=p['uuid']
            rev=self._revisao_operacional()
            participantes=self._participantes_exatos()
            grupos=[r['candidato'] for r in participantes if r.get('candidato')]
            if len(grupos)!=len(set(grupos)):
                raise ValueError('Selecione apenas uma interpretação por conexão candidata.')
            parametros=self._parametros()
            config=hg.configuracao(prep,rev.get('uuid'),parametros)
            hip=self._hip_ativa if modo!='temporaria' else None
            if hip:self._validar_configuracao_fixada(hip,config,participantes)
            contexto=dict(projeto_uid=projeto_uid,projeto=p['nome'],modelo_rev=rev.get('uuid'),
                          nome=self.nome.text().strip() or 'Conectividade GIS',
                          hipotese=hip,configuracao=config)
            pasta=self._pasta()/'resultados'
            pasta.mkdir(parents=True,exist_ok=True)
            destino=pasta/('topologia_gis_'+uuid4().hex[:16]+'.gpkg')
            self.status.setText('Análise de conectividade em andamento. Acompanhe em Janelas.')
            def trabalho(parar,etapa):
                inventario=ler(prep,parar,etapa)
                assinatura=hg.assinatura_inventario(inventario)
                if hip and assinatura!=hip['assinatura_inventario']:
                    raise ValueError('O conteúdo das fontes mudou desde a revisão salva. Restaure as fontes ou crie nova revisão.')
                d=executar(prep,contexto,parametros,participantes,parar,etapa,inventario=inventario)
                d['assinatura_inventario']=assinatura
                etapa(0,'Gravando execução verificada')
                pg.salvar_execucao(destino,d,parar)
                return d
            def pronto(d):
                if self._projeto()['uuid']!=projeto_uid:
                    raise ValueError('O projeto mudou. O resultado pode ser recuperado pelo arquivo gravado.')
                r=self.app.catalogo.registrar(destino)[0]
                self.central.projetos.vincular(r)
                self.central._catalogo_lido=None
                self.receber(d)
            self.app.atividades.executar_thread('Analisar conectividade',p['nome'],trabalho,pronto,self.status.setText)
        self._com_erro(iniciar)

    def reabrir(self,r):
        uid=self.uid_projeto
        self.app.atividades.executar_thread('Reabrir topologia GIS',r.get('nome','Conectividade GIS'),
            lambda parar,etapa:pg.carregar(r['base'],r['uuid'],uid),
            lambda d:self.receber(d,restaurar_configuracao=True),self.status.setText)

    def receber(self,d,restaurar_configuracao=False):
        if d['projeto_uid']!=self.uid_projeto or d['projeto_uid']!=self._projeto()['uuid']:
            raise ValueError('O projeto ativo mudou durante a abertura.')
        self.dados=d
        self._resultado_historico=True
        self.tubos={t['uid']:t for t in d['tubos']}
        self.nos={n['uid']:n for n in d['nos']}
        self.componentes={g['uid']:g for g in d['componentes']}
        self.componentes_tubo={t:g for g in d['componentes'] for t in g['tubos']}
        self.comps_origens={r['uuid']:r for r in d['participantes'] if r['tipo']=='ORIGEM'}
        if restaurar_configuracao:
            hip=d.get('hipotese')
            self._hip_ativa=hip if hip and hip.get('formato')==hg.FORMATO else None
            if self._hip_ativa:
                modelo=next((r for r in revisoes(self._projeto()) if r['uuid']==hip['configuracao']['modelo_rev']),None)
                if modelo is not None:self._listar_redes(modelo)
            self._pinos={r['uuid']:r for r in d['participantes']}
            self.nome.setText(d['nome'])
            self.crs.setCrs(QgsCoordinateReferenceSystem(d['crs']))
            self.tolerancia.setValue(d['parametros']['tolerancia'])
            self.limite.setValue(d['parametros']['limite_mm'])
            self.aproximadas.setChecked(d['parametros']['inferir_proximas'])
            self.unidades=dict(d['unidades'])
            redes={f['uid'] for f in d['fontes'] if f['categoria']=='PIPE'}
            for i in _itens(self.redes):
                i.setCheckState(Qt.Checked if i.data(Qt.UserRole) in redes else Qt.Unchecked)
            self.atualizar_complementos(escolhidos=self._pinos)
            self.mostrar_unidade(self.redes.currentItem())
            self._edicao_limpa=self._assinatura_edicao()
        self._resultado_historico=True
        self.status.setText(d['nome'])
        self.config_b.setChecked(False)
        self.listar_categorias()
        self.mostrar_contexto()
        self.agendar_mapa()

    def mostrar_contexto(self):
        if not self.dados:return
        d=self.dados
        antigos={f['uid']:f for f in d['fontes']}
        atual={f['uid']:f for f in self._revisao().get('fontes',[])}
        alterou=d['modelo_rev']!=self._revisao().get('uuid')
        camadas=list(self.central.modelo_gis.camadas())
        for uid,f in antigos.items():
            presente=atual.get(uid)
            c=identificar(presente,camadas) if presente else None
            try:
                if c is None or descrever(c)['assinatura']!=f['assinatura']:alterou=True
            except ValueError:
                alterou=True
        alterou |= any(self.registros.get(r['uuid'],{}).get('rev')!=r['rev'] for r in d['participantes'])
        g=d['componentes']
        c=[v for v in g if v['situacao']=='SEM_ORIGEM_ALCANCAVEL']
        s=f"{len(g)} componente(s) · {len(d['tubos'])} parte(s) de tubulação · {len(d['ramos'])} ramificação(ões)"
        s+=f"\nOrigens com portas válidas: {len(d['origens_validas'])}/{len(self.comps_origens)}."
        s+=(f" Sem ligação a essas origens: {len(c)} componente(s) · {sum(v['comprimento_m'] for v in c):.2f} m."
            if d['origens_validas'] else ' Acesso a origens ainda indeterminado.')
        if alterou:s+='\nAs fontes ou relações mudaram ou estão indisponíveis. A execução preserva a configuração anterior.'
        if d['avisos']:s+='\n'+'\n'.join(d['avisos'])
        if d.get('hipotese'):
            s+='\nHipótese: '+d['hipotese']['nome']
        self.resumo.setText(s)

    def listar_categorias(self):
        from collections import Counter
        self.categoria.blockSignals(True)
        self.categoria.clear()
        if self.dados:
            cont=Counter(r['tipo'] for r in self.dados['diagnosticos'])
            self.categoria.addItem(f"Todos os componentes ({len(self.dados['componentes'])})",'COMPONENTES')
            for k,n in ROTULOS.items():
                self.categoria.addItem(f'{n} ({cont[k]})',k)
        self.categoria.blockSignals(False)
        self.mudar_resultados()

    def _rotulo_tubo(self,uid):
        t=self.tubos.get(uid,{})
        return f"{t.get('id') or uid[:8]} · {t.get('camada','Fonte anterior')}"

    def _acompanhamento(self,r):
        return ACOMPANHAMENTO.get(self._decisoes_resultado.get(r['uid'],{}).get('acompanhamento'),'Pendente')

    def _colunas_resultados(self):
        categoria=self.categoria.currentData()
        if categoria in ('COMPONENTES','COMPONENTE_INDEPENDENTE','SEM_ORIGEM'):
            return ('ID','Situação topológica','Tubulações','Comprimento (m)','Maior Ø (mm)','Acima do limite (m)',
                    'Origens alcançáveis','Candidatas','Acompanhamento')
        if categoria=='REDE_PRINCIPAL':
            return ('Componente','Trechos','Extensão relevante (m)','Maior Ø (mm)','Origens','Critério','Prioridade','Acompanhamento')
        return ('ID','Tubulação que termina' if categoria=='CONEXAO_T' else 'Tubulação A',
                'Tubulação receptora' if categoria=='CONEXAO_T' else 'Tubulação B',
                'Distância (m)','Componentes','Interpretação','Acompanhamento')

    def _valores(self,r):
        categoria=self.categoria.currentData()
        g=self.componentes.get(r.get('componente',r['uid']),{})
        origens=', '.join((self.comps_origens[o].get('nome') or o[:8]) for o in g.get('origens',[]))
        situacao=self._acompanhamento(r)
        if categoria in ('COMPONENTES','COMPONENTE_INDEPENDENTE','SEM_ORIGEM'):
            return (g['uid'][:8],ESTADO_COMPONENTE[g['situacao']],g['quantidade_tubos'],g['comprimento_m'],
                    g.get('max_mm'),g['faixas_m']['A partir do limite'],origens,len(g['candidatas']),situacao)
        if categoria=='REDE_PRINCIPAL':
            prioridade=getattr(self,'_prioridade',{}).get(r['uid'])
            return (r['componente'][:8],len(r['tubos']),r['comprimento_m'],r.get('max_mm'),origens,r['criterio'],prioridade,situacao)
        ts=r['tubos']
        ponta=r.get('tubulacao_termina')
        receptora=r.get('tubulacao_receptora')
        if categoria=='CONEXAO_T' and not ponta:
            ponta=next((u for u,f in r.get('portas',[]) if f in (0,1)),None)
            receptora=next((u for u,f in r.get('portas',[]) if 0<f<1),None)
        a=ponta or (ts[0] if ts else None)
        b=receptora or (ts[1] if len(ts)>1 else None)
        componentes=r.get('componentes') or sorted({self.componentes_tubo[u]['uid'] for u in ts if u in self.componentes_tubo})
        return (r['uid'][:8],self._rotulo_tubo(a) if a else None,self._rotulo_tubo(b) if b else None,
                r.get('distancia_m'),', '.join(u[:8] for u in componentes),
                pg.DECISOES.get(r['situacao'],r['situacao'].replace('_',' ').capitalize()),situacao)

    def ordenar_resultados(self,coluna):
        atual=self._ordem_coluna
        descendente=not atual[1] if atual and atual[0]==coluna else False
        self._ordem_coluna=(coluna,descendente)
        self.resultados.horizontalHeader().setSortIndicator(coluna,Qt.DescendingOrder if descendente else Qt.AscendingOrder)
        self.resultados.horizontalHeader().setSortIndicatorShown(True)
        self.mudar_resultados()

    def mudar_resultados(self,*_):
        self._pagina=0
        categoria=self.categoria.currentData()
        if categoria!=getattr(self,'_ultima_categoria',None):
            self._ultima_categoria=categoria
            self._ordem_coluna=None
            self.resultados.horizontalHeader().setSortIndicatorShown(False)
        d=self.dados
        if d and categoria:
            self._decisoes_resultado={r['alvo']:r for r in self.registros.values()
                                     if r['tipo']=='DECISAO' and r.get('execucao')==d['uuid']}
            candidatos=(d['componentes'] if categoria=='COMPONENTES' else
                        [c for c in d['diagnosticos'] if c['tipo']==categoria])
            chaves={
                'Prioridade':lambda r:(bool(r.get('origens')), -r.get('comprimento_m',0), -(r.get('max_mm') or 0),
                                       -len(r.get('candidatas',[])),-len(r['tubos']),r['uid']),
                'Comprimento':lambda r:(-r.get('comprimento_m',0),r['uid']),
                'Diâmetro':lambda r:(-(r.get('max_mm') or 0),r['uid']),
                'Categoria':lambda r:(r.get('tipo',r['situacao']),r['uid']),
            }
            if categoria=='REDE_PRINCIPAL':
                self._prioridade={r['uid']:i+1 for i,r in enumerate(sorted(candidatos,key=chaves['Prioridade']))}
            termo=self.busca.text().strip().casefold()
            if termo:
                candidatos=[r for r in candidatos if termo in ' '.join((r['uid'],self._acompanhamento(r),
                    *(str(x) for x in self._valores(r) if x is not None),
                    *(z for t in r['tubos'] for z in self.tubos[t].get('zonas',[])))).casefold()]
            self._lista_resultados=sorted(candidatos,key=chaves[self.ordem.currentText()])
            if self._ordem_coluna:
                coluna,desc=self._ordem_coluna
                def chave(r):
                    v=self._valores(r)[coluna]
                    return (v is None, str(v).casefold() if isinstance(v,str) or v is None else v)
                self._lista_resultados.sort(key=chave,reverse=desc)
        else:self._lista_resultados=[]
        self.resultados.colunas(self._colunas_resultados())
        self.paginar(0)

    def paginar(self,delta):
        n=len(self._lista_resultados)
        self._pagina=max(0,min(self._pagina+delta,(n-1)//200))
        bloqueado=self.resultados.blockSignals(True)
        self.resultados.limpar()
        for r in self._lista_resultados[200*self._pagina:200*(self._pagina+1)]:
            self.resultados.inserir(self._valores(r),r['uid'])
        self.resultados.blockSignals(bloqueado)
        if n:self.resultados.setCurrentCell(0,0)
        else:self.detalhes.setText('Nenhum resultado nesta categoria e filtro.')

    def selecionar_resultado_uid(self,uid,categoria):
        indice=self.categoria.findData(categoria)
        if indice<0:return False
        self.busca.clear()
        self.categoria.setCurrentIndex(indice)
        self.mudar_resultados()
        pos=next((i for i,r in enumerate(self._lista_resultados) if r['uid']==uid),None)
        if pos is None:return False
        self._pagina=pos//200
        self.paginar(0)
        self.resultados.setCurrentCell(pos%200,0)
        self.ensureWidgetVisible(self.resultados)
        return True

    def _selecionado(self):
        i=self.resultados.currentRow()
        pos=200*self._pagina+i
        return self._lista_resultados[pos] if i>=0 and pos<len(self._lista_resultados) else None

    def detalhar(self,*_):
        r=self._selecionado()
        if r is None:return
        g=self.componentes.get(r.get('componente',r['uid']))
        partes=[]
        if g:
            origens=', '.join(self.comps_origens[o].get('nome') or self.comps_origens[o]['categoria'] for o in g['origens'])
            partes.append(f"{g['quantidade_tubos']} tubulações · {len(g['nos'])} nós · {len(g['candidatas'])} conexões candidatas")
            partes.append('Maior diâmetro: '+(f"{g['max_mm']:g} mm" if g['max_mm'] else 'indisponível'))
            partes.append('Comprimento por faixa: '+ ' · '.join(f'{k}: {v:.2f} m' for k,v in g['faixas_m'].items()))
            partes.append('Origens alcançáveis: '+(origens or 'nenhuma na hipótese'))
            if g['uid']==self.dados['componentes'][0]['uid']:partes.append('Maior componente por extensão no escopo analisado.')
            perto=g.get('origem_mais_proxima')
            if perto:
                nome=self.comps_origens[perto['uuid']].get('nome') or perto['uuid'][:8]
                partes.append(f"Origem mais próxima geometricamente: {nome} · {perto['distancia_m']:.2f} m")
            if g.get('componentes_candidatos'):
                partes.append('Outros componentes junto de candidatas: '+', '.join(u[:8] for u in g['componentes_candidatos'][:12]))
            if g['zonas']:partes.append('Interseções espaciais: '+', '.join(g['zonas']))
        if 'distancia_m' in r:
            partes.append(f"Distância: {r['distancia_m']:.3f} m · alternativas: {r.get('concorrentes',0)}")
        if r.get('tipo')=='CONEXAO_T':
            partes.append('Nós cadastrais ou pontas próximas do ponto projetado: '+
                          str(len(r.get('junctions_proximas',[]))+len(r.get('pontas_proximas',[]))))
        if r['tubos']:
            partes.append('Tubulações: '+', '.join(str(self.tubos[t].get('id') or t[:8]) for t in r['tubos'][:12]))
        if r.get('motivo') or r.get('criterio'):partes.append(r.get('motivo') or r['criterio'])
        if g and g.get('nos'):
            partes.append('Nós: '+', '.join(u[:8] for u in g['nos'][:8]))
        decisao=self._decisoes_resultado.get(r['uid'],{})
        estado=decisao.get('acompanhamento','PENDENTE')
        self.acompanhamento.setCurrentIndex(max(0,self.acompanhamento.findData(estado)))
        partes.append('Acompanhamento: '+ACOMPANHAMENTO.get(estado,'Pendente'))
        if decisao.get('nota'):partes.append('Observação: '+decisao['nota'])
        hip=self.dados.get('hipotese')
        partes.append('Hipótese: '+(hip['nome']+' · '+hip['rev'][:8] if hip else 'Execução temporária'))
        self.detalhes.setText(f"Página {self._pagina+1} · {len(self._lista_resultados)} resultados\n"+'\n'.join(partes))

    def destacar(self,checked=False,aproximar=False):
        r=self._selecionado()
        if r is None or self.central.ocupado():return
        d=self.dados
        # Agrupa geometrias por papel para manter poucos itens no canvas.
        tubos=[geometria(self.tubos[t]['wkb']) for t in r['tubos']]
        grupos=[]
        if tubos:grupos.append(('tubo',QgsGeometry.collectGeometry([g for g in tubos if g])))
        g=self.componentes.get(r.get('componente',r['uid']))
        if g:
            pontos=[QgsPointXY(*self.nos[u]['xy']) for u in g['nos']]
            if pontos:grupos.append(('local',QgsGeometry.fromMultiPointXY(pontos)))
        if r.get('wkb'):grupos.append(('evento',geometria(r['wkb'])))
        for uid in (g['origens'] if g else []):
            origem=self.comps_origens[uid]
            geom=geometria(origem.get('wkb'))
            if geom is None and origem.get('xy'):
                geom=QgsGeometry.fromPointXY(QgsPointXY(*origem['xy']))
            if geom and origem.get('crs'):
                from qgis.core import QgsCoordinateTransform
                trans=QgsCoordinateTransform(QgsCoordinateReferenceSystem(origem['crs']),
                    QgsCoordinateReferenceSystem(d['crs']),QgsProject.instance())
                if geom.transform(trans)==0:grupos.append(('equipamento',geom))
        self._com_erro(lambda:self.central.mapa.destacar_investigacao(
            grupos,QgsCoordinateReferenceSystem(d['crs']),aproximar,toda_extensao=True))

    def revisar_conexao(self):
        r=self._selecionado()
        if not r or r.get('tipo') not in ('CONEXAO_T','CRUZAMENTO','EXTREMIDADES_PROXIMAS'):return
        antigos=[c for c in {**self.registros,**self._pinos}.values() if c.get('candidato')==r['uid']]
        self.editar('CONEXAO',antigos[0] if len(antigos)==1 else None,candidato=r)

    def _id_resultado(self):
        from auditoria_fronteiras.entradas import digest
        r=self._selecionado()
        return digest([self.dados['uuid'],r['uid']]) if r else None

    def anotar(self):
        uid=self._id_resultado()
        if not uid or self.central.ocupado():return
        anterior=self.registros.get(uid,dict(uuid=uid))
        txt,ok=QInputDialog.getMultiLineText(self,'Observação do resultado','Observação',anterior.get('nota',''))
        if ok:
            alvo=self._selecionado()
            estado=self.acompanhamento.currentData()
            r=self._com_erro(lambda:self._salvar('DECISAO',dict(nota=txt,execucao=self.dados['uuid'],
                                               alvo=alvo['uid'],acompanhamento=estado),anterior))
            if r:self.selecionar_resultado_uid(alvo['uid'],self.categoria.currentData())

    def _mostrar_historico(self,uid):
        if not uid or self.central.ocupado():return
        def mostrar():
            rs=pg.revisoes(self._base_complementos(),self.uid_projeto,uid)
            def resumo(r):
                estado=ACOMPANHAMENTO.get(r.get('acompanhamento')) or pg.DECISOES.get(r.get('decisao'))
                return r['data_utc']+' · '+(estado or ('Habilitado' if r.get('habilitado',True) else 'Desabilitado'))+(
                    '\n'+r['nota'] if r.get('nota') else '')
            self.historico.setPlainText('\n\n'.join(resumo(r) for r in rs) or 'Nenhuma revisão registrada.')
            self.historico.show()
        self._com_erro(mostrar)

    def historico_resultado(self):
        self._mostrar_historico(self._id_resultado())

    def historico_elemento(self):
        r=self._registro_selecionado()
        if r:self._mostrar_historico(r['uuid'])

    def comparar(self):
        d=self.dados
        if not d or self.central.ocupado():return
        rs=[r for r in self._projeto()['bases'] if r['tipo']=='TOPOLOGIA_GIS' and r['uuid']!=d['uuid']]
        if not rs:
            self.status.setText('Salve outra execução deste projeto para comparar hipóteses.')
            return
        nomes=[Path(r['base']).name+' · '+r['uuid'][:8] for r in rs]
        nome,ok=QInputDialog.getItem(self,'Comparar hipóteses','Execução de referência',nomes,editable=False)
        if not ok:return
        r=rs[nomes.index(nome)]
        def trabalho(parar,etapa):
            antiga=pg.carregar(r['base'],r['uuid'],d['projeto_uid'])
            return antiga,hg.comparar_execucoes(antiga,d)
        def pronto(dados):
            antiga,diff=dados
            self._comparadas=(antiga,d)
            self._comparacao_antes={t['uid']:t for t in antiga['tubos']}
            self._comparacao_depois={t['uid']:t for t in d['tubos']}
            self.comparacao.blockSignals(True)
            self.comparacao.limpar()
            for linha in diff['diferencas']:
                self.comparacao.inserir((linha['nome'],linha['antes'],linha['depois'],len(linha['tubos'])),linha)
            self.comparacao.blockSignals(False)
            self.comparacao.show()
            a,b=diff['componentes']
            antes,depois=diff['sem_origem_m']
            def medida(n):return 'indeterminado' if n is None else f'{n:.2f} m'
            self.status.setText(f"Componentes {a} → {b} · {diff['unioes']} união(ões) · {diff['divisoes']} divisão(ões). "
                                f"Sem origem {medida(antes)} → {medida(depois)}. "
                                f"Acesso topológico acrescentado a {diff['passou_alcancar_m']:.2f} m em trechos comuns.")
        self.app.atividades.executar_thread('Comparar topologias GIS',d['nome'],trabalho,pronto,self.status.setText)

    def destacar_diferenca(self,linha,*_):
        item=self.comparacao.item(linha,0) if linha>=0 else None
        if item is None:return
        r=item.data(Qt.UserRole)
        a,b=self._comparadas
        from .mapa_topologia_gis import _transformar,geometria_referencia
        crs_b=QgsCoordinateReferenceSystem(b['crs'])
        def mostrar():
            grupos=[]
            for foto,inventario,papel,simbolo in ((a,self._comparacao_antes,'evento','evento'),(b,self._comparacao_depois,'tubo','equipamento')):
                crs=QgsCoordinateReferenceSystem(foto['crs'])
                gs=[_transformar(g,crs,crs_b) for uid in r['tubos'] if uid in inventario
                    for g in [geometria(inventario[uid]['wkb'])] if g is not None]
                if gs and (papel=='tubo' or r['tipo'] in ('AUSENTE','DIVIDIDO','PERDEU')):
                    grupos.append((papel,QgsGeometry.collectGeometry(gs)))
                rel=next((o for o in foto['participantes'] if o['uuid']==r.get('relacao')),None)
                if rel:
                    g=geometria_referencia(rel,crs_b)
                    if g:grupos.append((simbolo,g))
            if grupos:self.central.mapa.destacar_investigacao(grupos,crs_b)
        self._com_erro(mostrar)

    def exportar(self,formato):
        if not self.dados or self.central.ocupado():return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de exportação',str(self._pasta()))
        if not pasta:return
        from .exportar_grafo_gis import exportar
        d=self.dados
        self.app.atividades.executar_thread('Exportar topologia GIS',d['nome'],
            lambda parar,etapa:exportar(d,pasta,formato,parar,etapa),
            lambda destino:self.status.setText('Exportação salva em '+str(destino)),self.status.setText)
