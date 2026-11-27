"""Correção guiada das pendências da fotografia usada pelo ModelBuilder."""

from math import isfinite
import sqlite3

from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout,
    QLineEdit, QPlainTextEdit, QVBoxLayout)
from qgis.core import QgsGeometry,QgsPointXY

from . import correcao_modelbuilder as motor
from . import persistencia_grafo_gis as pg
from .mapa_topologia_gis import _transformar, fracao_clicada
from .modelo_gis_ui import aviso,botao,formulario
from .validacao_modelbuilder_gis import EPS, diagnosticar, linha, no_ja_conectado


class CorrecaoTopologica(QDialog):
    def __init__(self,assistente,pendencias,registros,selecionada=None,*,historico=False,adicional=None):
        super().__init__(assistente)
        self.setWindowTitle('Correção topológica para ModelBuilder')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(725,555)
        self.assistente=assistente
        self.pagina=assistente.pagina
        self.foto=assistente.foto
        self.projeto=assistente.projeto['uuid']
        self.registros=dict(registros)
        self.observacoes={}
        self.registros_diagnostico={}
        self.chaves=[]
        self.historico=historico
        self.adicional=adicional
        self.pipes={r['uid']:r for r in assistente.previa['pipes']}
        self.nos={r['uid']:r for r in assistente.previa['nos']}
        self.plano=None
        self.idx=0
        v=QVBoxLayout(self)
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        self.anterior=botao(faixa,'‹ Anterior',lambda:self._mostrar(self.idx-1))
        self.posicao=aviso()
        faixa.addWidget(self.posicao,1)
        self.proxima=botao(faixa,'Próxima ›',lambda:self._mostrar(self.idx+1))
        self.alternar_b=botao(faixa,'Histórico e execuções pendentes',self._alternar)
        self.resumo=aviso()
        v.addWidget(self.resumo)
        self.detalhe=QPlainTextEdit()
        self.detalhe.setReadOnly(True)
        v.addWidget(self.detalhe,1)
        self.comandos_anel=QHBoxLayout()
        v.addLayout(self.comandos_anel)
        self.rotulo_corte=aviso('Posição do corte')
        self.comandos_anel.addWidget(self.rotulo_corte)
        self.fracao=QDoubleSpinBox()
        self.fracao.setDecimals(8)
        self.fracao.setRange(.00000001,.99999999)
        self.fracao.setSingleStep(.05)
        self.fracao.setToolTip('Posição de divisão, de 0 a 1, ao longo do comprimento geométrico.')
        self.comandos_anel.addWidget(self.fracao)
        self.meio=QComboBox()
        self.comandos_anel.addWidget(self.meio,1)
        self.corte_mapa=botao(self.comandos_anel,'Escolher corte no mapa',lambda:self._acao(self._clicar))
        self.fracao.valueChanged.connect(self._invalidar)
        self.meio.currentIndexChanged.connect(self._mudar_no)
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        self.mapa_b=botao(faixa,'Aproximar e destacar',lambda:self._acao(self._destacar))
        self.consultar_b=botao(faixa,'Consultar conectividade',self._consultar)
        self.conflitos_b=botao(faixa,'Resolver conexões conflitantes…',lambda:self._acao(self.resolver_conflitos))
        self.prever=botao(faixa,'Pré-visualizar correção',lambda:self._acao(self.preview))
        form=formulario(v)
        self.nota=QLineEdit()
        form.addRow('Observação opcional',self.nota)
        self.status=aviso()
        v.addWidget(self.status)
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        self.aplicar_b=botao(faixa,'Aplicar',lambda:self._acao(self.aplicar))
        self.reverter_b=botao(faixa,'Reverter',lambda:self._acao(lambda:self._gravar('REVERTIDA')))
        self.pendente_b=botao(faixa,'Manter pendente',lambda:self._acao(lambda:self._gravar('PENDENTE')))
        self.elemento_b=botao(faixa,'Revalidar elemento',lambda:self._acao(self.revalidar))
        self.executar_b=botao(v,'Executar hipótese derivada',lambda:self._acao(self._executar_derivada))
        botao(v,'Revalidar cadastro completo',lambda:self._acao(self._revalidar_completo))
        botao(v,'Encerrar',self.close)
        self.atualizar(pendencias,registros,selecionada=selecionada)

    def _alternar(self):
        self.historico=not self.historico
        self.atualizar(self.assistente.pendencias_vigentes(),self.assistente._correcoes(todas=True))

    def atualizar(self,pendencias,registros,*,selecionada=None):
        anterior=selecionada or (self.chaves[self.idx] if self.chaves else None)
        self.registros=registros
        self.observacoes=self.assistente._observacoes_correcao()
        ativos=motor.fila(self.foto,pendencias,registros,self.observacoes)
        self.ativos=len(ativos)
        if self.historico:
            self.registros_diagnostico={u:r['diagnostico'] for u,r in reversed(tuple(registros.items()))
                                       if r.get('diagnostico')}
        else:
            self.registros_diagnostico=ativos
            if self.adicional and any(x==self.adicional for x in pendencias):
                u=motor.identidade(self.foto['uuid'],self.adicional)
                if not (r:=registros.get(u)) or r['estado'] not in ('APLICADA','VERIFICADA'):
                    self.registros_diagnostico[u]=self.adicional
        self.chaves=list(self.registros_diagnostico)
        self.alternar_b.setText('Voltar à fila ativa' if self.historico else 'Histórico e execuções pendentes')
        self._mostrar(self.chaves.index(anterior) if anterior in self.chaves else min(self.idx,max(0,len(self.chaves)-1)))

    def _atual(self):
        if not self.chaves:raise ValueError('Não há ocorrências nesta visualização.')
        u=self.chaves[self.idx]
        return u,self.registros_diagnostico[u],self.registros.get(u,{})

    def _mostrar(self,i):
        self.idx=i
        if not self.chaves:
            self.posicao.setText(f'{self.ativos} pendências críticas ativas')
            self.resumo.setText('Nenhuma ocorrência nesta visualização.')
            self.detalhe.clear()
            self.nota.clear()
            for w in (self.anterior,self.proxima,self.reverter_b,self.pendente_b,self.elemento_b,self.prever,
                      self.mapa_b,self.consultar_b,self.conflitos_b,self.executar_b):w.setEnabled(False)
            for w in (self.rotulo_corte,self.fracao,self.meio,self.corte_mapa):w.hide()
            self._invalidar()
            self.status.setText('As decisões ficam disponíveis no histórico. Use Validar para atualizar a fila.')
            return
        uid,r,decisao=self._atual()
        mesma=not decisao or decisao['topologia_uid']==self.foto['uuid']
        aplicada=decisao.get('estado')=='APLICADA'
        obs=self.observacoes.get(uid,{})
        observada=obs.get('estado') if obs.get('correcao_rev')==decisao.get('rev') else None
        confirmada=observada=='VALIDADA'
        retomavel=aplicada and bool(decisao.get('nova_hipotese')) and not confirmada
        estado=r.get('situacao_fila','PENDENTE_ATUAL')
        if self.historico:
            estado=('CORRIGIDA_E_VALIDADA' if confirmada else observada if observada else
                    'AGUARDANDO_NOVA_EXECUCAO' if retomavel else 'AGUARDANDO_VALIDACAO' if aplicada and mesma else
                    decisao.get('estado','HISTORICA'))
        self.anterior.setEnabled(i>0)
        self.proxima.setEnabled(i+1<len(self.chaves))
        self.posicao.setText(f"{i+1} de {len(self.chaves)} · {self.ativos} pendências ativas")
        chave=r['uid'] if r.get('gis_id') in (None,'') else r['gis_id']
        self.resumo.setText(f"{r['tipo']} · {chave} · {r.get('camada') or 'Camada indisponível'}\n"
                            f"{r['motivo']} · {estado.replace('_',' ').capitalize()}")
        coords=r.get('coordenadas') or ()
        posicoes=[f'{x:.4f}, {y:.4f}' for x,y in coords]
        textos=[f"Gravidade: {r.get('gravidade','').lower()} · {r.get('codigo') or r['tipo']}",
                f"Label cadastral: {r.get('label_cadastral') or '—'}",
                f"UID do elemento: {r['uid']}"]
        if r['tipo']=='PIPE':
            textos.extend((f"Pipe original: {r.get('original') or '—'}",
                           f"Parte: {r.get('parte') or '—'} · intervalo {r.get('inicio')} → {r.get('fim')}",
                           f"Nó inicial: {r.get('no_a') or '—'} · {posicoes[0] if posicoes else '—'}",
                           f"Nó final: {r.get('no_b') or '—'} · {posicoes[-1] if posicoes else '—'}"))
        if r.get('relacoes'):
            textos.append('\nRelações na execução do diagnóstico' if self.historico else '\nRelações topológicas')
            for x in r['relacoes']:
                nome=x.get('nome') or x.get('uuid') or 'Relação'
                portas=', '.join(f'{u[:12]} @ {fr:g}' for u,fr in x.get('portas') or ())
                textos.append(f"• {nome} · {x.get('resultado') or x.get('decisao') or '—'}"
                              +(f' · {portas}' if portas else ''))
        if r.get('solucao') and not self.historico:
            textos.extend(('','Próximo passo',r['solucao']))
        if self.historico:
            from .resolver_conexoes_modelbuilder import DECISOES
            nomes={x['uuid']:x.get('nome') for x in r.get('relacoes',())}
            textos.append('\nRevisões da correção')
            for h in reversed(pg.revisoes(self.pagina._complementos(),self.projeto,uid,tipo=motor.TIPO)):
                textos.append(f"{h['data_utc'][:16]} · {h['estado'].capitalize()} · revisão {h['rev'][:12]}")
                for u,d in h.get('decisoes',{}).items():
                    textos.append(f"• {nomes.get(u) or u[:12]} · {DECISOES[d]}")
                for u,nota in h.get('notas_ligacoes',{}).items():
                    textos.append(f"• {nomes.get(u) or u[:12]} · {nota}")
                if h.get('nota'):textos.append(h['nota'])
                if nova:=h.get('nova_hipotese'):
                    textos.append('Hipótese derivada · revisão '+nova['rev'][:12])
        self.detalhe.setPlainText('\n'.join(textos))
        self.nota.setText(decisao.get('nota',''))
        pode_editar=mesma and not aplicada and not self.historico
        self.reverter_b.setEnabled(aplicada and mesma)
        self.pendente_b.setEnabled(pode_editar)
        self.elemento_b.setEnabled(mesma)
        self.executar_b.setEnabled(retomavel)
        self.mapa_b.setEnabled(mesma)
        self.consultar_b.setEnabled(mesma)
        self.conflitos_b.setEnabled(pode_editar and r['tipo']=='PIPE' and r.get('parte') is not None)
        modo_anel=pode_editar and r.get('codigo')=='ANEL_MESMO_NO'
        self.rotulo_corte.setVisible(modo_anel)
        self.fracao.setVisible(modo_anel)
        self.meio.setVisible(modo_anel)
        self.corte_mapa.setVisible(modo_anel)
        corto=decisao.get('fracao',.5)
        self.meio.blockSignals(True)
        self.meio.clear()
        self.meio.addItem('Criar nó de corte no pacote',None)
        if modo_anel and (p:=self.pipes.get(r['uid'])):
            for n in self.nos.values():
                for u,fr in n['portas']:
                    if u==p['parte'] and p['inicio']<fr<p['fim']:
                        f=(fr-p['inicio'])/(p['fim']-p['inicio'])
                        self.meio.addItem('Nó intermediário · '+n['uid'][:12],(n['uid'],f))
                        if n['uid']==decisao.get('no_intermediario'):
                            self.meio.setCurrentIndex(self.meio.count()-1)
        self.meio.blockSignals(False)
        self.fracao.setValue(corto)
        self.fracao.setEnabled(self.meio.currentData() is None)
        self.prever.setEnabled(pode_editar and r.get('codigo') in ('ANEL_MESMO_NO','MESMO_NO_PONTAS_DISTINTAS'))
        self._invalidar()
        if self.historico:
            self.status.setText('A validação foi registrada na execução '+obs['topologia_uid'][:12]+'.'
                                if observada else 'Consulte a decisão gravada e as revisões anteriores.')
        else:
            self.status.setText('Consulte as relações antes de aplicar. A prévia usa a fotografia selecionada.')

    def _mudar_no(self,*_):
        escolhido=self.meio.currentData()
        self.fracao.setEnabled(escolhido is None)
        if escolhido:self.fracao.setValue(escolhido[1])
        self._invalidar()

    def _invalidar(self,*_):
        self.plano=None
        self.aplicar_b.setEnabled(False)

    def _acao(self,fn):
        try:
            if self.pagina._projeto()['uuid']!=self.projeto or self.pagina.foto is not self.foto:
                raise ValueError('Abra novamente o exportador na execução selecionada.')
            return fn()
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as erro:
            self.status.setText(str(erro))

    def _clicar(self):
        _,r,_=self._atual()
        g=linha(self.pipes[r['uid']])
        if not g:
            raise ValueError('Geometria do Pipe indisponível.')
        canvas=self.pagina.app.iface.mapCanvas()
        crs=canvas.mapSettings().destinationCrs()
        dados=self.pagina.crs_foto
        self._destacar()
        self.hide()
        def voltar():
            self.show()
            self.raise_()
        def clique(ponto,sair):
            p=_transformar(QgsGeometry.fromPointXY(ponto),crs,dados)
            tol=max(self.foto.get('parametros',{}).get('tolerancia',.2),EPS)
            f=fracao_clicada(g,p,tol)
            if not 0<=g.distance(p)<=tol or not 0<f<1:
                self.status.setText('Clique perto do interior do anel.')
                return
            self.meio.setCurrentIndex(0)
            self.fracao.setValue(f)
            sair(True)
            self._acao(self.preview)
        if not self.pagina.iniciar_ferramenta(clique,voltar,voltar):
            voltar()

    def _destacar(self):
        _,r,_=self._atual()
        p=self.pipes.get(r['uid'])
        nos=[self.nos[u] for u in set((p.get('no_a'),p.get('no_b'))) if u in self.nos] if p else [
            self.nos[r['uid']]] if r['uid'] in self.nos else []
        itens=[('tubo',linha(p))] if p else []
        itens.extend(('local',QgsGeometry.fromPointXY(QgsPointXY(*n['xy']))) for n in nos
                     if len(n.get('xy') or ())==2 and all(isinstance(x,(float,int)) and isfinite(x) for x in n['xy']))
        self.pagina.central.mapa.destacar_investigacao(itens,self.pagina.crs_foto,True,toda_extensao=True)

    def _consultar(self):
        _,r,_=self._atual()
        self.assistente.revisar_pendencia(r)

    def resolver_conflitos(self):
        from . import resolver_conexoes_modelbuilder as conflitos
        from .resolver_conexoes_modelbuilder_ui import ResolverConexoes
        uid,r,decisao=self._atual()
        if self.historico or decisao.get('estado')=='APLICADA' or not (p:=self.pipes.get(r['uid'])):
            raise ValueError('Abra uma ocorrência ativa com uma parte de Pipe na fotografia.')
        anterior=getattr(self,'_resolver',None)
        if anterior is not None and not sip.isdeleted(anterior):
            if anterior.uid==uid:
                anterior.raise_()
                return
            anterior.close()
        vigentes=tuple(pg.vigentes(self.pagina._complementos(),self.projeto).values()) if self.pagina._complementos() else ()
        def pronto(analise):
            if sip.isdeleted(self) or not self.chaves or self._atual()[0]!=uid:return
            if not analise['ligacoes']:
                self.status.setText('Nenhuma relação declarada foi encontrada para as portas ou o trecho. Confira a inferência de proximidade e as Junctions.')
                return
            self._resolver=ResolverConexoes(self,analise,p,uid)
            self._resolver.show()
            self._resolver.destacar()
        self.pagina._tarefa_cartografica('Investigar relações do Pipe',
            lambda parar,_:conflitos.investigar(self.foto,p,vigentes,parar),pronto)

    def salvar_conflitos(self,plano,referencia):
        uid,r,antes=self._atual()
        if uid!=referencia or self.historico:
            raise ValueError('A ocorrência selecionada mudou. Reabra a resolução.')
        if antes.get('estado')=='APLICADA':
            raise ValueError('A correção já foi aplicada para esta ocorrência.')
        dados=self._dados(r,'APLICADA')
        base=self.pagina._complementos(True)
        h=self.foto.get('hipotese')
        if not plano['operacoes']:
            d=pg.salvar_revisao(base,self.projeto,motor.TIPO,dict(dados,estado='VERIFICADA',decisoes=plano['escolhas'],
                              notas_ligacoes=plano['notas']),
                              uid,antes.get('rev'))
            self.registros[uid]=d
            self.adicional=None
            self.assistente.validar()
            return d
        if not h or not h.get('rev'):
            raise ValueError('Salve e execute a hipótese atual antes de gravar uma derivação de conectividade.')
        d=pg.salvar_resolucao_modelbuilder(base,self.projeto,h,dados,plano,uid,antes.get('rev'))
        self._depois_de_gravar(uid,d)
        self.assistente.executar_derivada(d['nova_hipotese'],uid)
        return d

    def _executar_derivada(self):
        u,_,d=self._atual()
        if d.get('estado')!='APLICADA' or not d.get('nova_hipotese'):
            raise ValueError('Esta ocorrência não tem execução derivada pendente.')
        self.assistente.executar_derivada(d['nova_hipotese'],u)

    def preview(self):
        self._invalidar()
        _,r,d=self._atual()
        if d.get('estado')=='APLICADA' or self.historico:
            raise ValueError('Esta ocorrência já foi revisada. Confira sua situação no histórico.')
        p=self.pipes[r['uid']]
        if r.get('codigo')=='ANEL_MESMO_NO':
            escolhido=self.meio.currentData()
            if escolhido and not no_ja_conectado(self.pipes.values(),p['no_a'],escolhido[0]):
                raise ValueError('O nó escolhido pertence a outro componente. Revise a conexão na hipótese.')
            self.plano=motor.anel(p,self.nos,escolhido[1] if escolhido else self.fracao.value(),
                                escolhido[0] if escolhido else None)
            if (not escolhido and self.plano['no_novo']['uid'] in self.nos
                    or any(x['uid'] in self.pipes for x in self.plano['segmentos'])):
                self._invalidar()
                raise ValueError('A divisão proposta reutilizaria uma identidade incompatível.')
        elif r.get('codigo')=='MESMO_NO_PONTAS_DISTINTAS':
            self.plano=motor.separacao(p,self.foto,self.nos.get(p.get('no_a')))
        else:
            raise ValueError('Consulte a execução para restabelecer as referências ou a geometria.')
        itens=[('correcao_original',linha(p))]
        itens.extend(('correcao_segmento',linha(t)) for t in self.plano['segmentos'])
        for chave,papel in (('nos_antes','local'),('nos_depois','inicio_corredor')):
            itens.extend((papel,QgsGeometry.fromPointXY(QgsPointXY(*n['xy']))) for n in self.plano[chave])
        self.pagina.central.mapa.destacar_investigacao(itens,self.pagina.crs_foto,True,toda_extensao=True)
        comprimentos=', '.join(f"{t['comprimento_m']:g} m" for t in self.plano['segmentos'])
        self.status.setText(f"{self.plano['impacto']} Segmentos previstos: {comprimentos}.")
        self.aplicar_b.setEnabled(True)

    def aplicar(self):
        if not self.plano:
            raise ValueError('Pré-visualize a configuração antes de aplicar.')
        self._gravar('APLICADA')

    def _dados(self,r,estado):
        return dict(projeto_uid=self.projeto,topologia_uid=self.foto['uuid'],elemento_uid=r['uid'],
                    codigo=r['codigo'],estado=estado,diagnostico=r,nota=self.nota.text().strip())

    def _depois_de_gravar(self,uid,d):
        self.registros[uid]=d
        self.assistente.invalidar_validacao()
        if d.get('nova_hipotese'):
            self.historico=True
            self.atualizar([],self.registros,selecionada=uid)
            self.status.setText('Hipótese derivada salva. Execute a nova hipótese para conferir a correção.')
        else:
            self._invalidar()
            self.status.setText('Decisão gravada · aguardando validação do cadastro.')
            self.assistente.validar()

    def _gravar(self,estado,*,notas_ligacoes=None):
        if self.pagina.central.ocupado():
            raise ValueError('Aguarde a operação em curso.')
        uid,r,antes=self._atual()
        if antes.get('estado')=='APLICADA' and estado!='REVERTIDA':
            raise ValueError('A correção já foi aplicada. Use Reverter para alterar a decisão.')
        dados=self._dados(r,estado)
        if notas_ligacoes:dados['notas_ligacoes']=dict(notas_ligacoes)
        base=self.pagina._complementos(True)
        if estado=='APLICADA':
            p=self.plano
            dados.update({k:p[k] for k in ('operacao','assinatura','fracao','no_intermediario','impacto') if k in p})
        if dados.get('operacao')=='SEPARACAO':
            d=pg.salvar_separacao_modelbuilder(base,self.projeto,self.foto['hipotese'],dados,p['relacao'],uid,antes.get('rev'))
        else:
            d=pg.salvar_revisao(base,self.projeto,motor.TIPO,dados,uid,antes.get('rev'))
        self._depois_de_gravar(uid,d)

    def revalidar(self):
        _,r,d=self._atual()
        if d.get('nova_hipotese'):
            self.status.setText('Gere uma execução da hipótese derivada para confirmar a separação.')
            return
        p=self.pipes.get(r['uid'])
        if not p:
            raise ValueError('Para validar nós ou relações, use a validação do cadastro completo.')
        cfg=motor.do_pacote(self.registros,self.foto['uuid'])
        _,_,pend,excluidos,_=diagnosticar(self.assistente.previa,[p],list(self.nos.values()),
            self.assistente.tolerancia.value(),correcoes=cfg,segmentar=self.assistente.aneis.isChecked())
        erros=[x['motivo'] for x in pend if x['gravidade']=='CRITICA' and x['uid']==p['uid']]
        self.status.setText(' · '.join(erros) if p['uid'] in excluidos else
                            'Elemento validado para a materialização atual. Revalide o cadastro antes de exportar.')

    def _revalidar_completo(self):
        self.assistente.escopo.setCurrentIndex(self.assistente.escopo.findData('COMPLETO'))
        self.assistente.validar()
        self.historico=False
