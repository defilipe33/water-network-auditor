"""Assistente e histórico do pacote de importação ModelBuilder."""

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.PyQt.QtCore import Qt
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QInputDialog,
    QDoubleSpinBox, QLineEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from auditoria_fronteiras.modelos import verificar_cancelamento
from . import cadastro_exportavel as cadastro
from . import conjuntos_modelagem as cm
from . import modelbuilder_conferencia as conferir
from . import modelbuilder_gis as mb
from . import persistencia_grafo_gis as pg
from .manifesto_projeto import pasta_projeto
from .modelo_gis_ui import aviso, botao, formulario
from .publicar_pasta_gis import publicar


def _combo(pares):
    c=QComboBox()
    for rotulo,k in pares:
        c.addItem(rotulo,k)
    return c


def _revisoes(pagina,tipo):
    return {r['uuid']:r for r in pg.revisoes(pagina._complementos(),pagina._projeto()['uuid'],tipo=tipo)}


def _pasta(p,r=None):
    if r and r.get('relativo'):
        if not p.get('manifesto_wna'):
            raise ValueError('Abra o manifesto .wna antes de acessar o caminho relativo.')
        raiz=Path(p['manifesto_wna']).parent.resolve()
        destino=(raiz/r['pasta']).resolve()
        if not destino.is_relative_to(raiz):
            raise ValueError('A referência relativa está fora da pasta do projeto.')
        return destino
    return Path(r['pasta']) if r else pasta_projeto(p,'EXPORTACOES',Path.home())


