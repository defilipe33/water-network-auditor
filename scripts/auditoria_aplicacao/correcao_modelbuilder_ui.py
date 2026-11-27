"""Correção guiada das pendências da fotografia usada pelo ModelBuilder."""

from math import isfinite
import sqlite3

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
    def __init__(self,assistente,pendencias,registros,selecionada=None):
        super().__init__(assistente)
        self.setWindowTitle('Correção topológica para ModelBuilder')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(725,555)
        self.assistente=assistente
        self.pagina=assistente.pagina
        self.foto=assistente.foto
        self.projeto=assistente.projeto['uuid']
        self.registros=dict(registros)
        self.registros_diagnostico={}
        for r in pendencias:
            if r.get('gravidade')=='CRITICA':
                self.registros_diagnostico[motor.identidade(self.foto['uuid'],r)]=r
        for u,r in registros.items():
            if r.get('diagnostico'):
                self.registros_diagnostico.setdefault(u,r['diagnostico'])
        self.chaves=list(self.registros_diagnostico)
        self.pipes={r['uid']:r for r in assistente.previa['pipes']}
        self.nos={r['uid']:r for r in assistente.previa['nos']}
        self.plano=None
        self.idx=self.chaves.index(selecionada) if selecionada in self.chaves else 0
        v=QVBoxLayout(self)
        faixa=QHBoxLayout()
        v.addLayout(faixa)
        self.anterior=botao(faixa,'‹ Anterior',lambda:self._mostrar(self.idx-1))
        self.posicao=aviso()
        faixa.addWidget(self.posicao,1)
        self.proxima=botao(faixa,'Próxima ›',lambda:self._mostrar(self.idx+1))
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
        botao(faixa,'Aproximar e destacar',lambda:self._acao(self._destacar))
        botao(faixa,'Consultar conectividade',self._consultar)
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
        botao(faixa,'Manter pendente',lambda:self._acao(lambda:self._gravar('PENDENTE')))
        botao(faixa,'Revalidar elemento',lambda:self._acao(self.revalidar))
        botao(v,'Revalidar cadastro completo',lambda:self._acao(self._revalidar_completo))
        botao(v,'Encerrar',self.close)
        self._mostrar(self.idx)

    def _atual(self):
        u=self.chaves[self.idx]
        return u,self.registros_diagnostico[u],self.registros.get(u,{})

    def _mostrar(self,i):
        self.idx=i
        _,r,decisao=self._atual()
        self.anterior.setEnabled(i>0)
        self.proxima.setEnabled(i+1<len(self.chaves))
        self.posicao.setText(f'Pendência {i+1} de {len(self.chaves)}')
        chave=r['uid'] if r.get('gis_id') in (None,'') else r['gis_id']
        self.resumo.setText(f"{r['tipo']} · {chave} · {r.get('camada') or 'Camada indisponível'}\n"
                            f"{r['motivo']} · {decisao.get('estado','PENDENTE').title()}")
        coords=r.get('coordenadas') or ()
        posicoes=[f'{x:.4f}, {y:.4f}' for x,y in coords]
        textos=[f"Gravidade: crítica · {r.get('codigo') or r['tipo']}",
                f"Label cadastral: {r.get('label_cadastral') or '—'}",
                f"UID do elemento: {r['uid']}"]
        if r['tipo']=='PIPE':
            textos.extend((f"Pipe original: {r.get('original') or '—'}",
                           f"Parte: {r.get('parte') or '—'} · intervalo {r.get('inicio')} → {r.get('fim')}",
                           f"Nó inicial: {r.get('no_a') or '—'} · {posicoes[0] if posicoes else '—'}",
                           f"Nó final: {r.get('no_b') or '—'} · {posicoes[-1] if posicoes else '—'}"))
        if r.get('relacoes'):
            textos.append('\nRelações topológicas')
            for x in r['relacoes']:
                nome=x.get('nome') or x.get('uuid') or 'Relação'
                portas=', '.join(f'{u[:12]} @ {fr:g}' for u,fr in x.get('portas') or ())
                textos.append(f"• {nome} · {x.get('resultado') or x.get('decisao') or '—'}"
                              +(f' · {portas}' if portas else ''))
        if r.get('solucao'):
            textos.extend(('','Próximo passo',r['solucao']))
        self.detalhe.setPlainText('\n'.join(textos))
        self.nota.setText(decisao.get('nota',''))
        self.reverter_b.setEnabled(decisao.get('estado')=='APLICADA')
        modo_anel=r.get('codigo')=='ANEL_MESMO_NO'
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
        self.prever.setEnabled(r.get('codigo') in ('ANEL_MESMO_NO','MESMO_NO_PONTAS_DISTINTAS'))
        self._invalidar()
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

    def preview(self):
        self._invalidar()
        _,r,_=self._atual()
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

    def _gravar(self,estado):
        if self.pagina.central.ocupado():
            raise ValueError('Aguarde a operação em curso.')
        uid,r,antes=self._atual()
        dados=dict(projeto_uid=self.projeto,topologia_uid=self.foto['uuid'],elemento_uid=r['uid'],
                   codigo=r['codigo'],estado=estado,diagnostico=r,nota=self.nota.text().strip())
        base=self.pagina._complementos(True)
        if estado=='APLICADA':
            p=self.plano
            dados.update({k:p[k] for k in ('operacao','assinatura','fracao','no_intermediario','impacto') if k in p})
        if dados.get('operacao')=='SEPARACAO':
            d=pg.salvar_separacao_modelbuilder(base,self.projeto,self.foto['hipotese'],dados,p['relacao'],uid,antes.get('rev'))
        else:
            d=pg.salvar_revisao(base,self.projeto,motor.TIPO,dados,uid,antes.get('rev'))
        self.registros[uid]=d
        self.assistente._validado=None
        self._mostrar(self.idx)
        if d.get('nova_hipotese'):
            self.status.setText('Hipótese derivada salva. Em Conectividade, selecione a hipótese “separar extremidades” '
                                'e execute novamente. Use a execução nova para exportar.')
        elif estado=='REVERTIDA' and antes.get('nova_hipotese'):
            self.status.setText('Reversão registrada. Selecione a hipótese original nas próximas execuções.')
        else:
            self.revalidar()

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
        self.close()
