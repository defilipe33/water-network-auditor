"""Apresentação e decisões sobre vínculos já calculados, sem reexecutar auditoria."""
import json
import sqlite3
from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout,QLineEdit,QComboBox,QPlainTextEdit,QMessageBox,QDoubleSpinBox
from qgis.core import QgsProject,QgsCoordinateReferenceSystem,QgsGeometry,QgsPointXY
from .modelo_gis_ui import aviso,botao,expansivel,formulario,tabela,linha,secao
from .navegacao_cartografica import acao_disponivel,navegar_registros
from .investigacao_gis import IndiceInvestigacao,SITUACOES,descricao,geometria
from .relevancia_gis import ROTULOS,VERSAO
from auditoria_fronteiras import revisoes_ocorrencias as individuais
from auditoria_fronteiras.persistencia import salvar_revisao,historico
from auditoria_fronteiras.inspecao import detalhes_local


def combo(itens):
    b=QComboBox()
    for k,v in itens.items():b.addItem(v,k)
    return b


class PainelInvestigacaoGIS:
    def montar_investigacao(self,v):
        self.indice=None;self._evento_uid=None;self._historico=[];self._cache_geometrias={};self._destaque_alvo=None
        secao(v,'RESULTADOS')
        self.busca=QLineEdit();self.busca.setPlaceholderText('Pesquisar local ou identificador de tubulação');v.addWidget(self.busca)
        self.busca.editingFinished.connect(self.filtrar)
        self.filtro_relevancia=combo({'ATENCAO':'Precisam de revisão','':'Todas as ocorrências',**ROTULOS})
        v.addWidget(self.filtro_relevancia);self.filtro_relevancia.currentIndexChanged.connect(self.filtrar)
        self.relevancia_info=aviso();v.addWidget(self.relevancia_info)
        _,filtros=expansivel(v,'Filtrar resultados')
        f=formulario(filtros)
        self.filtro_situacao=combo({'':'Todas as situações',**SITUACOES})
        self.filtro_tipo=combo({'':'Todos os tipos'})
        self.filtro_categoria=combo({'':'Todas as análises','PERIMETRO':'Contato com perímetro','TRANSICAO':'Transição entre regiões'})
        self.filtro_regiao=QLineEdit();self.filtro_regiao.setPlaceholderText('Nome, ID ou camada de setor / zona');f.addRow('Setor / zona',self.filtro_regiao);self.filtro_regiao.editingFinished.connect(self.filtrar)
        self.filtro_equipamento=QLineEdit();self.filtro_equipamento.setPlaceholderText('Consultar equipamentos para habilitar');self.filtro_equipamento.setEnabled(False);f.addRow('Equipamento',self.filtro_equipamento);self.filtro_equipamento.editingFinished.connect(self.filtrar)
        for label,b in [('Situação',self.filtro_situacao),('Tipo de ocorrência',self.filtro_tipo),('Categoria da análise',self.filtro_categoria)]:
            f.addRow(label,b);b.currentIndexChanged.connect(self.filtrar)
        botao(filtros,'Limpar filtros',self.limpar_filtros)
        self.lista=tabela(['Local','Ocorrências','Tubulações','Acompanhamento']);self.lista.setMinimumHeight(120);self.lista.setMaximumHeight(240);v.addWidget(self.lista)
        self.lista.currentCellChanged.connect(self.escolher_local)
        navegar_registros(self.lista,lambda i,a:self.navegar_alvo(i,a),
                          self.acoes_alvo,self.limpar_destaque)
        nav=QHBoxLayout();v.addLayout(nav)
        botao(nav,'Local anterior',lambda:self.navegar(-1));botao(nav,'Próximo local',lambda:self.navegar(1))
        self.pagina_info=aviso();v.addWidget(self.pagina_info)
        pag=QHBoxLayout();filtros.addLayout(pag)
        botao(pag,'Página anterior',lambda:self.paginar(-1));botao(pag,'Próxima página',lambda:self.paginar(1))
        self.detalhes_b,det=expansivel(v,'DETALHES DO LOCAL')
        self.detalhes_widget=det.parentWidget()
        self.local_info=aviso();det.addWidget(self.local_info)
        self.eventos_lista=tabela(['Ocorrência','Relevância','Classificação','Análise','Ambiguidade','Decisão individual']);self.eventos_lista.setMaximumHeight(150);det.addWidget(self.eventos_lista)
        self.eventos_lista.currentCellChanged.connect(self.escolher_evento_tabela)
        navegar_registros(self.eventos_lista,lambda i,a:self.navegar_alvo(i,a,evento=True),
                          lambda i:self.acoes_alvo(i,evento=True),self.limpar_destaque)
        self.descricao_evento=QPlainTextEdit();self.descricao_evento.setReadOnly(True);self.descricao_evento.setMaximumHeight(130);det.addWidget(self.descricao_evento)
        self.tubos_lista=tabela(['ID cadastral','Camada de origem']);self.tubos_lista.setMaximumHeight(120);det.addWidget(self.tubos_lista)
        navegar_registros(self.tubos_lista,lambda i,a:self.destacar(
            aproximar=a,somente_tubos=True,tubos_uids={self.tubos_lista.item(i.row(),0).data(Qt.UserRole)}),
            limpar=self.limpar_destaque)
        self.poligonos_info=aviso();det.addWidget(self.poligonos_info)
        _,equip=expansivel(det,'Equipamentos próximos e associações declaradas')
        equip.addWidget(aviso('Consulta opcional às fontes atuais do Modelo GIS. Proximidade não confirma conexão; associações declaradas podem estar afastadas da tubulação. Não altera relevância ou topologia.'))
        self.raio_equipamento=QDoubleSpinBox();self.raio_equipamento.setRange(0,1000);self.raio_equipamento.setValue(20);self.raio_equipamento.setSuffix(' m');formulario(equip).addRow('Distância para contexto',self.raio_equipamento)
        botao(equip,'Consultar / atualizar equipamentos',self.consultar_equipamentos)
        self.equipamentos_info=aviso('Equipamentos ainda não consultados.');equip.addWidget(self.equipamentos_info)
        self.equipamentos_lista=tabela(['Tipo','ID / nome','Fonte','Relação','Distância (m)']);self.equipamentos_lista.setMaximumHeight(150);equip.addWidget(self.equipamentos_lista)
        navegar_registros(self.equipamentos_lista,self.navegar_equipamento,limpar=self.limpar_destaque)
        self._equipamentos=None;self._equipamentos_chave=None
        self.tecnicos_b,tec=expansivel(det,'Informações técnicas das ocorrências')
        self.tecnicos_info=QPlainTextEdit();self.tecnicos_info.setReadOnly(True);self.tecnicos_info.setMaximumHeight(180);tec.addWidget(self.tecnicos_info)
        self.tecnicos_b.toggled.connect(lambda aberto:self.mostrar_tecnicos() if aberto else None)
        _,mapa=expansivel(v,'MAPA')
        mapa.addWidget(aviso('Tubulações: azul · local: quadrado violeta. Pontos de ocorrência: círculo azul-cinza informativo, triângulo âmbar a revisar, losango vermelho inconsistência, quadrado roxo indeterminado. O ponto representa o evento, não uma conexão hidráulica.'))
        botao(mapa,'Destacar local e elementos',self.destacar)
        botao(mapa,'Destacar tubulações',lambda:self.destacar(somente_tubos=True))
        botao(mapa,'Aproximar local',self.aproximar)
        botao(mapa,'Ver toda a extensão dos elementos',lambda:self.destacar(aproximar=True,toda_extensao=True))
        botao(mapa,'Limpar destaque',self.limpar_destaque)
        secao(v,'ANÁLISE E DECISÃO')
        self.alvo=QComboBox();formulario(v).addRow('Analisar',self.alvo);self.alvo.currentIndexChanged.connect(self.escolher_alvo)
        self.situacao=combo({k:v for k,v in SITUACOES.items() if k!='MISTO'});formulario(v).addRow('Situação',self.situacao)
        self.observacao=QPlainTextEdit();self.observacao.setPlaceholderText('Observação opcional');self.observacao.setMaximumHeight(85);v.addWidget(self.observacao)
        self.salvar_b=botao(v,'Salvar decisão',self.salvar_decisao);self.salvar_b.setObjectName('Principal')
        self.historico_b,h=expansivel(v,'HISTÓRICO')
        self.historico_widget=h.parentWidget()
        h.addWidget(aviso('Revisões do agrupamento ou da ocorrência escolhida. Recuperar preenche um rascunho; Salvar cria uma nova revisão.'))
        botao(h,'Consultar histórico do alvo selecionado',self.historico)
        self.historico_lista=tabela(['Data (UTC)','Situação','Observação']);self.historico_lista.setMaximumHeight(150);h.addWidget(self.historico_lista)
        navegar_registros(self.historico_lista,lambda _,a:self.destacar(aproximar=a),
                          lambda _: [('Recuperar revisão como rascunho',self.recuperar_revisao)],self.limpar_destaque)
        botao(h,'Recuperar revisão selecionada',self.recuperar_revisao)
        self.historico_info=aviso();h.addWidget(self.historico_info)
        self.exportacao_b,e=expansivel(v,'EXPORTAÇÃO');self.exportacao_widget=e.parentWidget()
        e.addWidget(aviso('Exportar trabalho gera arquivos GIS e tabelas; não executa novamente a análise.'))
        botao(e,'Exportar GeoPackage completo…',self.exportar_gpkg)
        botao(e,'Exportar Shapefile e tabelas…',self.exportar_shp)
        _,leg=expansivel(e,'Compatibilidade avançada')
        botao(leg,'Abrir visualizador anterior',self.abrir_legado)
        self._filtros_aplicados=('', '', '', '', 'ATENCAO', '', '')
        self.detalhes_b.setChecked(True)

    def filtro(self):return (self.busca.text(),self.filtro_situacao.currentData(),self.filtro_tipo.currentData(),self.filtro_categoria.currentData(),self.filtro_relevancia.currentData(),self.filtro_regiao.text(),self.filtro_equipamento.text())

    def filtrar(self,*_):
        if not self.indice:return
        if self.filtro_equipamento.text().strip() and not self.equipamentos_validos():
            self.info.setText('Atualize a consulta de equipamentos ou limpe esse filtro; o contexto anterior não será usado.');return
        if not self.resolver():
            busca,estado,classe,tipo,relevancia,regiao,equipamento=self._filtros_aplicados
            for b,valor in [(self.busca,busca),(self.filtro_situacao,estado),(self.filtro_tipo,classe),(self.filtro_categoria,tipo),(self.filtro_relevancia,relevancia),(self.filtro_regiao,regiao),(self.filtro_equipamento,equipamento)]:
                b.blockSignals(True)
                if isinstance(b,QLineEdit):b.setText(valor)
                else:b.setCurrentIndex(b.findData(valor))
                b.blockSignals(False)
            return
        self._pagina=0;self.listar()

    def limpar_filtros(self):
        if not self.resolver():return
        for b in (self.busca,self.filtro_situacao,self.filtro_tipo,self.filtro_categoria,self.filtro_regiao,self.filtro_relevancia,self.filtro_equipamento):
            b.blockSignals(True)
            b.clear() if isinstance(b,QLineEdit) else b.setCurrentIndex(b.findData(''))
            b.blockSignals(False)
        self.filtrar()

    def listar(self,preferido=None):
        self.lista.blockSignals(True);self.lista.setRowCount(0)
        self._filtrados=self.indice.filtrar(*self.filtro()) if self.indice else []
        self._filtros_aplicados=self.filtro()
        if self.indice:
            contagens=self.indice.contagens_relevancia
            self.relevancia_info.setText(f'{len(self.indice.eventos)} eventos geométricos · '+ ' · '.join(f'{ROTULOS[k]}: {n}' for k,n in contagens.items())+'\nRegra '+VERSAO+' aplicada aos registros carregados, sem alterar eventos ou decisões históricos.')
        if preferido is None and self.selecionado:preferido=self.selecionado['uid']
        ids=[l['uid'] for l in self._filtrados]
        if preferido in ids:self._pagina=ids.index(preferido)//200
        self._pagina=max(0,min(self._pagina,max(0,(len(ids)-1)//200)))
        self._visiveis=self._filtrados[self._pagina*200:(self._pagina+1)*200]
        for l in self._visiveis:
            r=l['registro'];linha(self.lista,[r['LOCAL'],r['N_EVENTOS'],r['N_TUBOS'],SITUACOES[self.indice.situacao(l['uid'])]])
        self.lista.setFixedHeight(min(220,max(85,self.lista.horizontalHeader().height()+22*min(len(self._visiveis),8)+4)))
        self.lista.blockSignals(False)
        self.selecionado=None;self._evento_uid=None
        ativos=[rotulo+': '+valor for rotulo,valor in [('Pesquisa',self.busca.text()),('Situação',self.filtro_situacao.currentText() if self.filtro_situacao.currentData() else ''),('Tipo',self.filtro_tipo.currentText() if self.filtro_tipo.currentData() else ''),('Categoria',self.filtro_categoria.currentText() if self.filtro_categoria.currentData() else '')] if valor]
        ativos += [rotulo+': '+valor for rotulo,valor in [('Relevância',self.filtro_relevancia.currentText() if self.filtro_relevancia.currentData() else ''),('Setor / zona',self.filtro_regiao.text()),('Equipamento',self.filtro_equipamento.text())] if valor]
        self.pagina_info.setText(f'{len(ids)} locais encontrados · {len(self.indice.locais) if self.indice else 0} no trabalho · página {self._pagina+1}. '+('Filtros ativos: '+' · '.join(ativos) if ativos else 'Sem filtros.'))
        if self._visiveis:
            uids=[l['uid'] for l in self._visiveis];self.lista.setCurrentCell(uids.index(preferido) if preferido in uids else 0,0)
        else:
            self.mostrar_local()
            if self.indice:self.pagina_info.setText(self.pagina_info.text()+' Nenhum local atende aos filtros. Escolha Todas as ocorrências para consultar também as informativas e indeterminadas.')

    def paginar(self,delta):
        if not self.resolver():return
        self._pagina+=delta;self.selecionado=None;self.listar()

    def navegar(self,delta):
        if not self.resolver() or not self._filtrados:return
        ids=[l['uid'] for l in self._filtrados];atual=ids.index(self.selecionado['uid']) if self.selecionado else 0
        self.listar(ids[max(0,min(len(ids)-1,atual+delta))])

    def escolher_local(self,atual,coluna=0,anterior=-1,*_):
        destino=self._visiveis[atual]['uid'] if 0<=atual<len(self._visiveis) else None
        if not self.resolver():
            self.lista.blockSignals(True)
            if anterior>=0:self.lista.setCurrentCell(anterior,0)
            self.lista.blockSignals(False);return
        self.selecionado=self.indice.locais.get(destino) if self.indice else None
        self._evento_uid=None;self.limpar_destaque();self.mostrar_local()

    def mostrar_local(self):
        self.alvo.blockSignals(True);self.alvo.clear();self.eventos_lista.blockSignals(True);self.eventos_lista.setRowCount(0)
        if self.selecionado:
            l=self.selecionado;d=detalhes_local(self.dossie,l['uid'],self.indice)
            self.local_info.setText(f"{l['registro']['LOCAL']} · {len(d['eventos'])} ocorrências · {len(d['tubulacoes'])} tubulações. "
                'Decisão do agrupamento: '+SITUACOES[l['revisao']['situacao']]+'. Acompanhamento: '+SITUACOES[self.indice.situacao(l['uid'])]+'.')
            self.alvo.addItem('Agrupamento '+l['registro']['LOCAL'],None)
            for e in d['eventos']:
                self.alvo.addItem('Ocorrência '+str(e['registro']['ID'])+' · '+e['tecnico']['classificacao'],e['uid'])
                rev=self.indice.revisoes.get(e['uid'])
                linha(self.eventos_lista,[e['registro']['ID'],ROTULOS[self.indice.relevancias[e['uid']]['categoria']],e['tecnico']['classificacao'].replace('_',' ').capitalize(),'Perímetro' if e['tecnico']['modo']=='PERIMETRO' else 'Transição',e['registro']['AMBIGUO'],SITUACOES[rev['situacao']] if rev else 'Sem decisão individual'],e['uid'])
        else:self.local_info.setText('Selecione um local.');self.descricao_evento.clear();self.tubos_lista.setRowCount(0);self.poligonos_info.clear();self.equipamentos_lista.setRowCount(0)
        self.alvo.blockSignals(False);self.eventos_lista.blockSignals(False);self.carregar_alvo()
        self.eventos_lista.setFixedHeight(min(160,max(75,self.eventos_lista.horizontalHeader().height()+22*self.eventos_lista.rowCount()+4)))

    def revisao_alvo(self):
        if not self.selecionado:return dict(situacao='PENDENTE',observacoes='')
        return (self.indice.revisoes.get(self._evento_uid,dict(situacao='PENDENTE',observacoes=''))
                if self._evento_uid else self.selecionado['revisao'])

    def escolher_evento_tabela(self,row,*_):
        if row>=0 and self.selecionado:self.alvo.setCurrentIndex(row+1)

    def navegar_alvo(self,indice,aproximar,evento=False,extensao=False):
        if not self.selecionado:return
        alvo=self.alvo.itemData(indice.row()+1) if evento else None
        if alvo!=self._evento_uid:
            self.alvo.setCurrentIndex(self.alvo.findData(alvo))
        if alvo==self._evento_uid:self.destacar(aproximar=aproximar,toda_extensao=extensao)

    def acoes_alvo(self,indice,evento=False):
        def acao(fn):
            alvo=self.alvo.itemData(indice.row()+1) if evento else None
            if self._evento_uid!=alvo:self.alvo.setCurrentIndex(self.alvo.findData(alvo))
            if self._evento_uid==alvo:fn()
        return [('Enquadrar toda a extensão',lambda:self.navegar_alvo(indice,True,evento,True)),
                ('Alterar situação ou observação',lambda:acao(self.observacao.setFocus)),
                ('Consultar histórico',lambda:acao(self.historico))]

    def navegar_equipamento(self,indice,aproximar):
        registros=self.equipamentos_alvo()
        if not 0<=indice.row()<len(registros) or self.central.ocupado():return
        r=registros[indice.row()]
        crs=QgsCoordinateReferenceSystem(self.dossie['contexto']['parametros']['crs'])
        if not self.central.mapa.destacar_investigacao([('equipamento',r['geometria'])],crs,aproximar):
            self.equipamentos_info.setText('Geometria indisponível para este equipamento.')

    def escolher_alvo(self,i):
        anterior=self._evento_uid
        destino=self.alvo.itemData(i)
        if not self.resolver():
            self.alvo.blockSignals(True);self.alvo.setCurrentIndex(max(0,self.alvo.findData(anterior)));self.alvo.blockSignals(False);self.sincronizar_evento();return
        self.alvo.blockSignals(True);self.alvo.setCurrentIndex(max(0,self.alvo.findData(destino)));self.alvo.blockSignals(False)
        self._evento_uid=destino;self.limpar_destaque();self.carregar_alvo()

    def sincronizar_evento(self):
        self.eventos_lista.blockSignals(True)
        self.eventos_lista.setCurrentCell(self.alvo.currentIndex()-1,0)
        if self.alvo.currentIndex()==0:self.eventos_lista.clearSelection()
        self.eventos_lista.blockSignals(False)

    def carregar_alvo(self):
        self.sincronizar_evento()
        r=self.revisao_alvo();self.situacao.setCurrentIndex(self.situacao.findData(r['situacao']));self.observacao.setPlainText(r['observacoes'])
        acao_disponivel(self.salvar_b,'' if self.selecionado else 'Selecione um local ou ocorrência antes de salvar.')
        self.historico_lista.setRowCount(0);self._historico=[];self.historico_info.clear()
        if not self.selecionado:return
        d=detalhes_local(self.dossie,self.selecionado['uid'],self.indice,self._evento_uid)
        self.descricao_evento.setPlainText('\n\n'.join('Ocorrência '+str(e['registro']['ID'])+': '+descricao(e)+'\n'+ROTULOS[self.indice.relevancias[e['uid']]['categoria']]+': '+self.indice.relevancias[e['uid']]['motivo']+'\n'+'\n'.join(map(str,e['tecnico'].get('observacoes',[]))) for e in d['eventos']))
        self.tubos_lista.setRowCount(0)
        for t in d['tubulacoes']:
            linha(self.tubos_lista,[t['id_exibido'],t['camada']],t['uid'])
            self.tubos_lista.item(self.tubos_lista.rowCount()-1,0).setData(Qt.UserRole,t['uid'])
        self.tubos_lista.setFixedHeight(min(140,max(75,self.tubos_lista.horizontalHeader().height()+22*self.tubos_lista.rowCount()+4)))
        self.poligonos_info.setText('Regiões / polígonos: '+'; '.join(str(p.get('nome') or p.get('id_original') or 'Sem identificação')+' · '+p['camada'] for p in d['poligonos']) if d['poligonos'] else 'Sem região associada neste registro.')
        self.mostrar_equipamentos()
        if self.tecnicos_b.isChecked():self.mostrar_tecnicos()
        if self.historico_b.isChecked():self.historico()

    def mostrar_tecnicos(self):
        if not self.selecionado:return
        d=self.indice.detalhes(self.selecionado['uid'],self._evento_uid)
        self.tecnicos_info.setPlainText(json.dumps([{k:v for k,v in e['tecnico'].items() if k not in ('geometria_wkb_hex','apresentacao')} for e in d['eventos']],ensure_ascii=False,indent=2,default=str))

    def chave_equipamentos(self):
        return (self.dossie['execucao_uid'] if self.dossie else None,
                self.central.projetos.dados.get('ativo'),self._geracao,self.raio_equipamento.value(),
                json.dumps(self.central.modelo_gis.fontes,sort_keys=True,default=str))

    def equipamentos_validos(self):
        return self._equipamentos is not None and self._equipamentos_chave==self.chave_equipamentos()

    def consultar_equipamentos(self):
        if not self.dossie or self.central.ocupado():return
        from .contexto_equipamentos_gis import preparar,ler
        try:
            m=self.central.modelo_gis
            prep=preparar(m.fontes,list(m.camadas()),self.dossie['contexto']['parametros']['crs'],QgsProject.instance().transformContext())
            from .modelo_gis import identificar
            camadas=list(m.camadas())
            for f in m.fontes:
                c=identificar(f,camadas)
                if c is None:continue
                if not hasattr(c,'dataChanged') or c.id() in self._observadas:continue
                self._observadas.add(c.id())
                for s in ('dataChanged','dataSourceChanged','updatedFields','crsChanged','subsetStringChanged'):
                    getattr(c,s).connect(self.fonte_mudou)
            chave=self.chave_equipamentos();d=self.dossie;raio=self.raio_equipamento.value()
            def pronto(dados):
                if self.chave_equipamentos()!=chave:
                    self.equipamentos_info.setText('Contexto alterado durante a consulta; atualize os equipamentos.');return
                self._equipamentos,avisos=dados;self._equipamentos_chave=chave
                self.indice.equipamentos_textos={e:' '.join(str(r[k]) for r in rs for k in ('id','nome','categoria','camada','relacao')).casefold() for e,rs in self._equipamentos.por_evento.items()}
                self.filtro_equipamento.setEnabled(True);self.filtro_equipamento.setPlaceholderText('ID, nome, tipo ou fonte dos equipamentos consultados')
                self.equipamentos_info.setText('Contexto das fontes atuais consultado. '+(' '.join(avisos) if avisos else 'Nenhuma conexão inferida.'))
                self.mostrar_equipamentos()
            self.app.atividades.executar_thread('Consultando equipamentos GIS','Contexto espacial e associações declaradas, sem alterar conectividade',lambda parar,_:ler(prep,d,parar,raio),pronto,lambda erro:self.equipamentos_info.setText(erro+' Contexto anterior não alterado.'))
        except (ValueError,RuntimeError) as e:self.equipamentos_info.setText(str(e))

    def equipamentos_alvo(self):
        if not self.selecionado or not self.equipamentos_validos():return []
        ids=[self._evento_uid] if self._evento_uid else self.selecionado['eventos']
        registros={}
        for e in ids:
            for r in self._equipamentos.por_evento.get(e,[]):
                chave=(r['indice'],r['relacao'])
                registros.setdefault(chave,r)
        return list(registros.values())

    def mostrar_equipamentos(self):
        self.equipamentos_lista.setRowCount(0)
        if self._equipamentos is not None and not self.equipamentos_validos():
            self.equipamentos_info.setText('Fontes, projeto ou parâmetros alterados. Atualize a consulta antes de usar este contexto.')
            self.filtro_equipamento.setEnabled(False);self.indice.equipamentos_textos={}
        for r in self.equipamentos_alvo():
            linha(self.equipamentos_lista,[r['categoria'],str(r['id'])+' '+r['nome'],r['camada'],r['relacao'],f"{r['distancia']:.2f}" if r['distancia'] is not None else 'Sem geometria'])

    def pendente(self):
        r=self.revisao_alvo()
        return bool(self.selecionado and (self.observacao.toPlainText()!=r['observacoes'] or self.situacao.currentData()!=r['situacao']))

    def resolver(self):
        if not self.pendente():return True
        r=QMessageBox.question(self,'Decisão não salva','Salvar as alterações do alvo selecionado?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if r==QMessageBox.Save:return self.salvar_decisao()
        if r==QMessageBox.Discard:
            rev=self.revisao_alvo();self.situacao.setCurrentIndex(self.situacao.findData(rev['situacao']));self.observacao.setPlainText(rev['observacoes']);return True
        return False

    def salvar_observacao(self):return self.salvar_decisao()

    def proteger_gravacao(self):
        """Evita leitura OGR em renderização durante DDL/gravação SQLite."""
        from qgis.PyQt import sip
        base=str(Path(self.base).resolve())
        canvases=[self.central.mapa.canvas]
        iface=getattr(self.app,'iface',None)
        if iface is not None and hasattr(iface,'mapCanvases'):canvases+=list(iface.mapCanvases())
        estados={c:c.isFrozen() for c in canvases if c is not None and not sip.isdeleted(c)}
        for c in estados:c.stopRendering();c.freeze(True)
        restaurado=False
        def restaurar():
            nonlocal restaurado
            if restaurado:return
            restaurado=True
            try:
                for layer in QgsProject.instance().mapLayers().values():
                    if layer.customProperty('wna/categoria')=='gis' and layer.customProperty('wna/base')==base:
                        layer.dataProvider().reloadData();layer.triggerRepaint()
            finally:
                for c,congelado in estados.items():
                    if not sip.isdeleted(c):
                        c.freeze(congelado)
                        if not congelado:c.refresh()
        return restaurar

    def salvar_decisao(self):
        if not self.selecionado or not self.base or self.central.ocupado():return False
        uid=self.selecionado['uid'];e=self._evento_uid;rev=self.revisao_alvo();estado=self.situacao.currentData();texto=self.observacao.toPlainText().strip()
        restaurar=None
        try:
            restaurar=self.proteger_gravacao()
            if e:
                def pronto(r):
                    self.indice.revisoes[e]=r;self.aplicar_decisao(uid,e,texto)
                worker=self.app.atividades.executar_thread('Salvando decisão individual','Histórico e backup verificado quando necessário',
                    lambda parar,etapa:individuais.salvar(self.base,self.dossie['execucao_uid'],e,estado,texto,rev.get('rev_uid')),
                    pronto,lambda erro:self.info.setText(erro+' Rascunho preservado.'))
                worker.finished.connect(restaurar)
                self.app.atividades.atual.critica('Gravando decisão e verificando integridade')
                restaurar=None  # O sinal finished restaura também em falha/cancelamento.
                return False  # Uma navegação iniciada por resolver() deve aguardar a gravação.
            else:
                r=salvar_revisao(self.base,self.dossie['execucao_uid'],uid,estado,texto,esperada=rev.get('uid'))
                self.selecionado['revisao']=r;self.selecionado['registro']['SITUACAO']=estado
            self.aplicar_decisao(uid,e,texto);return True
        except (ValueError,OSError,RuntimeError,sqlite3.Error) as erro:
            self.info.setText(str(erro)+' Alterações preenchidas preservadas.');return False
        finally:
            if restaurar is not None:restaurar()

    def aplicar_decisao(self,uid,e,texto):
        # Atualizar o formulário antes de reconstruir a seleção evita falso rascunho.
        self.observacao.setPlainText(texto);self.listar(uid)
        if e and self.selecionado and self.selecionado['uid']==uid:self.alvo.setCurrentIndex(self.alvo.findData(e))
        self.info.setText('Decisão salva no histórico. A avaliação não modifica o cadastro nem comprova operação hidráulica.')

    def historico(self):
        if not self.selecionado:return
        try:
            self._historico=individuais.historico(self.base,self.dossie['execucao_uid'],self._evento_uid) if self._evento_uid else historico(self.base,self.dossie['execucao_uid'],self.selecionado['uid'])
            self.historico_lista.setRowCount(0)
            for r in self._historico:linha(self.historico_lista,[r.get('data_utc',r.get('data','')),SITUACOES[r['situacao']],r['observacoes']])
            self.historico_lista.setFixedHeight(min(150,max(75,self.historico_lista.horizontalHeader().height()+22*len(self._historico)+4)))
            self.historico_info.setText(f'{len(self._historico)} revisões do alvo selecionado.');self.historico_b.setChecked(True)
        except (ValueError,OSError,sqlite3.Error) as e:self.info.setText(str(e))

    def recuperar_revisao(self):
        i=self.historico_lista.currentRow()
        if not 0<=i<len(self._historico):return
        r=self._historico[i]
        if not self.resolver():return
        self.situacao.setCurrentIndex(self.situacao.findData(r['situacao']));self.observacao.setPlainText(r['observacoes'])
        self.info.setText('Revisão recuperada como rascunho. Salvar acrescenta uma nova revisão; o histórico anterior permanece.')

    def limpar_destaque(self):
        if self._destaque_alvo is not None:self.central.mapa.limpar()
        self._destaque_alvo=None

    def aproximar(self):return self.destacar(aproximar=True)

    def destacar(self,checked=False,somente_tubos=False,aproximar=False,toda_extensao=False,tubos_uids=None):
        if not self.selecionado or self.central.ocupado():return
        from .geometrias_investigacao import preparar,localizar
        uid,e=self.selecionado['uid'],self._evento_uid;d=detalhes_local(self.dossie,uid,self.indice,e)
        crs=QgsCoordinateReferenceSystem(self.dossie['contexto']['parametros']['crs'])
        gs={};faltantes=[]
        for t in d['tubulacoes']:
            if tubos_uids is not None and t['uid'] not in tubos_uids:continue
            g=geometria(t.get('geometria_wkb_hex'))
            if g is None and t['uid'] in self._cache_geometrias:g=geometria(self._cache_geometrias[t['uid']].hex())
            if g is None:faltantes.append(t)
            else:gs[t['uid']]=bytes(g.asWkb())
        def pronto(dados):
            if not self.selecionado or (self.selecionado['uid'],self._evento_uid)!=(uid,e):return False
            novos,avisos=dados;self._cache_geometrias.update(novos);novos={**gs,**novos}
            itens=[('tubo',geometria(w.hex())) for w in novos.values()]
            if not somente_tubos:
                itens += [('evento_'+self.indice.relevancias[x['uid']]['categoria'],geometria(x['tecnico'].get('geometria_wkb_hex'))) for x in d['eventos']]
                itens += [('equipamento',r['geometria']) for r in self.equipamentos_alvo() if r['relacao']=='Associação declarada']
                r=d['local']['registro'];itens.append(('local',QgsGeometry.fromPointXY(QgsPointXY(r['X'],r['Y']))))
            mostrou=self.central.mapa.destacar_investigacao(itens,crs,aproximar,toda_extensao)
            self._destaque_alvo=(uid,e) if mostrou else None
            texto='Destaque temporário aplicado. ' if mostrou else 'Geometria indisponível para esta seleção. '
            self.info.setText(texto+' '.join(avisos))
        if faltantes:
            prep=preparar(self.dossie,faltantes,QgsProject.instance())
            # Publicação pela thread principal após o worker finalizar; o gerenciador ainda está ocupado no callback.
            holder={}
            def receber(dados):holder['dados']=dados
            worker=self.app.atividades.executar_thread('Recuperando geometrias vinculadas','Somente fontes e assinaturas correspondentes',lambda parar,_:localizar(prep,crs.toWkt(),parar),receber,self.info.setText)
            operacao=self.app.atividades.atual
            worker.finished.connect(lambda:pronto(holder['dados']) if 'dados' in holder and operacao.estado=='CONCLUIDO' else None)
        else:pronto(({},[]))