class AssistenteModelBuilder(QDialog):
    def __init__(self,pagina,previa):
        super().__init__(pagina)
        self.setWindowTitle('Exportar modelo para WaterGEMS')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(715,565)
        self.pagina=pagina
        self.projeto=pagina._projeto()
        self.foto=pagina.foto
        self.previa=previa
        self.perfis=_revisoes(pagina,'MODELBUILDER_PERFIL')
        self.conjuntos={u:r for u,r in _revisoes(pagina,'CONJUNTO_WG').items() if not r.get('arquivado') and
                        r['topologia_uid']==previa['manifesto']['execucao']}
        self.escopo_chaves=None
        self.conjuntos_ids=[]
        v=QVBoxLayout(self)
        self.tabs=QTabWidget()
        v.addWidget(self.tabs)
        selecao=self._aba('Origem e escopo')
        m=previa['manifesto']
        totais=m['contagens']
        hip=m.get('hipotese') or {}
        selecao.addWidget(aviso(f"{self.projeto['nome']} · {hip.get('nome','Hipótese temporária')} · revisão "
            f"{str(hip.get('rev') or '—')[:12]}\nExecução {m['execucao'][:12]} · cadastro {str(m['modelo_cadastral_rev'])[:12]}\n"
            f"{totais['conexoes_aplicadas']} conexões aplicadas · {totais['complementares']} Pipes complementares"))
        self.escopo=_combo((('Cadastro completo','COMPLETO'),('Participantes da hipótese','HIPOTESE'),
            ('Rede alcançável pelas origens selecionadas','ALCANCAVEL'),('Corredores calculados','CORREDORES'),
            ('Blocos calculados','BLOCOS'),('Áreas cadastradas','AREAS'),('Conjuntos personalizados','CONJUNTOS')))
        form=formulario(selecao)
        form.addRow('Escopo',self.escopo)
        self.escopo.currentIndexChanged.connect(lambda *_:setattr(self,'escopo_chaves',None))
        botao(selecao,'Escolher corredores, blocos, áreas ou conjuntos…',lambda:self._acao(self._escolher_escopo))
        self.selecao_resumo=aviso('O cadastro completo inclui Pipes isolados e fora da hipótese.')
        selecao.addWidget(self.selecao_resumo)
        selecao.addStretch()
        dados=self._aba('Tipos e atributos')
        self.perfis_combo=_combo([('Novo perfil',None),*((r['nome']+' · '+u[:8],u) for u,r in self.perfis.items())])
        form=formulario(dados)
        form.addRow('Perfil salvo',self.perfis_combo)
        self.nome=QLineEdit('Preparação GIS')
        form.addRow('Nome do perfil',self.nome)
        self.destino=_combo((v,v) for v in mb.DESTINOS)
        self.destino.setCurrentText('2026')
        form.addRow('Versão de destino',self.destino)
        self.modo=_combo((('Criar modelo de teste','NOVO'),('Preparar atualização','ATUALIZAR')))
        form.addRow('Operação',self.modo)
        self.modelo=QLineEdit()
        form.addRow('Identidade do modelo de destino',self.modelo)
        self.anterior=QLineEdit()
        self.anterior.setReadOnly(True)
        form.addRow('Pacote de referência',self.anterior)
        botao(dados,'Localizar pacote ModelBuilder anterior…',self.localizar_anterior)
        self.observado=QLineEdit()
        self.observado.setReadOnly(True)
        form.addRow('FlexTables do destino (opcional)',self.observado)
        botao(dados,'Localizar CSV para a prévia de atualização…',self.localizar_observado)
        nomes={t:t.title() for t in mb.PROPRIEDADES}
        self.tipos={}
        self.campos={}
        atribuiveis=defaultdict(set)
        for r in previa['cadastro']:
            atribuiveis[r['categoria']].update(r.get('atributos_originais') or {})
        for tipo,props in mb.PROPRIEDADES.items():
            incluir=QCheckBox(nomes[tipo])
            incluir.setChecked(tipo in ('PIPE','JUNCTION'))
            incluir.setEnabled(tipo not in ('PIPE','JUNCTION'))
            dados.addWidget(incluir)
            self.tipos[tipo]=incluir
            f=formulario(dados)
            self.campos[tipo]={}
            for propriedade,(rotulo,unidade) in props.items():
                c=_combo([('Em branco',None),*((k,k) for k in sorted(atribuiveis[tipo]))])
                u=_combo((x,x) for x in (('C',) if unidade=='C' else ('m','cm','mm','km','ft')))
                f.addRow(rotulo,c)
                f.addRow('Unidade do campo',u)
                self.campos[tipo][propriedade]=(c,u)
        dados.addWidget(aviso('A chave técnica, o Label previsto, o GIS-ID original e os nós Start/Stop são inclusos. '
            'Reservoirs e Tanks precisam de atributos e vínculo verificados. Os demais equipamentos seguem no inventário.'))
        self.perfis_combo.currentIndexChanged.connect(self._aplicar_perfil)
        botao(dados,'Salvar perfil no projeto',lambda:self._acao(self._salvar_perfil))
        final=self._aba('Atividade, conjuntos e saída')
        self.atividade=_combo((('Manter atividade da prévia','PREVIA'),('Ativos na hipótese','HIPOTESE'),('Tudo a definir','INDEFINIDA')))
        f=formulario(final)
        f.addRow('Atividade pretendida',self.atividade)
        self.formato=_combo((('Shapefile e tabelas','ESRI Shapefile'),('GeoPackage e tabelas','GPKG'),('CSV com WKT','CSV')))
        f.addRow('Formato',self.formato)
        self.tolerancia=QDoubleSpinBox()
        self.tolerancia.setRange(0,1)
        self.tolerancia.setDecimals(4)
        self.tolerancia.setValue(.001)
        self.tolerancia.setSuffix(' m')
        f.addRow('Tolerância de conferência',self.tolerancia)
        botao(final,'Incluir conjuntos salvos…',self.escolher_conjuntos)
        self.validacao=aviso(f"{totais['originais_materializados']} de {totais['pipes_originais']} Pipes físicos · {totais['segmentos']} segmentos · "
            f"{totais['pipes_divididos']} divididos\n{totais['fora_da_hipotese']} segmentos fora da hipótese · "
            f"{totais['sem_origem']} sem origem · {totais['atividade'].get('INATIVO',0)} previstos como inativos\n"
            f"{totais['junctions']} nós · {totais['equipamentos']} equipamentos inventariados · {totais['sem_diametro']} sem diâmetro.\n"
            +( 'Existem lacunas. Consulte a tabela de pendências antes de importar.' if m['lacunas'] else 'O pacote inclui uma ficha de conferência para o ModelBuilder.'))
        final.addWidget(self.validacao)
        botao(final,'Validar e exportar pacote…',lambda:self._acao(self.exportar))
        botao(final,'Conferir importações ou reabrir pacotes…',self.abrir_historico)
        final.addStretch()
        self.status=aviso()
        v.addWidget(self.status)
        botao(v,'Fechar',self.reject)

    def abrir_historico(self):
        self._historico=HistoricoModelBuilder(self.pagina,self)
        self._historico.open()

    def _aba(self,nome):
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        w=QWidget()
        scroll.setWidget(w)
        self.tabs.addTab(scroll,nome)
        return QVBoxLayout(w)

    def _acao(self,fn):
        try:
            return fn()
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as erro:
            self.status.setText(str(erro))

    def _perfil(self):
        campos={t:{k:dict(campo=c.currentData(),unidade=u.currentData()) for k,(c,u) in ps.items() if c.currentData()}
                for t,ps in self.campos.items()}
        return mb.validar_perfil(dict(versao=mb.VERSAO,nome=self.nome.text().strip(),destino=self.destino.currentData(),
            modo=self.modo.currentData(),modelo_destino=self.modelo.text().strip(),tipos=[t for t,b in self.tipos.items()
            if b.isChecked()],campos=campos,politica_remocao='PRESERVAR'))

    def _salvar_perfil(self):
        d=self._perfil()
        anterior=self.perfis.get(self.perfis_combo.currentData(),{})
        r=pg.salvar_revisao(self.pagina._complementos(True),self.projeto['uuid'],'MODELBUILDER_PERFIL',d,
                            anterior.get('uuid'),anterior.get('rev'))
        u=r['uuid']
        self.perfis[u]=r
        idx=self.perfis_combo.findData(u)
        if idx<0:
            self.perfis_combo.addItem(r['nome']+' · '+u[:8],u)
            idx=self.perfis_combo.count()-1
        self.perfis_combo.setCurrentIndex(idx)
        self.status.setText('Perfil salvo · revisão '+r['rev'][:8])

    def _aplicar_perfil(self,*_):
        r=self.perfis.get(self.perfis_combo.currentData())
        if not r:
            return
        self.nome.setText(r['nome'])
        self.destino.setCurrentIndex(self.destino.findData(r['destino']))
        self.modo.setCurrentIndex(self.modo.findData(r['modo']))
        self.modelo.setText(r.get('modelo_destino',''))
        for t,ps in self.campos.items():
            self.tipos[t].setChecked(t in r['tipos'])
            for k,(c,u) in ps.items():
                a=r['campos'].get(t,{}).get(k,{})
                c.setCurrentIndex(max(0,c.findData(a.get('campo'))))
                u.setCurrentIndex(max(0,u.findData(a.get('unidade'))))

    def localizar_anterior(self):
        pasta=QFileDialog.getExistingDirectory(self,'Pacote exportado anteriormente')
        if pasta:
            self.anterior.setText(pasta)

    def localizar_observado(self):
        arq,_=QFileDialog.getOpenFileName(self,'CSV do modelo de destino','','CSV (*.csv)')
        if arq:self.observado.setText(arq)

    def escolher_conjuntos(self):
        ids=self.pagina._escolher_itens_integral('Conjuntos para este pacote',
            [(u,r['nome']) for u,r in self.conjuntos.items()])
        self.conjuntos_ids=ids
        self.status.setText(f'{len(ids)} conjuntos selecionados.')

    def _escolher_escopo(self):
        modo=self.escopo.currentData()
        macro=self.pagina.macro_integral or {}
        d=self.pagina.dados or {}
        if modo in ('CORREDORES','BLOCOS'):
            chave='corredores' if modo=='CORREDORES' else 'blocos'
            registros=[*macro.get(chave,()),*d.get('agrupamento' if modo=='CORREDORES' else 'blocos',{}).get(chave,())]
            if modo=='BLOCOS':
                registros.extend(macro.get('detalhados',()))
            grupos={r['uid']:r for r in registros}
            ids=self.pagina._escolher_itens_integral('Elementos do escopo',
                [(u,r.get('nome') or u[:10]) for u,r in grupos.items()])
            self.escopo_chaves=cm.por_segmentos(self.foto,{i for u in ids for i in grupos[u]['segmentos']})
        elif modo=='AREAS':
            ids=self.pagina._escolher_itens_integral('Áreas em interseção espacial',
                [(r['uid'],str(r.get('label') or r.get('id') or r['uid'][:10])) for r in self.foto.get('areas',())])
            partes={t['uid'] for t in self.foto['tubos'] if set(t.get('zonas_uids',())).intersection(ids)}
            self.escopo_chaves={('PIPE',r['uid']) for r in self.previa['pipes'] if r['parte'] in partes}
        elif modo=='CONJUNTOS':
            self.escolher_conjuntos()
            self.escopo_chaves={(r['tipo'],r['uid']) for u in self.conjuntos_ids for r in self.conjuntos[u]['membros']}
        else:
            self.selecao_resumo.setText('O escopo usa a condição cadastral e as origens selecionadas na prévia.')
            return
        self.selecao_resumo.setText(f'{len(self.escopo_chaves)} elementos selecionados.')

    def _escopo(self):
        modo=self.escopo.currentData()
        if modo=='COMPLETO':return None
        if modo=='HIPOTESE':
            return {('PIPE',r['uid']) for r in self.previa['pipes'] if r['participacao']=='INCLUIDO'}
        if modo=='ALCANCAVEL':
            if not self.previa['manifesto']['origens']:
                raise ValueError('Selecione origens válidas para usar a rede alcançável.')
            return {('PIPE',r['uid']) for r in self.previa['pipes'] if r['condicao_topologica']=='COM_ORIGEM'}
        if not self.escopo_chaves:
            raise ValueError('Escolha os elementos que serão exportados neste escopo.')
        return self.escopo_chaves

    def exportar(self):
        if self.pagina.foto is not self.foto or self.pagina._projeto()['uuid']!=self.projeto['uuid']:
            raise ValueError('O contexto mudou. Reabra o assistente.')
        perfil=self._perfil()
        escopo=self._escopo()
        cfg=dict(perfil=perfil,escopo=self.escopo.currentData(),tolerancia_m=self.tolerancia.value())
        anterior=self.anterior.text()
        observado=self.observado.text()
        if perfil['modo']=='ATUALIZAR' and not anterior:
            raise ValueError('Localize o pacote de referência para comparar a atualização.')
        formato=self.formato.currentData()
        sugestao=_pasta(self.projeto)
        if self.projeto.get('manifesto_wna'):
            sugestao.mkdir(parents=True,exist_ok=True)
        pasta=QFileDialog.getExistingDirectory(self,'Destino do pacote ModelBuilder',str(sugestao))
        if not pasta:return
        selecoes=[self.conjuntos[u] for u in self.conjuntos_ids]
        regra=self.atividade.currentData()
        base=self.pagina._complementos(True)
        projeto_uid=self.projeto['uuid']
        raiz=Path(self.projeto['manifesto_wna']).parent.resolve() if self.projeto.get('manifesto_wna') else None
        previa=self.previa
        def executar(parar,etapa):
            dados=previa
            if regra!='PREVIA':
                excecoes=previa['manifesto'].get('atividades_explicitas',{})
                dados=dict(previa,pipes=[dict(r,atividade=excecoes.get(r['original'],
                    'ATIVO' if regra=='HIPOTESE' and r['participacao']=='INCLUIDO' else 'A_DEFINIR'))
                    for r in previa['pipes']])
            if perfil['modo']=='ATUALIZAR':
                m0,originais=mb.ler_pacote(anterior)
                if m0['projeto']!=projeto_uid:
                    raise ValueError('O pacote anterior pertence a outro projeto.')
                cfg['componentes_anteriores']=originais
                cfg['referencia_anterior']=m0['assinatura_csv']
                if observado:cfg['observado']=conferir.ler_evidencia(observado)
            dst=cadastro.exportar(dados,Path(pasta),formato,parar,etapa,selecoes=selecoes,modelbuilder=cfg,escopo=escopo)
            m=json.loads((dst/'MODELBUILDER.json').read_text(encoding='utf-8'))
            relativo=bool(raiz and dst.resolve().is_relative_to(raiz))
            p=str(dst.resolve().relative_to(raiz)) if relativo else str(dst.resolve())
            r=pg.salvar_revisao(base,projeto_uid,'MODELBUILDER_EXPORTACAO',
               dict(projeto_uid=projeto_uid,topologia_uid=m['execucao'],pasta=p,relativo=relativo,
                    assinatura=m['assinatura_csv'],metadata=m,estado=m['estado']))
            return dst,r
        def pronto(rs):
            dst,r=rs
            texto=f"Pacote {r['uuid'][:8]} · {r['estado'].lower().replace('_',' ')}\n{dst}"
            self.pagina.status.setText(texto)
            if not sip.isdeleted(self):self.status.setText(texto)
        self.pagina.tarefa('Validar e exportar para ModelBuilder',executar,pronto)


