"""Investigação estrutural vinculada a uma execução da topologia do Modelo GIS."""

from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import sqlite3

from qgis.PyQt.QtCore import QAbstractListModel, QModelIndex, Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QInputDialog,
                                QLineEdit, QListView, QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget)
from qgis.core import QgsCoordinateReferenceSystem

from . import corredores_gis as motor, persistencia_grafo_gis as pg
from .corredores_agrupados_ui import CorredoresAgrupadosUI
from .mapa_topologia_gis import IndiceSelecao, escolher, fracao_clicada, _ponto, _transformar
from .modelo_gis import descrever, identificar, revisoes
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import acao_disponivel, navegar_registros
from .representacao_estrutura_gis import GeometriasEstrutura, carregar_camadas, exportar
from .tabelas_topologia_gis import TabelaGIS
from .topologia_gis_mapa_ui import MapaGIS


PAGINA=200
ESTADOS={
    'AVALIADA':'Avaliada','INDETERMINADA_LIMITE':'Indeterminada por limite',
    'PIPE_OBRIGATORIO':'Pipe obrigatório para a origem','CAMINHO_UNICO':'Caminho único no grafo',
    'DISJUNTA_VERIFICADA':'Alternativa sem Pipe em comum','PARCIAL_VERIFICADA':'Alternativa com Pipe em comum',
    'SEM_DISJUNTA_DA_ROTA_ESCOLHIDA':'Nenhuma alternativa disjunta desta rota',
    'NAO_TESTADA_LIMITE':'Alternativa ainda não testada','NO_DA_ORIGEM':'Destino é nó da origem',
    'ALCANCAVEL':'Com caminho topológico','SEM_CAMINHO':'Sem caminho','PARCIAL':'Alcance parcial',
    'SEM_ORIGENS':'Sem origens consideradas','SEM_DESTINO':'Sem destino topológico',
}
MUDANCAS={
    'TORNOU_CRITICA':'Tornou-se crítica','DEIXOU_CRITICA':'Deixou de ser crítica','FUNCAO':'Função estrutural',
    'PIPE_NOVO':'Pipe novo','PIPE_AUSENTE':'Pipe ausente','IMPACTO':'Comprimento dependente',
    'ZONA_GANHOU':'Zona ganhou acesso','ZONA_PERDEU':'Zona perdeu acesso','ZONA_DEPENDENCIAS':'Dependências da zona',
    'DESTINO_FONTES':'Fontes do destino','ALTERNATIVA':'Caminho alternativo','TRAJETO':'Trajeto principal',
    'ORIGEM_CONSIDERADA':'Origem considerada','CONEXAO_APLICADA':'Conexão aplicada na hipótese',
}


class ListaDestinos(QAbstractListModel):
    def __init__(self,pagina):
        super().__init__(pagina)
        self.pagina=pagina
        self.registros=[]

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.registros)

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid():return None
        d=self.registros[index.row()]
        if role==Qt.UserRole:return d['uid']
        if role in (Qt.DisplayRole,Qt.ToolTipRole):
            zona=(' · '+self.pagina._nome_area(d['zona'])) if d.get('zona') else ''
            return d['nome']+zona+(' · espacial' if d['modo']=='ESPACIAL' else '')

    def substituir(self,registros):
        self.beginResetModel()
        self.registros=list(registros)
        self.endResetModel()


