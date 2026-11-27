"""Catálogo dos elementos materializados e preparação de Selection Sets."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
    QInputDialog, QLineEdit, QMessageBox, QVBoxLayout)
from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY

from auditoria_fronteiras.entradas import valor_python
from auditoria_fronteiras.modelos import verificar_cancelamento
from . import cadastro_exportavel as cadastro
from . import conjuntos_modelagem as cm
from . import persistencia_grafo_gis as pg
from .entradas_grafo_gis import marca_feicao
from .modelo_gis import identificar, revisoes
from .modelo_gis_ui import aviso, botao, formulario
from .navegacao_cartografica import navegar_registros
from .seletor_multiplos import escolher, opcoes_corredores
from .tabelas_topologia_gis import TabelaGIS


class CatalogoConjuntos(QDialog):
    def __init__(self,pagina,previa,estado,preselecao=None,parent=None):
        super().__init__(parent or pagina)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Conjuntos para WaterGEMS')
        self.resize(870,520)
        self.pagina,self.previa,self.estado=pagina,previa,estado
        self.foto=pagina.foto
        self.projeto=pagina._projeto()
        self.por_id=cm.indice(previa)
        self.registros={}
        self.resultados={}
        self.preselecao=preselecao
        v=QVBoxLayout(self)
        v.addWidget(aviso(f"Seleções de Pipes e Junctions para a exportação GIS · execução {self.foto['uuid'][:8]}."))
        self.filtro=QLineEdit()
        self.filtro.setPlaceholderText('Pesquisar nome, categoria ou subpasta')
        v.addWidget(self.filtro)
        self.arquivados=QCheckBox('Mostrar conjuntos arquivados')
        v.addWidget(self.arquivados)
        self.tabela=TabelaGIS()
        self.tabela.setObjectName('catalogo_conjuntos_wg')
        self.tabela.colunas(('Nome','Categoria / pasta','Pipes','Junctions','Outros','Hipótese','Revisão','Situação'))
        for i,largura in enumerate((220,142,60,75,58,117,82)):
            self.tabela.setColumnWidth(i,largura)
        v.addWidget(self.tabela)
        self.detalhe=aviso()
        v.addWidget(self.detalhe)
        botao(v,'Criar conjunto…',lambda:self.editar())
        botao(v,'Preparar Selection Sets para WaterGEMS…',self.exportar_todos)
        botao(v,'Exportar cadastro completo com conjuntos…',lambda:self.exportar_todos(completo=True))
        botao(v,'Fechar',self.reject)
        self.filtro.textChanged.connect(self.preencher)
        self.arquivados.toggled.connect(self.preencher)
        self.tabela.currentCellChanged.connect(self.detalhar)
        navegar_registros(self.tabela,self.localizar,self.menu,pagina.central.mapa.limpar)
        self._carregar()

    def _base(self,criar=False):
        if self.pagina._projeto()['uuid']!=self.projeto['uuid'] or self.pagina.foto is not self.foto:
            raise ValueError('O projeto ou a execução mudou. Reabra o catálogo.')
        return self.pagina._complementos(criar)

    def _carregar(self,uid=None):
        base=self._base()
        registros=pg.revisoes(base,self.projeto['uuid'],tipo='CONJUNTO_WG') if base else []
        self.registros={r['uuid']:r for r in registros}
        self.resultados={u:cm.reconciliar(r,self.previa,self.por_id) for u,r in self.registros.items()}
        self.preencher()
        if uid:
            for i in range(self.tabela.rowCount()):
                if self.tabela.item(i,0).data(Qt.UserRole)==uid:self.tabela.selectRow(i)

    def preencher(self,*_):
        termo=self.filtro.text().strip().casefold()
        self.tabela.setSortingEnabled(False)
        self.tabela.limpar()
        for u,r in sorted(self.registros.items(),key=lambda x:(x[1]['categoria'],x[1]['nome'].casefold(),x[0])):
            pasta=' / '.join(p for p in (r['categoria'],r.get('subpasta')) if p)
            if (r.get('arquivado') and not self.arquivados.isChecked()) or termo not in (pasta+' '+r['nome']).casefold():
                continue
            c=Counter(e['tipo'] for e in r['membros'])
            situacao='Arquivado' if r.get('arquivado') else (
                'Disponível para preparação' if self.resultados[u]['compativel'] else 'Requer conferência nesta execução')
            self.tabela.inserir((r['nome'],pasta,c['PIPE'],c['JUNCTION'],0,r.get('hipotese_nome') or 'Temporária',
                                 (r.get('hipotese_rev') or r['rev'])[:8],situacao),u)
        self.tabela.setSortingEnabled(True)
        self.detalhar()

    def _registro(self,i=None):
        linha=i.row() if i is not None else self.tabela.currentRow()
        item=self.tabela.item(linha,0)
        return self.registros.get(item.data(Qt.UserRole)) if item else None

    def detalhar(self,*_):
        r=self._registro()
        if not r:
            self.detalhe.setText('Selecione um conjunto para consultar sua composição e opções.')
            return
        c=self.resultados[r['uuid']]
        origem={'AUTOMATICA':'composição automática','MANUAL':'composição manual'}[r['origem']]
        self.detalhe.setText(f"{r['nome']} · {r['uuid'][:12]} · {origem} · "
            f"execução {r['topologia_uid'][:8]} · revisão {r['rev'][:8]}.\n"
            f"{len(c['preservados'])} membros correspondentes · {len(c['divididos'])} divisões verificáveis · "
            f"{len(c['novos'])} novos segmentos identificados · "
            f"{len(c['ausentes'])} ausentes · {len(c['ambiguos'])} ambíguos. "+r.get('descricao',''))

    def menu(self,i):
        r=self._registro(i)
        if not r:return []
        motivos='' if self.resultados[r['uuid']]['compativel'] else 'A composição precisa ser conferida nesta execução.'
        return [
            ('Consultar membros…',lambda:self.consultar(r)),
            ('Editar nome e classificação…',lambda:self.editar(r,metadados=True)),
            ('Editar composição / conferir a nova execução…',lambda:self.editar(r)),
            ('Histórico de revisões…',lambda:self.historico(r)),
            ('Recuperar conjunto' if r.get('arquivado') else 'Arquivar conjunto',lambda:self.arquivar(r)),
            ('Exportar conjunto…',lambda:self.exportar([r]),'Conjunto arquivado.' if r.get('arquivado') else motivos),
        ]

    def consultar(self,r):
        janela=QDialog(self)
        janela.setWindowTitle('Membros de '+r['nome'])
        v=QVBoxLayout(janela)
        tabela=TabelaGIS()
        tabela.colunas(('Tipo','WNA_UID','Pipe original','Parte','Início','Fim','Correspondência'))
        c=self.resultados[r['uuid']]
        ok=set(c['preservados'])
        div=dict(c['divididos'])
        for e in r['membros'][:500]:
            u=e['uid']
            estado='Correspondente' if (e['tipo'],u) in ok else (
                'Divisão verificável: '+', '.join(div[u]) if u in div else 'Sem correspondência exata')
            tabela.inserir((e['tipo'],u,e.get('original'),e.get('parte'),e.get('inicio'),e.get('fim'),estado))
        v.addWidget(aviso(f"{len(r['membros'])} membros · prévia de até 500 registros. O pacote inclui a composição completa."))
        v.addWidget(tabela)
        botao(v,'Fechar',janela.reject)
        janela.resize(850,480)
        janela.exec()

    def historico(self,r):
        def mostrar():
            historico=pg.revisoes(self._base(),self.projeto['uuid'],r['uuid'])
            texto='\n'.join(f"{x['data_utc']} · {x['rev'][:8]} · {x['nome']} · {len(x['membros'])} membros"
                            +(' · arquivado' if x.get('arquivado') else '') for x in reversed(historico))
            QMessageBox.information(self,'Histórico do conjunto',texto)
        self.pagina._com_erro(mostrar)

    def _gravar(self,d,r=None):
        r=r or {}
        d.setdefault('data_criacao',datetime.now(timezone.utc).isoformat())
        base=self._base(True)
        if not r:
            atuais={x['uuid']:x for x in pg.revisoes(base,self.projeto['uuid'],tipo='CONJUNTO_WG')}
            if any(not x.get('arquivado') and x['nome']==d['nome'] and x['categoria']==d['categoria']
                   and x.get('subpasta')==d.get('subpasta') and x['topologia_uid']==d['topologia_uid']
                   and x['membros']==d['membros'] for x in atuais.values()):
                raise ValueError('Já existe um conjunto com a mesma identificação e composição nesta execução.')
        novo=pg.salvar_revisao(base,self.projeto['uuid'],'CONJUNTO_WG',d,r.get('uuid'),r.get('rev'))
        self._carregar(novo['uuid'])
        return novo

    def arquivar(self,r):
        self.pagina._com_erro(lambda:self._gravar(dict(r,arquivado=not r.get('arquivado')),r))

    def localizar(self,i,aproximar):
        r=self._registro(i)
        if not r or self.pagina.central.ocupado():return
        crs=self.pagina.crs_foto
        itens=[self.por_id[k] for k in self.resultados[r['uuid']]['preservados']]
        if not itens:
            self.detalhe.setText('Abra a execução original para localizar a composição histórica.')
            return
        def preparar(parar,_):
            geos,pontos=[],[]
            for e in itens:
                verificar_cancelamento(parar)
                if 'wkb' in e:
                    g=QgsGeometry()
                    g.fromWkb(e['wkb'])
                    if not g.isEmpty():geos.append(g)
                else:
                    pontos.append(QgsPointXY(*e['xy']))
            return ([('tubo',QgsGeometry.collectGeometry(geos))] if geos else [])+(
                [('local',QgsGeometry.fromMultiPointXY(pontos))] if pontos else [])
        def mostrar(g):
            if self.pagina.foto is self.foto:
                self.pagina.central.mapa.destacar_investigacao(g,crs,aproximar,toda_extensao=True)
        self.pagina._tarefa_cartografica('Preparando destaque do conjunto',preparar,mostrar)

    def _grupos(self):
        p=self.pagina
        macro=p.macro_integral or {}
        dados=p.dados or {}
        return {
            'Corredores':[(r,'CORREDORES') for r in (*macro.get('corredores',()),*dados.get('agrupamento',{}).get('corredores',()))],
            'Blocos':[(r,'BLOCOS') for r in (*macro.get('blocos',()),*macro.get('detalhados',()),
                                           *dados.get('blocos',{}).get('blocos',()))],
        }

    def _mapa(self):
        # A impressão digital do cadastro inclui a fonte, a geometria e todos os atributos.
        por_marca=defaultdict(set)
        por_original=defaultdict(set)
        for t,u in self.por_id:
            if t=='PIPE':
                ori=self.por_id[t,u]['original']
                por_original[ori].add((t,u))
                por_marca[ori.split('_')[0]].add(ori)
        junctions=self._junctions_cadastrais
        for r in self.previa['cadastro']:
            if r['categoria']=='JUNCTION':
                por_marca[r['feicao'].split('_')[0]].add(r['feicao'])
                por_original[r['feicao']].update(junctions.get(r['uid'],()))
        camadas=self.pagina.central.modelo_gis.camadas()
        fontes=next(reversed(revisoes(self.projeto)),{}).get('fontes',())
        ids=set()
        for fonte in fontes:
            if fonte['categoria'] not in ('PIPE','JUNCTION'):continue
            c=identificar(fonte,camadas)
            if not c or not c.selectedFeatureCount():continue
            req=QgsFeatureRequest().setFilterFids(c.selectedFeatureIds())
            for f in c.getFeatures(req):
                a={campo.name():valor_python(f[campo.name()]) for campo in c.fields()}
                marca=marca_feicao(fonte['origem_estavel'],a,f.geometry())
                originais=por_marca.get(marca,())
                if len(originais)>1:
                    raise ValueError('A seleção inclui feições idênticas da mesma fonte. Selecione os membros materializados.')
                for u in originais:ids.update(por_original[u])
        return ids

    @property
    def _junctions_cadastrais(self):
        por_uid=defaultdict(set)
        for n in self.previa['nos']:
            for tipo,u in n['portas']:
                if tipo=='J':por_uid[u].add(('JUNCTION',n['uid']))
        return por_uid

    def _origem_composicao(self):
        linhas=self._grupos()
        opcoes=[*linhas,'Intervenções','Conexões confirmadas','Origem de água','Setor ou zona',
                'Pipes divididos','Pipes isolados','Pipes sem origem','Pipes inativos','Seleção atual do mapa',
                'Filtro de atributo','Escolher elementos materializados']
        modo,ok=QInputDialog.getItem(self,'Composição do conjunto','Obter elementos de',opcoes,0,False)
        if not ok:return None
        if modo in linhas:
            grupos={r['uid']:r for r,_ in linhas[modo]}
            opcoes=(opcoes_corredores(list(grupos.values())) if modo=='Corredores' else
                    [(u,r.get('nome') or 'Bloco detalhado · '+u[:10]) for u,r in grupos.items()])
            ids=escolher(self,modo,opcoes)
            if ids is None:return None
            chaves=cm.por_segmentos(self.foto,{i for u in ids for i in grupos[u]['segmentos']})
            return chaves,linhas[modo][0][1] if ids else 'PERSONALIZADOS',dict(modo=modo,referencias=ids)
        if modo=='Conexões confirmadas':
            op={f"{r.get('nome') or 'Conexão'} · {r['uuid'][:10]}":r['uuid'] for r in self.previa['operacoes']
                if r['tipo']=='CONEXAO' and r.get('resultado')=='APLICADA'}
            if not op:raise ValueError('A execução não tem conexões confirmadas e aplicadas.')
            n,ok=QInputDialog.getItem(self,modo,'Conexão',list(op),0,False)
            return (cm.da_conexao(self.previa,op[n]),'TOPOLOGIA',dict(modo=modo,conexao=op[n])) if ok else None
        if modo=='Origem de água':
            m=self.pagina.macro_integral or {}
            componentes=m.get('componentes',())
            origens={u for c in componentes for u in c['origens']}
            if not origens:raise ValueError('Calcule a visão macro integral com fontes habilitadas.')
            ids=escolher(self,modo,[(u,f"{self.pagina._nomes([u])} · {u[:10]}") for u in sorted(origens)])
            if ids is None:return None
            selecionadas=set(ids)
            segs={i for i,c in enumerate(m['componente_segmento']) if selecionadas.intersection(componentes[c]['origens'])}
            return cm.por_segmentos(self.foto,segs),'ORIGENS',dict(modo=modo,origem=ids[0] if len(ids)==1 else None,origens=ids)
        if modo=='Setor ou zona':
            nomes=[(a['uid'],f"{a.get('label') or a.get('id') or 'Área'} · {a['uid'][:10]}")
                   for a in self.foto.get('areas',())]
            if not nomes:raise ValueError('A execução não contém setores ou zonas cadastrados.')
            ids=escolher(self,'Áreas em interseção espacial',nomes)
            if ids is None:return None
            selecionadas=set(ids)
            partes={r['uid'] for r in self.foto['tubos'] if selecionadas.intersection(r.get('zonas_uids',()))}
            return {('PIPE',p['uid']) for p in self.previa['pipes'] if p['parte'] in partes},'AREAS',dict(
                modo=modo,area=ids[0] if len(ids)==1 else None,areas=ids)
        if modo=='Intervenções':
            propostas={r['uuid']:r for r in self.previa['operacoes'] if r['tipo']=='PIPE'}
            ids=self.pagina._escolher_itens_integral(modo,[(u,r.get('nome') or u[:10]) for u,r in propostas.items()])
            return {('PIPE',p['uid']) for p in self.previa['pipes'] if p.get('proposta') in ids},'INTERVENCOES',dict(modo=modo,referencias=ids)
        if modo=='Seleção atual do mapa':
            return self._mapa(),'PERSONALIZADOS',dict(modo=modo)
        if modo=='Escolher elementos materializados':
            return self._escolher_membros(set()),'PERSONALIZADOS',dict(modo=modo)
        if modo=='Filtro de atributo':
            campos=['gis_id','label','camada','material','diametro_mm','procedencia','situacao','atividade','condicao_topologica']
            campo,ok=QInputDialog.getItem(self,modo,'Campo da prévia',campos,0,False)
            if not ok:return None
            valor,ok=QInputDialog.getText(self,modo,'Valor exato')
            if not ok:return None
            chaves=cm.selecionar(self.previa,self.por_id,atributo=(campo,valor))
            return chaves,'PERSONALIZADOS',dict(modo=modo,campo=campo,valor=valor)
        regras={'Pipes divididos':('natureza','DIVISAO_VIRTUAL'),'Pipes inativos':('atividade','INATIVO'),
                'Pipes sem origem':('condicao_topologica','SEM_ORIGEM')}
        if modo=='Pipes isolados':
            chaves={('PIPE',r['uid']) for r in self.previa['pipes'] if 'ISOLADO' in r.get('componente',())}
        else:
            chaves=cm.selecionar(self.previa,self.por_id,tipo='PIPE',atributo=regras[modo])
        return chaves,'ATIVIDADE' if modo=='Pipes inativos' else 'TOPOLOGIA',dict(modo=modo)

    def _escolher_membros(self,ids):
        opcoes=[(k,f"{r.get('gis_id') or '—'} · {r.get('label') or '—'} · {r.get('camada') or ''} · {k[1]}",k[0])
                for k,r in self.por_id.items()]
        escolhidos=escolher(self,'Editar membros materializados',opcoes,ids)
        return set(escolhidos) if escolhidos is not None else None

    def editar(self,r=None,*,metadados=False):
        def editar():
            origem='MANUAL'
            if r:
                cat,criterio=r['categoria'],r.get('criterio',{})
                c=self.resultados[r['uuid']]
                ids=set(c['preservados'])
                if not metadados:
                    if not c['compativel']:
                        botao=QMessageBox.question(self,'Verificar composição em nova execução',
                            f"{len(c['preservados'])} membros correspondem e {len(c['divididos'])} Pipes têm divisões verificáveis. "
                            f"{len(c['ausentes'])} ausentes e {len(c['ambiguos'])} ambíguos exigem revisão. "
                            "Abrir uma nova composição com as correspondências verificáveis?",
                            QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
                        if botao!=QMessageBox.Yes:return
                        ids.update(('PIPE',u) for _,us in c['divididos'] for u in us)
                    ids=self._escolher_membros(ids)
                    if ids is None:return
            else:
                resultado=self.preselecao or self._origem_composicao()
                if resultado is None:return
                self.preselecao=None
                ids,cat,criterio=resultado
                if ids is None:return
                if not ids:raise ValueError('Nenhum elemento materializado corresponde à seleção.')
                origem='MANUAL' if criterio['modo'] in ('Seleção atual do mapa','Escolher elementos materializados') else 'AUTOMATICA'
            self._formulario(r,metadados,ids,cat,criterio,origem)
        self.pagina._com_erro(editar)

    def _formulario(self,r,metadados,ids,cat,criterio,origem):
        atual=r or {}
        d=QDialog(self)
        d.setWindowTitle('Editar conjunto' if r else 'Criar conjunto')
        v=QVBoxLayout(d)
        f=formulario(v)
        nome=QLineEdit(atual.get('nome') or criterio.get('nome') or '')
        categoria=QComboBox()
        categoria.addItems(cm.CATEGORIAS)
        categoria.setCurrentText(cat)
        subpasta=QLineEdit(atual.get('subpasta',''))
        descricao=QLineEdit(atual.get('descricao',''))
        for rotulo,w in (('Nome',nome),('Categoria',categoria),('Subpasta (opcional)',subpasta),('Descrição',descricao)):
            f.addRow(rotulo,w)
        nos=QCheckBox('Incluir as Junctions das extremidades')
        apenas=QCheckBox('Somente Pipes')
        if not metadados:
            v.addWidget(aviso(f'{len(ids)} membros na composição atual'))
            v.addWidget(apenas)
            v.addWidget(nos)
        def salvar():
            meta=dict(nome=nome.text().strip(),categoria=categoria.currentText(),subpasta=subpasta.text().strip(),
                      descricao=descricao.text().strip())
            if metadados:
                dados=dict(atual,**meta)
            else:
                chaves=cm.selecionar(self.previa,ids,tipo='PIPE' if apenas.isChecked() else 'TODOS',incluir_nos=nos.isChecked())
                dados=cm.compor(self.previa,chaves,origem=origem,criterio=criterio,
                    analise_uid=(self.pagina.dados or {}).get('uuid'),data_criacao=atual.get('data_criacao') or
                    datetime.now(timezone.utc).isoformat(),arquivado=atual.get('arquivado',False),
                    hipotese_nome=(self.foto.get('hipotese') or {}).get('nome'),**meta)
            self._gravar(dados,r)
            d.accept()
        botao(v,'Salvar conjunto',lambda:self.pagina._com_erro(salvar))
        botao(v,'Cancelar',d.reject)
        d.exec()

    def exportar_todos(self,*,completo=False):
        selecionados=[r for r in self.registros.values() if not r.get('arquivado') and self.resultados[r['uuid']]['compativel']]
        ignorados=sum(not r.get('arquivado') and not self.resultados[r['uuid']]['compativel'] for r in self.registros.values())
        if ignorados and selecionados:
            resposta=QMessageBox.question(self,'Conjuntos de outras execuções',
                f'{ignorados} conjunto(s) requerem conferência. Exportar os {len(selecionados)} compatíveis?',
                QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if resposta!=QMessageBox.Yes:return
        self.exportar(selecionados,completo=completo)

    def exportar(self,registros,*,completo=False):
        if not registros:
            self.detalhe.setText('Crie ou recupere um conjunto compatível com a execução atual.')
            return
        fmt,ok=QInputDialog.getItem(self,'Preparar Selection Sets','Formato GIS',('GeoPackage','Shapefile'),0,False)
        if not ok:return
        estados={'Todos os membros':'TODOS','Somente ativos':'ATIVO','Somente propostos':'PROPOSTO',
                 'Somente existentes':'EXISTENTE'}
        estado,ok=QInputDialog.getItem(self,'Preparar Selection Sets','Atividade ou situação do conjunto',list(estados),0,False)
        if not ok:return
        tipos={'Composição salva':'TODOS','Somente Pipes':'PIPE','Pipes e suas Junctions':'NOS'}
        tipo,ok=QInputDialog.getItem(self,'Preparar Selection Sets','Tipos de elemento',list(tipos),0,False)
        if not ok:return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta do pacote de preparação')
        if not pasta:return
        base=self._base(True)
        def gerar(parar,etapa):
            selecoes=[]
            for r in registros:
                if not cm.reconciliar(r,self.previa,self.por_id)['compativel']:
                    raise ValueError('Confira a compatibilidade do conjunto '+r['nome'])
                chaves=cm.selecionar(self.previa,((e['tipo'],e['uid']) for e in r['membros']),
                    tipo=tipos[tipo],estado=estados[estado],incluir_nos=tipos[tipo]=='NOS')
                if not chaves:raise ValueError('A composição filtrada ficou vazia para '+r['nome'])
                selecoes.append(dict(r,membros=[cm.membro(t,self.por_id[t,u]) for t,u in sorted(chaves)]))
            previa=dict(self.previa,manifesto=dict(self.previa['manifesto'],filtro_conjuntos=dict(
                atividade_ou_situacao=estados[estado],tipos=tipos[tipo])))
            return cadastro.exportar(previa,Path(pasta),'GPKG' if fmt=='GeoPackage' else 'ESRI Shapefile',
                parar,etapa,selecoes=selecoes,somente_conjuntos=not completo,base_labels=base)
        self.pagina.tarefa('Preparando Selection Sets para WaterGEMS',gerar,
                           lambda p:self.pagina.status.setText('Pacote de preparação gravado em '+str(p)))
