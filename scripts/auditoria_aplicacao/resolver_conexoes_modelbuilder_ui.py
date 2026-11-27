"""Decisões assistidas, prévia com o motor GIS e revisão de portas no mapa."""

import sqlite3

from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox,QDialog,QHBoxLayout,QInputDialog,QLineEdit,QPlainTextEdit,QVBoxLayout
from qgis.core import QgsGeometry,QgsPointXY,QgsProject

from . import entradas_grafo_gis as entradas
from . import hipoteses_gis as hg
from . import persistencia_grafo_gis as pg
from . import resolver_conexoes_modelbuilder as motor
from .executar_grafo_gis import executar
from .investigacao_gis import geometria
from .mapa_topologia_gis import IndiceSelecao,_transformar,escolher,fracao_clicada
from .modelo_gis import revisoes
from .modelo_gis_ui import aviso,botao,formulario
from .tabelas_topologia_gis import ACOMPANHAMENTO,TabelaGIS
from .validacao_modelbuilder_gis import linha


def nome(t):
    for k in ('label','id','uid'):
        if t.get(k) not in (None,''):return str(t[k])
    return 'Referência indisponível'


class ResolverConexoes(QDialog):
    def __init__(self,correcao,analise,pipe,uid):
        super().__init__(correcao)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Resolver conexões conflitantes')
        self.resize(955,660)
        self.correcao=correcao
        self.assistente=correcao.assistente
        self.pagina=correcao.pagina
        self.foto=correcao.foto
        self.analise,self.pipe=analise,pipe
        self.uid=uid
        self.ligacoes=analise['ligacoes']
        self.edicoes={}
        self.notas={}
        self.escolhas={}
        self.plano=None
        self._token=0
        self.indice=None
        self._capturando=False
        v=QVBoxLayout(self)
        rotulo=nome(analise['tubos'][pipe['parte']])
        consequencia=(' As duas pontas usam o mesmo nó, o que impede a exportação deste segmento.'
                      if pipe['no_a'] and pipe['no_a']==pipe['no_b'] else ' Confira se as posições representam ligações distintas.')
        v.addWidget(aviso(f'{rotulo} · {len(self.ligacoes)} ligações para conferir\n'
            f"Segmento de {pipe['comprimento_m']:.6g} m · tolerância de agrupamento {analise['tolerancia']:g} m. "
            f'{consequencia} A proximidade indica onde revisar.'))
        f=formulario(v)
        self.rapida=QComboBox()
        self.rapida.addItem('Escolher por ligação',None)
        if len(self.ligacoes)==2:
            for texto,k in (('Manter somente A','A'),('Manter somente B','B'),('Manter ambas','AMBAS'),
                            ('Consolidar em um nó físico','CONSOLIDAR'),('Registrar ambas como Sem conexão','NENHUMA'),
                            ('Informação insuficiente','PENDENTE')):
                self.rapida.addItem(texto,k)
        else:
            self.rapida.addItem('Consolidar ligações marcadas em um nó físico','CONSOLIDAR')
            self.rapida.addItem('Informação insuficiente','PENDENTE')
        f.addRow('Decisão rápida',self.rapida)
        self.principal=QComboBox()
        for x in self.ligacoes:self.principal.addItem('Ligação '+x['letra'],x['registro']['uuid'])
        f.addRow('Posição principal na consolidação',self.principal)
        self.principal.setEnabled(False)
        self.principal.currentIndexChanged.connect(self._invalidar)
        self.tabela=TabelaGIS()
        self.tabela.colunas(('Ligação','Pipes','Posição','Distância','Interpretação','Participação','Acompanhamento','Decisão proposta'))
        for i,largura in enumerate((55,153,64,71,132,107,115,211)):
            self.tabela.setColumnWidth(i,largura)
        v.addWidget(self.tabela,1)
        for i,x in enumerate(self.ligacoes):
            r=x['registro']
            u=r['uuid']
            detalhes=', '.join(nome(analise['tubos'].get(a,{'uid':a})) for a,_ in r['portas'])
            dist='—' if x['distancia_m'] is None else f"{x['distancia_m']:.6g} m"
            estado=x['situacao'].replace('_',' ').capitalize()
            if x['na_cadeia']:estado+=' · liga as duas portas'
            self.tabela.inserir((x['letra'],detalhes,', '.join(f'{p:.7g}' for p in x['fracoes']),dist,
                pg.DECISOES.get(r.get('decisao'),r.get('decisao')),estado,
                ACOMPANHAMENTO.get(r.get('acompanhamento'),'Pendente'),None),u)
            c=QComboBox()
            for k,texto in motor.DECISOES.items():c.addItem(texto,k)
            c.setCurrentIndex(c.findData(motor.REJEITAR if x['participa'] and r.get('decisao')=='SEPARADA'
                                        else motor.MANTER if x['situacao']=='APLICADA' else motor.EXCLUIR))
            c.currentIndexChanged.connect(self._invalidar)
            self.tabela.setCellWidget(i,7,c)
            self.escolhas[u]=c
        self.rapida.currentIndexChanged.connect(self._aplicar_rapida)
        self.tabela.cellClicked.connect(lambda i,_:self._acao(lambda:self._mostrar_ligacao(self.ligacoes[i])))
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        botao(faixa,'Mostrar todas no mapa',lambda:self._acao(self.destacar))
        botao(faixa,'Histórico da ligação…',lambda:self._acao(self.historico))
        botao(faixa,'Revisar referência ou posição no mapa…',lambda:self._acao(self.editar_mapa))
        botao(faixa,'Observação da ligação…',lambda:self._acao(self.anotar))
        self.texto=QPlainTextEdit()
        self.texto.setReadOnly(True)
        v.addWidget(self.texto,1)
        self.status=aviso()
        v.addWidget(self.status)
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        botao(faixa,'Pré-visualizar decisão',lambda:self._acao(self.preview))
        self.salvar_b=botao(faixa,'Salvar decisões e recalcular conectividade',lambda:self._acao(self.salvar))
        botao(faixa,'Manter pendente',lambda:self._acao(self.pendente))
        botao(faixa,'Voltar',self.close)
        self._invalidar()
        if self.ligacoes:self.tabela.selectRow(0)
        self._mostrar_analise()

    def _mostrar_analise(self):
        letras={x['registro']['uuid']:x['letra'] for x in self.ligacoes}
        textos=['Relações aplicadas nesta fotografia aparecem como Aplicada. Fora da hipótese e referência alterada indicam que o vínculo não foi aplicado.']
        if self.analise['duplicatas']:
            textos.extend(' e '.join(letras[r['uuid']] for r in d['registros'])+' · '+
                motor.duplicatas_conexoes_gis.ROTULOS[d['tipo']] for d in self.analise['duplicatas'])
        else:
            textos.append('A auditoria de duplicatas não encontrou equivalências demonstráveis neste grupo.')
        for x in self.ligacoes:
            r=x['registro']
            if x['ultima_revisao']!=r['rev']:
                textos.append(f"{x['letra']} · a revisão vigente difere da fotografia. Consulte o histórico.")
            textos.extend(f"{x['letra']} · {m}" for m in x['motivos'])
        self.texto.setPlainText('\n'.join(textos))

    def _acao(self,fn):
        try:
            if (self.pagina.foto is not self.foto or (self.pagina._projeto() or {}).get('uuid')!=self.foto['projeto_uid']
                    or not self.correcao.chaves or self.correcao._atual()[0]!=self.uid):
                raise ValueError('O projeto ou a fotografia mudou. Reabra a resolução.')
            return fn()
        except (ValueError,OSError,RuntimeError,sqlite3.Error) as erro:
            self.status.setText(str(erro))

    def _invalidar(self,*_):
        self._token+=1
        self.plano=None
        self.salvar_b.setEnabled(False)
        self.status.setText('Pré-visualize para comparar a conectividade antes de salvar.')

    def _aplicar_rapida(self,*_):
        modo=self.rapida.currentData()
        self.principal.setEnabled(modo=='CONSOLIDAR')
        if modo in ('A','B','AMBAS','NENHUMA') or modo=='CONSOLIDAR' and len(self.ligacoes)==2:
            for x in self.ligacoes:
                c=self.escolhas[x['registro']['uuid']]
                k=motor.REJEITAR if modo=='NENHUMA' else motor.MANTER if modo in ('AMBAS','CONSOLIDAR',x['letra']) else motor.EXCLUIR
                c.setCurrentIndex(c.findData(k))
        self._invalidar()
        if modo=='PENDENTE':
            self.status.setText('Use Manter pendente para encerrar sem mudanças de conectividade.')

    def _ligacao(self):
        i=self.tabela.currentRow()
        if i<0:raise ValueError('Selecione a ligação na tabela.')
        return self.ligacoes[i]

    def _mostrar_ligacao(self,x):
        r=x['registro']
        tubos=self.analise['tubos']
        portas=self.edicoes.get(r['uuid'],r['portas'])
        texto=[f"Ligação {x['letra']} · {r.get('nome','')}"]
        texto.extend(f"{nome(tubos.get(u,{'uid':u}))} · posição {f:.7g}" for u,f in portas)
        texto.extend(x['motivos'])
        if self.plano is None:self.texto.setPlainText('\n'.join(texto))
        self.destacar([x])

    def destacar(self,ligacoes=None):
        grupos=self.ligacoes if ligacoes is None else ligacoes
        tubos=self.analise['tubos']
        partes={u for x in grupos for u,_ in self.edicoes.get(x['registro']['uuid'],x['registro']['portas'])}
        itens=[('correcao_original',geometria(tubos[self.pipe['parte']]['wkb'])),
               ('correcao_segmento',linha(self.pipe))]
        itens.extend(('tubo',geometria(tubos[u]['wkb'])) for u in sorted(partes-{self.pipe['parte']}) if u in tubos)
        rotulos=[]
        for x in grupos:
            portas=self.edicoes.get(x['registro']['uuid'],x['registro']['portas'])
            pontos=[p for porta in portas if (p:=motor._ponto(tubos,porta)) is not None]
            itens.extend(('evento',QgsGeometry.fromPointXY(QgsPointXY(*p))) for p in pontos)
            if pontos:rotulos.append((x['letra'],x['coordenada'] if x['coordenada'] and portas==x['registro']['portas'] else pontos[0]))
        itens.extend(('local',QgsGeometry.fromPointXY(QgsPointXY(*n['xy']))) for n in self.analise['nos'].values())
        self.pagina.central.mapa.destacar_investigacao(itens,self.pagina.crs_foto,True,toda_extensao=True,
            foco=linha(self.pipe),rotulos=rotulos)

    def historico(self):
        x=self._ligacao()
        r=x['registro']
        tubos=self.analise['tubos']
        texto=['Vínculo exibido · revisão '+r['rev'],
              'Revisão vigente · '+(x['ultima_revisao'] or 'indisponível')]
        for h in pg.revisoes(self.pagina._complementos(),self.foto['projeto_uid'],r['uuid'],tipo='CONEXAO'):
            portas=', '.join(f"{nome(tubos.get(u,{'uid':u}))} @ {f:.7g}" for u,f in h['portas'])
            texto.append(f"{h['rev'][:12]} · {h['data_utc'][:16]} · {pg.DECISOES.get(h['decisao'])}\n{portas}\n{h.get('nota','')}")
        self.texto.setPlainText('\n\n'.join(texto))

    def anotar(self):
        r=self._ligacao()['registro']
        nota,ok=QInputDialog.getText(self,'Observação da ligação','Observação',text=self.notas.get(r['uuid'],r.get('nota','')))
        if ok:
            self.notas[r['uuid']]=nota
            self._invalidar()

    def editar_mapa(self):
        r=self._ligacao()['registro']
        if self.pagina.central.ocupado():return
        portas=list(self.edicoes.get(r['uuid'],r['portas']))
        tubos=self.analise['tubos']
        op=[f"{i+1} · {nome(tubos.get(u,{'uid':u}))} · {f:.7g}" for i,(u,f) in enumerate(portas)]
        chave,ok=QInputDialog.getItem(self,'Revisar referência','Porta a substituir',op,editable=False)
        if not ok:return
        i=op.index(chave)
        def capturar(indice):
            if sip.isdeleted(self):return
            self.indice=indice
            canvas=self.pagina.app.iface.mapCanvas()
            crs=canvas.mapSettings().destinationCrs()
            self._capturando=True
            self.hide()
            self.pagina._mensagem_captura('Clique no Pipe e na posição desejados. Esc cancela.')
            def voltar():
                self._capturando=False
                if not sip.isdeleted(self):
                    self.show()
                    self.raise_()
            def clique(pt,sair):
                g=_transformar(QgsGeometry.fromPointXY(pt),crs,self.pagina.crs_foto)
                tol=self.analise['tolerancia']
                candidatos=indice.consultar(g,max(tol,0.01))
                alvo=escolher(self,candidatos,lambda x:nome(x[2]))
                if alvo:
                    _,u,_,linha_alvo=alvo
                    f=fracao_clicada(linha_alvo,g,tol)
                    portas[i]=(u,f)
                    self.edicoes[r['uuid']]=portas
                    self._invalidar()
                    self.status.setText(f'Porta proposta: {nome(tubos[u])} · {f:.7g}. Pré-visualize antes de salvar.')
                    sair(True)
            if not self.pagina.iniciar_ferramenta(clique,voltar,voltar):voltar()
        if self.indice:
            capturar(self.indice)
        else:
            self.pagina._tarefa_cartografica('Preparar a localização de Pipes',lambda parar,_:IndiceSelecao(tubos.values(),parar),capturar)

    def preview(self):
        if self.pagina.central.ocupado():return
        self._invalidar()
        if self.rapida.currentData()=='PENDENTE':
            raise ValueError('Registre a pendência sem alterar as relações.')
        plano=motor.planejar(self.foto,self.analise,{u:c.currentData() for u,c in self.escolhas.items()},
            edicoes=self.edicoes,notas=self.notas,consolidar=self.principal.currentData() if self.principal.isEnabled() else None)
        p=self.pagina._projeto()
        f=self.foto
        config=f.get('configuracao')
        assinatura=f.get('assinatura_inventario')
        if not config or not assinatura:
            raise ValueError('Gere uma execução da revisão salva para conferir as fontes antes de propor mudanças.')
        modelo=next((r for r in revisoes(p) if r['uuid']==f['modelo_rev']),None)
        if not modelo:
            raise ValueError('A revisão do Modelo GIS da fotografia está indisponível.')
        redes={q['uid'] for q in config['fontes'] if q['categoria']=='PIPE'}
        prep=entradas.preparar(modelo['fontes'],self.pagina.central.modelo_gis.camadas(),f['crs'],
                              QgsProject.instance().transformContext(),redes=redes,unidades=config['unidades'])
        if hg.configuracao(prep,f['modelo_rev'],f['parametros'])!=config:
            raise ValueError('As fontes ou os parâmetros diferem da execução que está sendo corrigida.')
        conjuntos=tuple(self.assistente.conjuntos.values())
        def trabalho(parar,etapa):
            inv=entradas.ler(prep,parar,etapa)
            if hg.assinatura_inventario(inv)!=assinatura:
                raise ValueError('O conteúdo das fontes mudou. Gere uma nova execução antes de revisar as ligações.')
            depois=executar(prep,{},f['parametros'],plano['participantes'],parar,etapa,inventario=inv)
            return motor.impacto(f,depois,self.analise,conjuntos,plano)
        token=self._token
        def pronto(previsao):
            if not sip.isdeleted(self) and token==self._token and self.pagina.foto is f:
                self._mostrar_previa(plano,previsao)
        self.status.setText('Calculando a topologia proposta com as fontes verificadas…')
        worker=self.pagina._tarefa_cartografica('Prévia de resolução de ligações',trabalho,pronto)
        if worker:
            op=self.pagina.app.atividades.atual
            def conferir():
                if not sip.isdeleted(self) and token==self._token and op.estado!='CONCLUIDO':
                    self.status.setText(self.pagina.status.text() or 'Prévia não concluída.')
            worker.finished.connect(conferir)

    def _mostrar_previa(self,plano,previsao):
        partes=self.analise['tubos']
        texto=[]
        for chave in ('antes','depois'):
            segmentos=previsao[chave]
            comps=previsao['componentes_'+chave]
            texto.append(f"Topologia {'atual' if chave=='antes' else 'proposta'} · {len(segmentos)} segmentos nas partes envolvidas · {len(comps)} componentes relacionados")
            for e in segmentos:
                texto.append(f"{nome(partes[e['tubo']])} · {e['inicio']:.6g} → {e['fim']:.6g} · {e['comprimento_m']:.6g} m"
                             +(' · mesmo nó nas duas pontas' if e['a']==e['b'] else ''))
        letras={x['registro']['uuid']:x['letra'] for x in self.ligacoes}
        texto.extend(['',*(f'{letras[u]} · {motor.DECISOES[d]}' for u,d in plano['escolhas'].items()),
            f"{len(previsao['novos_nos'])} nó(s) novo(s) · {len(previsao['removidos_nos'])} nó(s) substituído(s)",
            f"Tubulações com alteração: {', '.join(nome(partes[u]) for u in previsao['afetadas']) or 'nenhuma'}",
            f"Equipamentos para conferir: {', '.join(nome(e) for e in previsao['equipamentos']) or 'nenhum identificado'}",
            f"Selection Sets para conferir: {', '.join(previsao['conjuntos']) or 'nenhum identificado'}"])
        self.texto.setPlainText('\n'.join(texto))
        itens=[]
        for chave,papel in (('antes','correcao_original'),('depois','correcao_segmento')):
            for e in previsao[chave]:
                if e['tubo']!=self.pipe['parte']:continue
                g=geometria(partes[e['tubo']]['wkb'])
                itens.append((papel,type(g)(g.constGet().curveSubstring(e['inicio']*g.length(),e['fim']*g.length()))))
        for chave,papel in (('nos_antes','local'),('nos_depois','inicio_corredor')):
            itens.extend((papel,QgsGeometry.fromPointXY(QgsPointXY(*n['xy']))) for n in previsao[chave])
        self.pagina.central.mapa.destacar_investigacao(itens,self.pagina.crs_foto,True,toda_extensao=True)
        pendentes=[e for e in previsao['depois'] if e['a']==e['b']]
        novos={e['uid'] for e in pendentes}-{e['uid'] for e in previsao['antes'] if e['a']==e['b']}
        if novos:
            self.status.setText('A proposta gera novas arestas com o mesmo nó nas pontas. Revise as posições ou decisões.')
            return
        if not plano['operacoes'] and pendentes:
            self.status.setText('As decisões mantêm a inconsistência atual. Revise uma ligação ou mantenha pendente.')
            return
        self.plano=plano
        self.salvar_b.setEnabled(True)
        self.status.setText('A proposta ainda contém uma pendência nas partes envolvidas.' if pendentes else
                            'Prévia calculada. A resolução será confirmada na validação do pacote após a nova execução.')

    def salvar(self):
        if not self.plano:raise ValueError('Calcule a prévia antes de salvar.')
        if self.pagina.central.ocupado():return
        self.correcao.salvar_conflitos(self.plano,self.uid)
        if not sip.isdeleted(self):self.close()

    def pendente(self):
        self.correcao.nota.setText('Informação insuficiente sobre as ligações revisadas.')
        self.correcao._gravar('PENDENTE',notas_ligacoes=self.notas)
        self.close()

    def closeEvent(self,evento):
        if self._capturando:self.pagina.cancelar_captura(reabrir=False)
        super().closeEvent(evento)