class EstruturaGIS(QScrollArea,MapaGIS,CorredoresAgrupadosUI):
    def __init__(self,central):
        super().__init__(central)
        self.central=central;self.app=central.app
        self.projeto_uid=None;self.foto=None;self.dados=None;self.diferencas=[];self.interrupcao=None
        self._ferramenta=None;self._finalizar_ferramenta=None;self._indice={}
        self._destinos={};self._associacoes={};self._retiradas=set()
        self._pagina=0;self._ordem=None
        w=QWidget();self.setWidget(w);self.setWidgetResizable(True)
        v=QVBoxLayout(w)
        botao(v,'‹ Investigar minha rede',central.mudar_area)
        v.addWidget(aviso('Redes estruturantes GIS'))
        self.status=aviso();v.addWidget(self.status)
        v.addWidget(aviso('Os resultados descrevem conectividade topológica sob a hipótese escolhida.'))
        self.config_b,cfg=expansivel(v,'Execução, fontes e destinos')
        self.config_b.setChecked(True)
        form=formulario(cfg)
        self.execucoes=QComboBox();form.addRow('Execução topológica',self.execucoes)
        self.execucoes.activated.connect(self.escolher_execucao)
        self.identidade=aviso();cfg.addWidget(self.identidade)
        self.conferir_b=botao(cfg,'Conferir dados atuais das fontes',self.conferir_fontes)
        self.nome=QLineEdit('Redes estruturantes');form.addRow('Nome do trabalho',self.nome)
        self.origens=QListWidget();self.origens.setMaximumHeight(100);cfg.addWidget(self.origens)
        _,alvos=expansivel(cfg,'Destinos e zonas')
        self.selecao_tipo=QComboBox()
        self.selecao_tipo.addItem('Tubulação', 'PIPE');self.selecao_tipo.addItem('Nó topológico','NO')
        self.areas=QComboBox()
        f=formulario(alvos);f.addRow('Escolher no mapa',self.selecao_tipo);f.addRow('Área cadastrada',self.areas)
        botao(alvos,'Adicionar destinos pelo mapa',lambda:self.selecionar_mapa())
        botao(alvos,'Escolher uma área no mapa',self.selecionar_area_mapa)
        botao(alvos,'Adicionar tubulações que intersectam a área',self.adicionar_area)
        self.lista_destinos=QListView()
        self.modelo_destinos=ListaDestinos(self)
        self.lista_destinos.setModel(self.modelo_destinos)
        self.lista_destinos.setUniformItemSizes(True)
        self.lista_destinos.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lista_destinos.setMaximumHeight(135);alvos.addWidget(self.lista_destinos)
        navegar_registros(self.lista_destinos,self.localizar_destino,
                          lambda _: [('Remover os destinos selecionados',self.remover_destinos)],
                          limpar=central.mapa.limpar)
        botao(alvos,'Vincular destinos selecionados à área e salvar revisão',self.associar)
        botao(alvos,'Recuperar revisão dos destinos da área…',self.recuperar_associacao)
        botao(alvos,'Limpar destinos · analisar toda a rede',self.limpar_destinos)
        cfg.addWidget(aviso('Sem destinos, os cortes consideram a rede inteira. Cada cálculo salva um trabalho nesta execução.'))
        self.montar_configuracao_macro(v)
        self.executar_b=botao(v,'Calcular análise por Pipe',self.calcular)
        ferramentas=QHBoxLayout();v.addLayout(ferramentas)
        self.camadas_b=botao(ferramentas,'Mostrar camadas',self.mostrar_camadas)
        self.comparar_b=botao(ferramentas,'Comparar trabalhos…',self.comparar)
        self.resumo=aviso();v.addWidget(self.resumo)
        self.categoria=QComboBox()
        for k,n in [('CRITICA','Ligações críticas'),('TUBOS','Todas as tubulações'),('CORREDOR','Corredores por tubulação'),
                    ('ROTAS','Trajetos origem–destino'),('REDUNDANCIA','Redundância verificada'),('ZONAS','Dependências por zona'),
                    ('PASSAGEM','Redes de passagem'),('LOCAL','Distribuição local observada'),
                    ('INDETERMINADA','Função indeterminada'),('DESTINOS','Destinos'),('PONTES','Pipes com segmentos-ponte'),
                    ('ARTICULACOES','Nós de articulação'),('COMPONENTES','Componentes após interrupção'),
                    ('INTERROMPIDOS','Destinos após interrupção'),('REMANESCENTES','Rotas após interrupção'),
                    ('COMPARAR','Diferenças entre trabalhos'),('AGRUPADOS','Corredores agrupados')]:
            self.categoria.addItem(n,k)
        self.categoria.currentIndexChanged.connect(self.mudar_categoria)
        v.addWidget(self.categoria)
        self.montar_resultados_macro(v)
        self.filtro=QLineEdit();self.filtro.setPlaceholderText('Filtrar por ID, zona, origem ou situação')
        self.filtro.editingFinished.connect(self.atualizar_tabela);v.addWidget(self.filtro)
        self.tabela=TabelaGIS();self.tabela.setMinimumHeight(145);self.tabela.setMaximumHeight(280);v.addWidget(self.tabela)
        self.tabela.currentCellChanged.connect(self.detalhar)
        self.tabela.horizontalHeader().sectionClicked.connect(self.ordenar)
        navegar_registros(self.tabela,self.localizar_linha,self.menu_linha,self.limpar_macro_mapa)
        nav=QHBoxLayout();v.addLayout(nav)
        self.ant=botao(nav,'‹ Anterior',lambda:self.paginar(-1))
        self.pagina_info=aviso();nav.addWidget(self.pagina_info,1)
        self.prox=botao(nav,'Próxima ›',lambda:self.paginar(1))
        self.detalhe=aviso();v.addWidget(self.detalhe)
        self.ensaio_b,ens=expansivel(v,'Testar interrupção topológica')
        self.selecao_corte=aviso('Escolha as tubulações que ficarão indisponíveis.');ens.addWidget(self.selecao_corte)
        botao(ens,'Escolher tubulações no mapa',lambda:self.selecionar_mapa(interrupcao=True))
        botao(ens,'Limpar tubulações escolhidas',self.limpar_retiradas)
        self.testar_b=botao(ens,'Simular retirada',self.testar)
        self.salvar_teste_b=botao(ens,'Salvar resultado da interrupção',self.salvar_teste)
        self.resumo_teste=aviso();ens.addWidget(self.resumo_teste)
        _,exp=expansivel(v,'Exportações')
        self.exportar_gpkg_b=botao(exp,'GeoPackage e tabelas…',lambda:self.exportar('GPKG'))
        self.exportar_shp_b=botao(exp,'Shapefile e tabelas…',lambda:self.exportar('ESRI Shapefile'))
        self.atualizar_tabela()

    def _projeto(self):
        return self.central.projetos.atual()

    def _com_erro(self,fn):
        try:return fn()
        except (ValueError,OSError,RuntimeError,sqlite3.Error) as e:self.status.setText(str(e))

    def tarefa(self,nome,operacao,pronto):
        if self.central.ocupado():return
        self.status.setText(nome+' · acompanhe em Janelas.')
        return self.app.atividades.executar_thread(nome,self._projeto()['nome'],operacao,pronto,self.status.setText)

    def abrir(self,foto=None):
        p=self._projeto()
        if self.projeto_uid!=p['uuid']:
            self.cancelar_captura()
            self.projeto_uid=p['uuid'];self.foto=None;self.dados=None;self.interrupcao=None
            self._destinos.clear();self._indice.clear()
            self._retiradas.clear();self._associacoes.clear();self.diferencas=[]
            self.carregar_macro(None)
            self.identidade.clear();self.resumo.clear();self.origens.clear();self.areas.clear()
            self.mostrar_destinos();self.atualizar_tabela()
        self.listar_execucoes()
        if foto is not None and (self.foto or {}).get('uuid')!=foto['uuid']:
            self.carregar_foto(foto)
        elif self.foto is not None:self.descrever_foto()
        elif self.execucoes.count()>1:self.status.setText('Escolha uma execução topológica persistida.')
        else:self.status.setText('Execute e salve uma análise em Analisar conectividade para começar.')

    def listar_execucoes(self):
        regs={r['uuid']:r for r in self.central._registros if r['tipo']=='TOPOLOGIA_GIS'}
        atual=(self.foto or {}).get('uuid')
        self.execucoes.clear()
        self.execucoes.addItem('Selecionar…',None)
        for r in reversed(self._projeto()['bases']):
            if r['tipo']!='TOPOLOGIA_GIS':continue
            nome=regs.get(r['uuid'],{}).get('nome',r.get('nome',Path(r['base']).stem))
            self.execucoes.addItem(f"{nome} · {r['uuid'][:8]}",r)
            if atual==r['uuid']:self.execucoes.setCurrentIndex(self.execucoes.count()-1)

    def escolher_execucao(self,*_):
        r=self.execucoes.currentData()
        if not r or (self.foto or {}).get('uuid')==r['uuid']:return
        self.cancelar_captura()
        self.tarefa('Abrindo fotografia topológica',
                    lambda parar,_:pg.carregar(r['base'],r['uuid'],self.projeto_uid),self.carregar_foto)

    def carregar_foto(self,foto,manter_resultado=False):
        if foto['projeto_uid']!=self._projeto()['uuid']:raise ValueError('A execução pertence a outro projeto.')
        self.foto=foto;self._indice.clear()
        self._destinos={};self._associacoes={};self._retiradas=set()
        if not manter_resultado:
            self.dados=None;self.diferencas=[];self.interrupcao=None
            self.carregar_macro(None)
            self.resumo.clear();self.resumo_teste.clear()
        self.crs_foto=QgsCoordinateReferenceSystem(foto['crs'])
        self.originais={t['uid']:t for t in foto['tubos']}
        self.nos_foto={n['uid']:n for n in foto['nos']}
        self.pontos_parte={}
        for n in self.nos_foto.values():
            for u,pos in n['portas']:
                if u in self.originais:self.pontos_parte.setdefault(u,[]).append((pos,n['uid']))
        self.nomes={}
        validas=set(foto['origens_validas'])
        self.origens.clear()
        for r in foto['participantes']:
            u=r['uuid']
            if r['tipo']!='ORIGEM' or u not in validas:continue
            nome=r.get('nome') or r.get('categoria') or u[:10];self.nomes[u]=nome
            item=QListWidgetItem(nome+' · '+pg.SITUACOES.get(r['situacao'],r['situacao']))
            item.setData(Qt.UserRole,u);item.setCheckState(Qt.Checked);self.origens.addItem(item)
        self.areas.clear();self.areas.addItem('Escolher área…',None)
        self.areas_foto={a['uid']:a for a in foto.get('areas',[])}
        for a in self.areas_foto.values():self.areas.addItem(str(a.get('label') or a.get('id') or a['uid'][:10]),a['uid'])
        self.selecao_corte.setText('Escolha as tubulações que ficarão indisponíveis.')
        self.mostrar_destinos()
        if not manter_resultado:self.atualizar_tabela()
        self.listar_execucoes();self.descrever_foto()
        self.status.setText('Fotografia topológica aberta.')

    def descrever_foto(self):
        d=self.foto
        p=self._projeto()
        modelo=next(reversed(revisoes(p)),{})
        atual={f['uid']:f for f in modelo.get('fontes',[])}
        alertas=[]
        if d.get('modelo_rev')!=modelo.get('uuid'):
            alertas.append('Modelo GIS em outra revisão. Gere nova topologia para analisar a configuração atual.')
        mapa=self.central.modelo_gis.camadas()
        for f in d.get('fontes',[]):
            anterior=atual.get(f['uid'])
            if anterior is None:continue
            camada=identificar(anterior,mapa)
            if camada is None or camada.isModified() or descrever(camada)['assinatura']!=f['assinatura']:
                alertas.append('Uma fonte está indisponível ou alterada. Esta fotografia continua consultável.')
                break
        hip=d.get('hipotese') or {}
        ht=(hip.get('nome','')+' · revisão '+hip.get('rev','')[:8]) if hip else 'Configuração temporária registrada'
        self.identidade.setText(f"{p['nome']} · {d['nome']} · {d['uuid'][:8]}\n{ht}\n"+
                                ' '.join(alertas or ['Análise sobre a fotografia salva. Alterações de feições exigem nova execução.']))

    def conferir_fontes(self):
        if not self.foto or self.central.ocupado():return
        from qgis.core import QgsProject
        from .entradas_grafo_gis import ler, preparar
        from .hipoteses_gis import assinatura_inventario
        foto=self.foto
        modelos=revisoes(self._projeto())
        modelo=next((r for r in modelos if r['uuid']==foto.get('modelo_rev')),None)
        assinatura=foto.get('assinatura_inventario')
        if not modelo or not assinatura:
            self.status.setText('Esta fotografia não possui a referência necessária à conferência de conteúdo.');return
        ids={f['uid'] for f in foto['fontes']}
        def conferir():
            prep=preparar([f for f in modelo['fontes'] if f['uid'] in ids],self.central.modelo_gis.camadas(),
                          foto['crs'],QgsProject.instance().transformContext(),unidades=foto.get('unidades'))
            def pronto(ok):
                self.status.setText('Conteúdo das fontes corresponde à fotografia.'
                                    if ok else 'Conteúdo das fontes mudou. Gere nova execução para analisar os dados atuais.')
            self.tarefa('Conferindo conteúdo das fontes',
                        lambda p,e:assinatura_inventario(ler(prep,p,e))==assinatura,pronto)
        self._com_erro(conferir)

    def fontes_marcadas(self):
        return [i.data(Qt.UserRole) for i in (self.origens.item(n) for n in range(self.origens.count()))
                if i.checkState()==Qt.Checked]

    def _complementos(self,criar=False):
        return self.central._pagina_conectividade()._base_complementos(criar)

    def adicionar_destino(self,tipo,ref,no=None):
        if self.foto is None:return
        if tipo=='PIPE':
            t=self.originais[ref];nome=str(t.get('label') or t.get('id') or ref[:10])
        else:nome='Nó '+ref[:10]
        d=motor.novo_destino(tipo,ref,no=no,nome=nome)
        self._destinos[d['uid']]=d
        self.mostrar_destinos()

    def mostrar_destinos(self):
        self.modelo_destinos.substituir(self._destinos.values())

    def _nome_area(self,u):
        a=self.areas_foto.get(u,{})
        return str(a.get('label') or a.get('id') or u[:8])

    def remover_destinos(self):
        for i in self.lista_destinos.selectedIndexes():
            self._destinos.pop(i.data(Qt.UserRole),None)
        self.mostrar_destinos()

    def limpar_destinos(self):
        self._destinos.clear();self._associacoes.clear();self.mostrar_destinos()

    def adicionar_area(self):
        zona=self.areas.currentData()
        if not zona or not self.foto:
            self.status.setText('Escolha uma área cadastrada da execução selecionada.');return
        novos=0
        for t in self.foto['tubos']:
            if zona in t.get('zonas_uids',()):
                d=motor.novo_destino('PIPE',t['uid'],zona=zona,modo='ESPACIAL',
                                    nome=str(t.get('label') or t.get('id') or t['uid'][:8]))
                if d['uid'] not in self._destinos:
                    novos+=1;self._destinos[d['uid']]=d
        self.mostrar_destinos()
        self.status.setText(f'{novos} destinos por interseção espacial. Confirme explicitamente os pontos de alimentação para avaliar redes de passagem.')

    def associar(self):
        zona=self.areas.currentData()
        selecao=[i.data(Qt.UserRole) for i in self.lista_destinos.selectedIndexes()]
        if not zona or not selecao:
            self.status.setText('Escolha uma área e selecione na lista os destinos que deseja declarar.');return
        def salvar():
            base=self._complementos(True)
            ds=[motor.novo_destino(d['tipo'],d['ref'],no=d['no'],zona=zona,nome=d['nome'])
                for u in selecao for d in [self._destinos[u]]]
            rs=[r for r in pg.vigentes(base,self.projeto_uid).values()
                if r['tipo']=='DESTINO_ZONA' and r['topologia_uid']==self.foto['uuid'] and r['zona']==zona]
            ant=rs[0] if rs else {}
            rev=pg.salvar_revisao(base,self.projeto_uid,'DESTINO_ZONA',
                dict(topologia_uid=self.foto['uuid'],zona=zona,destinos=ds),
                ant.get('uuid'),ant.get('rev'))
            for u in selecao:self._destinos.pop(u)
            self._carregar_associacao(rev)
            self.status.setText('Associação de destinos registrada como revisão '+rev['rev'][:8]+'.')
        self._com_erro(salvar)

    def _carregar_associacao(self,r):
        old=self._associacoes.get(r['zona'],{})
        for d in old.get('destinos',[]):self._destinos.pop(d['uid'],None)
        self._associacoes[r['zona']]=r
        self._destinos.update({d['uid']:d for d in r['destinos']})
        self.mostrar_destinos()

    def recuperar_associacao(self):
        zona=self.areas.currentData()
        if not zona or not self.foto:
            self.status.setText('Escolha uma área da execução.');return
        def buscar():
            rs=[r for r in pg.revisoes(self._complementos(),self.projeto_uid)
                if r['tipo']=='DESTINO_ZONA' and r['zona']==zona and r['topologia_uid']==self.foto['uuid']]
            if not rs:
                self.status.setText('Nenhuma associação salva nesta área e execução.');return
            rotulos=[r['data_utc'][:19]+' · '+r['rev'][:8] for r in reversed(rs)]
            nome,ok=QInputDialog.getItem(self,'Destinos versionados','Revisão',rotulos,editable=False)
            if ok:self._carregar_associacao(list(reversed(rs))[rotulos.index(nome)])
        self._com_erro(buscar)

    def selecionar_mapa(self,interrupcao=False):
        if not self.foto or self.central.ocupado() or (interrupcao and not self.dados):
            self.status.setText('Abra uma execução antes de selecionar elementos.');return
        tipo='PIPE' if interrupcao else self.selecao_tipo.currentData()
        alvos=self.originais if tipo=='PIPE' else self.nos_foto
        anteriores=dict(self._destinos);retiradas=set(self._retiradas)
        def iniciar(indice):
            self._indice[tipo]=indice
            def cancelar():
                self._destinos=anteriores;self._retiradas=retiradas
                self.mostrar_destinos();self.atualizar_retiradas()
            def clique(p,sair):
                g,tol=self._clique_metricas(p,self.crs_foto)
                hit=escolher(self,indice.consultar(g,tol),lambda x:str(x[2].get('id') or x[1][:10])+' · '+x[2].get('camada','Nó'))
                if not hit:return
                _,uid,r,geom=hit
                if interrupcao:
                    f=r.get('feicao',uid)
                    self._retiradas.add(f);self.atualizar_retiradas()
                else:
                    no=None
                    if tipo=='PIPE':
                        pos=fracao_clicada(geom,g,tol)
                        no=min(self.pontos_parte[uid],key=lambda x:(abs(x[0]-pos),x[0],x[1]))[1]
                    self.adicionar_destino(tipo,uid,no)
            if self.iniciar_ferramenta(clique,cancelar=cancelar):
                self._mensagem_captura('Clique para acrescentar elementos. Botão direito conclui. Esc cancela.')
        if tipo in self._indice:iniciar(self._indice[tipo]);return
        def indexar(parar,etapa):
            if tipo=='NO':
                return IndiceSelecao((dict(n,geom=_ponto(n['xy'])) for n in alvos.values()),parar)
            return IndiceSelecao(alvos.values(),parar)
        worker=self.tarefa('Indexando elementos GIS',indexar,lambda i:self._indice.__setitem__(tipo,i))
        if worker:
            operacao=self.app.atividades.atual
            worker.finished.connect(lambda:iniciar(self._indice[tipo]) if operacao.estado=='CONCLUIDO' and tipo in self._indice else None)

    def _destino_destaque(self,d):
        if d['tipo']=='NO' or d.get('no'):
            n=self.nos_foto.get(d.get('no') or d['ref'])
            return _ponto(n['xy']) if n else None
        from .investigacao_gis import geometria
        return geometria(self.originais.get(d['ref'],{}).get('wkb'))

    def selecionar_area_mapa(self):
        if not self.foto or not self.areas_foto or self.central.ocupado():
            self.status.setText('Abra uma execução com áreas cadastradas.')
            return
        if 'AREAS' not in self._indice:
            self._indice['AREAS']=IndiceSelecao(self.areas_foto.values())
        indice=self._indice['AREAS']
        def clique(p,sair):
            g,tol=self._clique_metricas(p,self.crs_foto)
            hit=escolher(self,indice.consultar(g,tol),lambda r:self._nome_area(r[1]))
            if hit:
                self.areas.setCurrentIndex(self.areas.findData(hit[1]))
                sair(True)
                self.status.setText('Área escolhida. Adicione destinos por interseção ou vincule os destinos selecionados.')
        if self.iniciar_ferramenta(clique):
            self._mensagem_captura('Clique em uma área cadastrada. Esc cancela.')

    def localizar_destino(self,indice,aproximar):
        d=self._destinos.get(indice.data(Qt.UserRole))
        if d:self._com_erro(lambda:self.central.mapa.destacar_investigacao(
            [('evento',self._destino_destaque(d))],self.crs_foto,aproximar,toda_extensao=True))

    def calcular(self,agrupado=False):
        if self.foto is None:
            self.status.setText('Abra uma execução de conectividade GIS.');return
        self.cancelar_captura(reabrir=False)
        foto=self.foto
        fontes=self.fontes_marcadas()
        ds=[d for d in self._destinos.values() if d['modo']!='AUTOMATICO']
        assocs=list(self._associacoes.values());nome=self.nome.text().strip() or 'Redes estruturantes'
        pasta=self._pasta_resultados()
        opcoes=self.configuracao_macro() if agrupado else None
        def trabalho(parar,etapa):
            d=motor.analisar(foto,fontes,ds,nome=nome,associacoes=assocs,cancelar=parar,etapa=etapa,
                             agrupamento=opcoes)
            return self._gravar(pasta,d,parar,etapa)
        self.tarefa('Analisando redes estruturantes',trabalho,self._registrar)

    def _pasta_resultados(self):
        p=self._projeto()
        return (Path(p['manifesto_wna']).parent if p.get('manifesto_wna') else
               self.app.catalogo.raiz/'estrutura_gis'/p['uuid'])/'resultados'

    @staticmethod
    def _gravar(pasta,d,parar,etapa):
        pasta.mkdir(parents=True,exist_ok=True)
        caminho=pasta/('estrutura_gis_'+d['uuid']+'.gpkg')
        etapa(0,'Gravando fotografia de investigação')
        pg.salvar_estrutura(caminho,d,parar)
        return caminho,d

    def _registrar(self,resultado):
        caminho,d=resultado
        if d['projeto_uid']!=self._projeto()['uuid']:raise ValueError('O projeto mudou. Resultado não vinculado.')
        r=self.app.catalogo.registrar(caminho)[0]
        self.central.projetos.vincular(r);self.central._catalogo_lido=None
        self.receber(d)

    def reabrir(self,r,cartografar=False,aproximar=False):
        from .contexto_trabalho import validar_registro
        def ler(parar,etapa):
            validacao=validar_registro(r)
            if not validacao['valido']:raise ValueError(validacao['erro'])
            return pg.carregar_estrutura(r['base'],r['uuid'],self.projeto_uid)
        worker=self.tarefa('Reabrindo investigação estrutural',
                          ler,self.receber)
        if cartografar and worker:
            operacao=self.app.atividades.atual
            worker.finished.connect(lambda:self.localizar_linha(self.tabela.currentIndex(),aproximar)
                                     if operacao.estado=='CONCLUIDO' and self.tabela.currentIndex().isValid() else None)
        return worker

    def receber(self,d):
        if d['projeto_uid']!=self._projeto()['uuid']:raise ValueError('A investigação pertence a outro projeto.')
        self.dados=d;self.interrupcao=d.get('interrupcao');self.diferencas=[]
        self.carregar_foto(d['foto'],manter_resultado=True)
        self.geo=GeometriasEstrutura(d)
        self._destinos_criticos={}
        for alvo in d['destinos']:
            for f in alvo['criticas']:
                self._destinos_criticos.setdefault(f,[]).append(alvo['nome'])
        self._destinos={r['uid']:r for r in d['destinos']}
        self._associacoes={r['zona']:r for r in d['associacoes']}
        self.mostrar_destinos()
        for i in range(self.origens.count()):
            item=self.origens.item(i);item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in d['fontes'] else Qt.Unchecked)
        self.nome.setText(d['nome'])
        self.carregar_macro(d)
        crit=sum('CRITICA' in t['funcoes'] for t in d['tubulacoes'])
        incid=sum(t['estado']=='INDETERMINADA_LIMITE' for t in d['tubulacoes'])
        self.resumo.setText(f"{len(d['tubulacoes'])} Pipes · {crit} ligações críticas · {len(d['rotas'])} trajetos · "
                            f"{d['pontes_segmentos']} segmentos-ponte · {len(d['articulacoes'])} articulações. "
                            f"{incid} cortes agrupados indeterminados por limite."
                            +(' Sem origens selecionadas. Consulte pontes e articulações; o alcance a fontes ficou indeterminado.'
                              if not d['fontes'] else ''))
        self.status.setText('Trabalho disponível no catálogo do projeto · '+d['uuid'][:8])
        if self.interrupcao:
            self._retiradas=set(self.interrupcao['retiradas'])
            self.atualizar_retiradas()
            self.mostrar_interrupcao(self.interrupcao)
        else:
            self.resumo_teste.clear()
            if self.macro:
                opcoes=self.macro.dados['parametros']
                self.modo_macro.setCurrentIndex(self.modo_macro.findData(opcoes['modo']))
                self.max_macro.setValue(opcoes['maximo']);self.dist_macro.setValue(opcoes['minimo_m'])
                self.categoria.setCurrentIndex(self.categoria.findData('AGRUPADOS'))
            elif not crit or self.categoria.currentData()=='AGRUPADOS':
                self.categoria.setCurrentIndex(self.categoria.findData('TUBOS'))
        self.atualizar_tabela()

    def limpar_retiradas(self):
        self._retiradas.clear();self.atualizar_retiradas()

    def atualizar_retiradas(self):
        self.selecao_corte.setText(f'{len(self._retiradas)} tubulação(ões) física(s) escolhida(s) para interrupção.')
        self._acoes()

    def incluir_corte(self,uid):
        self._retiradas.add(uid)
        self.ensaio_b.setChecked(True);self.atualizar_retiradas()
        self.ensureWidgetVisible(self.selecao_corte)

    def testar(self):
        if not self.dados or not self._retiradas:return
        d=self.dados;rs=set(self._retiradas)
        self.cancelar_captura()
        self.tarefa('Simulando interrupção topológica',lambda p,e:motor.testar_interrupcao(d,rs,p,e),self.mostrar_interrupcao)

    def mostrar_interrupcao(self,r):
        self.interrupcao=r
        self.resumo_teste.setText(f"{len(r['retiradas'])} Pipes retirados · {len(r['componentes'])} componentes · "
            f"{r['perda_m']:.2f} m e {r['afetadas']} Pipes remanescentes perderam acesso a todas as origens · "
            f"{r['destinos_afetados']} destinos perderam acesso · {r['destinos_retirados']} destinos retirados · "
            f"{len(r['rotas_intactas'])} trajetos intactos · {len(r.get('novas_rotas',{}))} rotas remanescentes detalhadas. "
            f"Fontes ligadas a trechos remanescentes: {self._nomes(r.get('fontes_remanescentes',[]))}."
            + (f" {r['rotas_omitidas']} rotas fora do limite de detalhamento." if r.get('rotas_omitidas') else ''))
        self.categoria.setCurrentIndex(self.categoria.findData('COMPONENTES'));self.atualizar_tabela()

    def salvar_teste(self):
        if self.dados and self.interrupcao:
            base=self.dados
            if base.get('interrupcao') is self.interrupcao:return
            novo=dict(base,uuid=uuid4().hex,interrupcao=self.interrupcao,referencia=base.get('referencia',base['uuid']),
                      nome=self.nome.text()+' · interrupção',data_utc=datetime.now(timezone.utc).isoformat())
            pasta=self._pasta_resultados()
            self.tarefa('Salvando teste de interrupção',lambda p,e:self._gravar(pasta,novo,p,e),self._registrar)

    def _comparaveis(self):
        return [r for r in (self._projeto() or {}).get('bases',[]) if r['tipo']=='ESTRUTURA_GIS'
                and (self.dados or {}).get('uuid')!=r['uuid']]

    def comparar(self):
        rs=self._comparaveis()
        if not self.dados or not rs:return
        registros={r['uuid']:r for r in self.central._registros if r['tipo']=='ESTRUTURA_GIS'}
        nomes=[registros.get(r['uuid'],{}).get('nome',r.get('nome',Path(r['base']).stem))+' · '+r['uuid'][:8] for r in rs]
        escolha,ok=QInputDialog.getItem(self,'Comparar trabalhos estruturais','Trabalho anterior',nomes,editable=False)
        if not ok:return
        r=rs[nomes.index(escolha)];d=self.dados
        def trabalho(parar,etapa):
            anterior=pg.carregar_estrutura(r['base'],r['uuid'],self.projeto_uid)
            return anterior,motor.comparar_estruturas(anterior,d)
        def pronto(resultado):
            anterior,self.diferencas=resultado
            self.anterior_geo=GeometriasEstrutura(anterior)
            self.categoria.setCurrentIndex(self.categoria.findData('COMPARAR'));self.atualizar_tabela()
            self.status.setText(f"Comparação de {anterior['nome']} com {d['nome']} · {len(self.diferencas)} mudanças.")
        self.tarefa('Comparando investigações estruturais',trabalho,pronto)

    def mostrar_camadas(self):
        if self.macro and self.categoria.currentData()=='AGRUPADOS':
            self.mostrar_macro()
        elif self.dados:
            self._com_erro(lambda:carregar_camadas(self.dados,self.geo))

    def exportar(self,formato):
        if not self.dados or self.central.ocupado():return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de exportação')
        if pasta:
            d=self.dados
            if self.interrupcao:d=dict(d,interrupcao=self.interrupcao)
            self.tarefa('Exportando investigação',lambda p,e:exportar(d,pasta,formato,p,e),
                         lambda caminho:self.status.setText('Exportado em '+str(caminho)))

    def _nomes(self,ids):
        return ', '.join(self.nomes.get(u,u[:8]) for u in ids) or '—'

    def dados_tabela(self):
        d=self.dados or {}
        c=self.categoria.currentData()
        if c=='AGRUPADOS':
            return self.tabela_corredores()
        if c in motor.CATEGORIAS or c in ('TUBOS','PONTES'):
            cab=('Pipe','Camada GIS','Função','Comprimento (m)','Diâmetro (mm)','Origens na rota','Destinos na rota',
                 'Perda de acesso (m)','Pipes afetados','Destinos afetados','Origens perdidas','Fontes remanescentes','Situação')
            rs=(r for r in d.get('tubulacoes',[]) if c=='TUBOS' or c in r['funcoes'] or c=='PONTES' and r['ponte'])
            valores=lambda r:(str(r['id'] if r['id'] is not None else r['uid'][:8]),r['camada'],
                ', '.join(motor.CATEGORIAS[f] for f in r['funcoes']),r['comprimento_m'],r['diametro_mm'],
                self._nomes(r['origens']),len(r['destinos']),r.get('perda_m'),r.get('afetadas'),r.get('destinos_afetados'),
                self._nomes(r.get('fontes_perdidas',[])),self._nomes(r.get('fontes_alternativas',[])),ESTADOS[r['estado']])
            return 'TUBOS',cab,rs,valores
        if c=='ROTAS':
            return c,('Origem','Destino','Comprimento (m)','Pipes','Alternativa','Alternativa (m)'),d.get('rotas',[]),lambda r:(
                self._nomes([r['origem']]),self.geo.destinos[r['destino']]['nome'],r['comprimento_m'],
                len(r['tubos']),ESTADOS[r['alternativa_estado']],r.get('alternativa',{}).get('comprimento_m'))
        if c=='ZONAS':
            return c,('Zona','Evidência','Origens','Destinos','Corredores','Pipes críticos','Redundância','Maior perda (m)','Situação'),d.get('zonas',[]),lambda r:(
                r['nome'],r['evidencia'],self._nomes(r['origens']),len(r['destinos']),len(r['rotas']),len(r['criticas']),
                r['alternativas'],r['maior_perda_m'],ESTADOS[r['estado']])
        if c=='DESTINOS':
            return c,('Destino','Área','Evidência','Origens','Distância pela rede (m)','Pipes críticos','Situação'),d.get('destinos',[]),lambda r:(
                r['nome'],self._nome_area(r['zona']) if r.get('zona') else '—',r['modo'],
                self._nomes(r['origens']),r.get('distancia_origem_m'),len(r['criticas']),ESTADOS[r['estado']])
        if c=='ARTICULACOES':
            return c,('Nó de articulação',),[dict(uid=u) for u in d.get('articulacoes',[])],lambda r:(r['uid'],)
        if c=='COMPONENTES':
            return c,('Componente','Pipes','Comprimento (m)','Origens','Acesso após retirada'),(
                dict(r,uid=str(i)) for i,r in enumerate((self.interrupcao or {}).get('componentes',[]),1)),lambda r:(
                    int(r['uid']),len(r['tubos']),r['comprimento_m'],self._nomes(r['origens']),'Perdeu acesso' if r['perdeu'] else 'Preservado ou já sem origem')
        if c=='INTERROMPIDOS':
            return c,('Destino','Fontes antes','Fontes depois','Situação'),(self.interrupcao or {}).get('destinos',[]),lambda r:(
                self.geo.destinos[r['uid']]['nome'],self._nomes(r['antes']),self._nomes(r['depois']),
                'Retirado' if r['direto'] else 'Perdeu acesso' if r['perdeu'] else 'Remanescente')
        if c=='REMANESCENTES':
            return 'ROTAS',('Origem','Destino','Comprimento (m)','Pipes'),(
                (self.interrupcao or {}).get('novas_rotas',{}).values()),lambda r:(
                    self._nomes([r['origem']]),self.geo.destinos[r['destino']]['nome'],r['comprimento_m'],len(r['tubos']))
        return 'COMPARAR',('Mudança','Referência','Antes','Depois'),self.diferencas,lambda r:(
            MUDANCAS.get(r['tipo'],r['tipo']),r['ref'],r['antes'],r['depois'])

    def _acoes(self):
        base='' if self.dados else 'Execute ou abra uma investigação estrutural.'
        acao_disponivel(self.executar_b,'' if self.foto else 'Selecione uma execução de conectividade GIS.')
        acao_disponivel(self.executar_macro_b,'' if self.foto else 'Selecione uma execução de conectividade GIS.')
        acao_disponivel(self.conferir_b,'' if self.foto else 'Selecione uma execução de conectividade GIS.')
        for b in (self.camadas_b,self.exportar_gpkg_b,self.exportar_shp_b):acao_disponivel(b,base)
        acao_disponivel(self.comparar_b,base or ('' if self._comparaveis() else 'Salve outra investigação estrutural no projeto.'))
        acao_disponivel(self.testar_b,base or ('' if self._retiradas else 'Escolha uma ou mais tubulações.'))
        acao_disponivel(self.salvar_teste_b,'' if self.interrupcao and (self.dados or {}).get('interrupcao') is not self.interrupcao
                        else 'Execute uma nova interrupção para salvar.')

    def mudar_categoria(self,*_):
        self._ordem=None;self.tabela.horizontalHeader().setSortIndicatorShown(False)
        self.atualizar_tabela()

    def ordenar(self,coluna):
        desc=not self._ordem[1] if self._ordem and self._ordem[0]==coluna else False
        self._ordem=(coluna,desc)
        h=self.tabela.horizontalHeader()
        h.setSortIndicator(coluna,Qt.DescendingOrder if desc else Qt.AscendingOrder);h.setSortIndicatorShown(True)
        self.atualizar_tabela()

    def atualizar_tabela(self):
        tipo,cab,rs,valores=self.dados_tabela()
        termo=self.filtro.text().strip().casefold()
        self._tipo_linha=tipo
        linhas=[(r,valores(r)) for r in rs]
        if termo:
            def contem(r,v):
                if termo in (' '.join(str(x) for x in v)+' '+r['uid']).casefold():return True
                return tipo=='AGRUPADOS' and any(termo in self.geo.destinos[u]['nome'].casefold()
                                                 for u in r['destinos'])
            linhas=[(r,v) for r,v in linhas if contem(r,v)]
        if self._ordem:
            coluna,desc=self._ordem
            def chave(x):
                v=x[1][coluna]
                return (0,v) if isinstance(v,(int,float)) else (1,str(v).casefold() if v is not None else '')
            linhas.sort(key=chave,reverse=desc)
        elif self.categoria.currentData()=='CRITICA':
            linhas.sort(key=lambda x:(-x[0]['perda_m'],-x[0]['destinos_afetados'],-x[0]['afetadas'],x[0]['uid']))
        self._linhas=linhas;self._pagina=0
        mudou=self.tabela._titulos!=cab
        self.tabela.colunas(cab);self.paginar(0);self._acoes()
        if mudou:
            for i in range(min(2,len(cab))):
                self.tabela.resizeColumnToContents(i)
                self.tabela.setColumnWidth(i,max(110,min(220,self.tabela.columnWidth(i))))

    def paginar(self,passo):
        total=max(1,(len(self._linhas)+PAGINA-1)//PAGINA)
        self._pagina=max(0,min(self._pagina+passo,total-1))
        ini=self._pagina*PAGINA
        self.tabela.blockSignals(True);self.tabela.limpar()
        for r,valores in self._linhas[ini:ini+PAGINA]:self.tabela.inserir(valores,r)
        self.tabela.blockSignals(False)
        self.pagina_info.setText(f'{self._pagina+1}/{total} · {len(self._linhas)} resultado(s)')
        acao_disponivel(self.ant,'Primeira página.' if self._pagina==0 else '')
        acao_disponivel(self.prox,'Última página.' if self._pagina+1==total else '')
        if self.tabela.rowCount():self.tabela.setCurrentCell(0,0)
        self.detalhar()

    def registro(self,indice=None):
        i=indice or self.tabela.currentIndex()
        item=self.tabela.item(i.row(),0) if i.isValid() else None
        return item.data(Qt.UserRole) if item else None

    def detalhar(self,*_):
        r=self.registro()
        if not r:
            vazio='Calcule um novo trabalho para gerar corredores agrupados nesta execução.'
            self.detalhe.setText(vazio if self._tipo_linha=='AGRUPADOS' and not self.macro else
                                'Nenhum resultado nesta categoria e filtro.');return
        if self._tipo_linha=='AGRUPADOS':
            texto=self.detalhe_corredor(r)
        elif self._tipo_linha=='TUBOS':
            texto=f"Pipe {r.get('id') or r['uid'][:8]} · {len(r['partes'])} parte(s) · "
            texto+=('segmento-ponte encontrado. ' if r['ponte'] else 'Sem segmento-ponte identificado. ')
            if r.get('travessias'):texto+='Travessias geométricas: '+', '.join(self._nome_area(u) for u in r['travessias'])+'. '
            if r.get('zonas_passagem'):texto+='Rotas para outra área cruzam '+', '.join(self._nome_area(u) for u in r['zonas_passagem'])+'. '
            afetados=self._destinos_criticos.get(r['uid'],[])
            if afetados:
                texto+='Destinos que perderiam todas as fontes: '+', '.join(afetados[:12])+('… ' if len(afetados)>12 else '. ')
            if r.get('destinos_afetados',0)>len(afetados):
                texto+='Consulte o teste de interrupção para identificar os demais destinos.'
        elif self._tipo_linha=='ROTAS':
            d=self.geo.destinos[r['destino']]
            texto='Pipes indispensáveis para esta origem: '+str(len(d['dependencias_fontes'].get(r['origem'],[])))+'. '
            if r.get('conexoes_no'):texto+='A rota passa por nó com relação declarada aplicada. Dependência isolada requer outra hipótese.'
        elif self._tipo_linha=='ZONAS':
            texto='Origens complementares ou hipotéticas alcançáveis: '+self._nomes(r['complementares'])+'. '
            texto+=f"{len(r.get('destinos_so_complementares',[]))} destinos acessíveis somente por essas origens. "
            texto+='Fontes exclusivas de algum destino: '+self._nomes(r.get('origens_exclusivas',[]))+'. '
            if r['conexoes_no']:texto+='Há conexões declaradas nos nós das rotas consideradas.'
        elif self._tipo_linha=='DESTINOS' and r.get('fontes_sem_rota_detalhada'):
            texto='Origens alcançáveis sem rota detalhada neste cálculo · '+self._nomes(r['fontes_sem_rota_detalhada'])+'.'
        else:
            texto='Duplo clique para aproximar os elementos com geometria disponível.'
        self.detalhe.setText(texto)

    def menu_linha(self,indice):
        r=self.registro(indice)
        if not r:return []
        if self._tipo_linha=='AGRUPADOS':
            return self.menu_corredor(r)
        if self._tipo_linha=='TUBOS':
            return [('Incluir Pipe no teste de interrupção',lambda:self.incluir_corte(r['uid'])),
                    ('Ver componentes ao retirar este Pipe',lambda:self.testar_pipe(r['uid']))]
        if self._tipo_linha=='ROTAS':
            acoes=[('Aproximar origem',lambda:self.localizar_linha(indice,True,'origem')),
                    ('Destacar alternativa',lambda:self.localizar_linha(indice,True,'alternativa'),
                     '' if r.get('alternativa') else 'Nenhuma alternativa foi registrada para esta rota.')]
            if self.macro:
                for papel in ('REFERENCIA','ALTERNATIVA'):
                    u=r['uid']+':'+papel
                    if u in self.macro.percursos:
                        titulo='Exportar percurso completo…' if papel=='REFERENCIA' else 'Exportar percurso alternativo…'
                        acoes.append((titulo,lambda u=u:self.exportar_macro('PERCURSO',u)))
            return acoes
        return []

    def testar_pipe(self,uid):
        self._retiradas={uid};self.ensaio_b.setChecked(True);self.atualizar_retiradas();self.testar()

    def _geometrias_diferenca(self,r):
        itens=[]
        for geo,papel in ((self.anterior_geo,'vinculo'),(self.geo,'tubo')):
            gs=[]
            for u in r.get('tubos',[]):
                if (g:=geo.tubo(u)):gs.append((papel,g))
            if r.get('zona') and (a:=geo.areas.get(r['zona'])):
                from .investigacao_gis import geometria
                gs.append(('local',geometria(a.get('wkb'))))
            if r.get('rota') and (rota:=geo.rotas.get(r['rota'])):
                gs.extend(geo.itens('ROTAS',rota))
            if r.get('destino') and (d:=geo.destinos.get(r['destino'])):
                gs.extend(geo.itens('DESTINOS',d))
            if v:=geo.referencia(geo.origens.get(r.get('origem')) or geo.conexoes.get(r.get('conexao'))):
                gs.append(('equipamento',v))
            itens.extend((p,_transformar(g,geo.crs,self.geo.crs)) for p,g in gs if g and not g.isEmpty())
        return itens

    def localizar_linha(self,indice,aproximar,opcao=None):
        r=self.registro(indice)
        if not r or not self.dados or self.central.ocupado():return
        if self._tipo_linha=='AGRUPADOS':
            return self.localizar_macro('CORREDOR',r['uid'],aproximar)
        self.restaurar_opacidade_macro()
        def mostrar():
            tipo=self._tipo_linha
            if tipo=='COMPARAR':itens=self._geometrias_diferenca(r)
            elif tipo=='INTERROMPIDOS':
                itens=self.geo.itens('DESTINOS',self.geo.destinos[r['uid']])
            else:itens=self.geo.itens(tipo,r,opcao)
            if not self.central.mapa.destacar_investigacao(itens,self.geo.crs,aproximar,toda_extensao=True):
                self.status.setText('A geometria deste resultado está indisponível.')
        self._com_erro(mostrar)