class HistoricoModelBuilder(QDialog):
    def __init__(self,pagina,parent=None):
        super().__init__(parent or pagina)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Exportações e conferência WaterGEMS')
        self.pagina=pagina
        self.projeto=pagina._projeto()
        self.registros=_revisoes(pagina,'MODELBUILDER_EXPORTACAO')
        v=QVBoxLayout(self)
        self.lista=_combo((f"{r['data_utc'][:16]} · {r['estado']} · {u[:8]}",u) for u,r in reversed(list(self.registros.items())))
        v.addWidget(self.lista)
        self.texto=aviso()
        self.texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.texto)
        self.lista.currentIndexChanged.connect(self.descrever)
        botao(v,'Conferir CSV exportado do WaterGEMS…',self.ler)
        botao(v,'Fechar',self.reject)
        self.descrever()

    def descrever(self,*_):
        r=self.registros.get(self.lista.currentData())
        if not r:
            self.texto.setText('Nenhum pacote registrado no projeto.')
            return
        self.texto.setText(str(_pasta(self.projeto,r))+'\n'+r['estado'].replace('_',' ').capitalize()+
            ('\nConferência: '+r['relatorio'] if r.get('relatorio') else ''))

    def ler(self):
        r=self.registros.get(self.lista.currentData())
        if not r:return
        p=_pasta(self.projeto,r)
        if not p.is_dir():
            novo=QFileDialog.getExistingDirectory(self,'Localizar a pasta do pacote exportado')
            if not novo:return
            p=Path(novo)
        arq,_=QFileDialog.getOpenFileName(self,'CSV exportado das tabelas WaterGEMS',str(p),'CSV (*.csv)')
        if not arq:return
        modelo,ok=QInputDialog.getText(self,'Conferir importação','Identidade do modelo de destino')
        if not ok:return
        versao,ok=QInputDialog.getText(self,'Conferir importação','Versão exata do WaterGEMS')
        if not ok:return
        cenario,ok=QInputDialog.getText(self,'Conferir importação','Cenário e alternativa de atividade, se conferidos')
        if not ok:return
        base=self.pagina._complementos()
        projeto_uid=self.projeto['uuid']
        def executar(parar,etapa):
            etapa(0,'Conferindo chaves, nós, coordenadas e propriedades')
            meta,esperado=mb.ler_pacote(p)
            if meta['projeto']!=projeto_uid or meta['assinatura_csv']!=r['assinatura']:
                raise ValueError('O pacote não corresponde ao registro do projeto.')
            evidencias=conferir.ler_evidencia(arq)
            d=conferir.conferir(meta,esperado,evidencias,modelo,versao,cenario=cenario,cancelar=parar)
            destino=p/('Conferencia_'+uuid4().hex[:10])
            with TemporaryDirectory(prefix='.conferencia_',dir=p) as temporario:
                temp=Path(temporario)/'saida'
                temp.mkdir()
                data=datetime.now(timezone.utc).isoformat()
                d['sha256_evidencia']=conferir.salvar_tabela(temp/'correspondencias.gpkg',d,arq,data)
                d['data_utc']=data
                (temp/'reconciliacao.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
                publicar(temp,destino,parar)
            novo=pg.salvar_revisao(base,projeto_uid,'MODELBUILDER_EXPORTACAO',dict(r,estado=d['estado'],
                relatorio=destino.name+'/reconciliacao.json'),r['uuid'],r['rev'])
            return novo,destino
        def pronto(rs):
            novo,destino=rs
            self.pagina.status.setText(str(destino))
            if sip.isdeleted(self):return
            self.registros[novo['uuid']]=novo
            self.lista.setItemText(self.lista.findData(novo['uuid']),novo['estado'])
            self.descrever()
            self.texto.setText(self.texto.text()+'\n'+str(destino))
        self.pagina.tarefa('Conferir modelo WaterGEMS',executar,pronto)
