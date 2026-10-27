"""Relatórios de acompanhamento; nunca arquivos de edição do modelo."""
from collections import Counter
from datetime import datetime
import csv
import json
from pathlib import Path
from uuid import uuid4
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.persistencia import exportar_gpkg
from .decisoes import existe,propostas,CONCLUSOES,MODOS
from .diagnosticos import catalogar
from .saidas_integracao import tabelas_integracao
from .saidas import exportar_tabelas_xlsx


def tabelas_decisoes(base,pacote):
    ig=pacote['resultado']['meta']['uid'];casos=catalogar(pacote)
    with abrir_ro(base) as con:
        con.row_factory=__import__('sqlite3').Row
        hs=[dict(r) for r in con.execute('SELECT * FROM IGD_REVISOES WHERE ig_uid=? ORDER BY rowid',(ig,))] if existe(con) else []
        comps=[json.loads(r[0]) for r in con.execute('SELECT dados FROM IGD_COMPARACOES WHERE ig_destino=? ORDER BY rowid',(ig,))] if existe(con) else []
        vals=[json.loads(r[0]) for r in con.execute('SELECT v.dados FROM IGD_VALIDACOES v JOIN IGD_PROPOSTAS p ON p.prop_uid=v.prop_uid WHERE p.ig_uid=? ORDER BY v.rowid',(ig,))] if existe(con) else []
        recs=[dict(r) for r in con.execute('SELECT r.* FROM IGD_RECONCILIACOES r JOIN IGD_COMPARACOES c ON c.comp_uid=r.comp_uid WHERE c.ig_destino=? ORDER BY r.rowid',(ig,))] if existe(con) else []
    ps=propostas(base,ig);atuais={(h['occ_uid'],h['modo']):h for h in hs};linhas=[];resumo=[]
    for modo in MODOS:
        for c in casos:
            h=atuais.get((c['uid'],modo),{})
            linhas.append((c['uid'],c['titulo'],modo,h.get('situacao','PENDENTE'),h.get('conclusao','NÃO AVALIADO'),
                h.get('justificativa',''),h.get('responsavel',''),h.get('data_utc',''),h.get('fonte',''),h.get('natureza','INDEFINIDO'),h.get('evidencia','')))
        hm=[h for h in atuais.values() if h['modo']==modo];pm=[p for p in ps if p['modo']==modo]
        resumo += [(modo,'Ocorrências do catálogo',len(casos)),(modo,'Com revisão topológica registrada',len(hm)),
            (modo,'Com situação diferente de PENDENTE',sum(h['situacao']!='PENDENTE' for h in hm)),
            (modo,'Conectividade correta declarada',sum(h['conclusao']=='CONECTIVIDADE CORRETA' for h in hm)),
            (modo,'Ocorrências com proposta',len({p['occ_uid'] for p in pm})),(modo,'Propostas',len(pm)),
            (modo,'Propostas validadas explicitamente',sum(p['atual']['situacao']=='VALIDADA' for p in pm))]
    tabelas={
        'RESUMO_REVISOES':(('PERSPECTIVA','INDICADOR','QUANTIDADE'),resumo),
        'DECISOES_TOPOLOGICAS':(('OCC_UID','DIAGNOSTICO','PERSPECTIVA','SITUACAO','CONCLUSAO','JUSTIFICATIVA','RESPONSAVEL','DATA_UTC','FONTE','NATUREZA','EVIDENCIA'),linhas),
        'HIST_DECISOES':(('REV_UID','OCC_UID','PERSPECTIVA','REV_ANTERIOR','SITUACAO_ANTES','SITUACAO','CONCLUSAO','JUSTIFICATIVA','RESPONSAVEL','DATA_UTC','FONTE','NATUREZA','EVIDENCIA'),[
            tuple(h[k] for k in ('rev_uid','occ_uid','modo','anterior','situacao_anterior','situacao','conclusao','justificativa','responsavel','data_utc','fonte','natureza','evidencia')) for h in hs]),
        'PROPOSTAS_INTERVENCAO':(('PROP_UID','OCC_UID','PERSPECTIVA','TIPO','SITUACAO','INCOMPLETA','DESCRICAO','JUSTIFICATIVA','REQUISITOS','RESPONSAVEL','DATA_UTC','EVIDENCIA'),[
            (p['prop_uid'],p['occ_uid'],p['modo'],*[p['atual'][k] for k in ('tipo','situacao','incompleta','descricao','justificativa','requisitos','responsavel','data_utc','evidencia')]) for p in ps]),
        'HIST_PROPOSTAS':(('PROP_UID','HIST_UID','ANTERIOR','SITUACAO_ANTES','SITUACAO','TIPO','DESCRICAO','JUSTIFICATIVA','REQUISITOS','RESPONSAVEL','DATA_UTC','EVIDENCIA','CONFIRMACAO','VALIDACAO_MANUAL'),[
            (p['prop_uid'],*[h[k] for k in ('hist_uid','anterior','situacao_anterior','situacao','tipo','descricao','justificativa','requisitos','responsavel','data_utc','evidencia','confirmacao','validacao_manual')]) for p in ps for h in p['historico']]),
        'ELEMENTOS_PROPOSTAS':(('PROP_UID','HIST_UID','PROJETO','WG_ID','LABEL','TIPO'),[
            (p['prop_uid'],h['hist_uid'],e['projeto'],e['wg_id'],e['label'],e['tipo']) for p in ps for h in p['historico'] for e in h['elementos']]),
        'COMPARACOES_VERSOES':(('COMP_UID','ORIGEM','DESTINO','PERSPECTIVA','OCC_ANTERIOR','OCC_ATUAIS','CLASSIFICACAO','REAVALIAR','MOTIVOS'),[
            (c['uid'],c['origem'],c['destino'],c['modo'],l['origem'],'; '.join(l['destinos']),l['classe'],l['reavaliar'],l['motivos']) for c in comps for l in c['linhas']]),
        'RESUMO_COMPARACOES':(('COMP_UID','PERSPECTIVA','VERSAO','INDICADOR','QUANTIDADE'),[
            (c['uid'],c['modo'],v,k,n) for c in comps for v in ('origem','destino') for k,n in c.get('resumo_'+v,{}).items()]+[
            (c['uid'],c['modo'],'confronto',k,n) for c in comps for k,n in c['contagens'].items()]),
        'RECONCILIACOES_TOPOLOGICAS':(('REC_UID','COMP_UID','ITEM','OCC_DESTINO','REV_UID','RESPONSAVEL','JUSTIFICATIVA','EVIDENCIA','DATA_UTC'),[
            tuple(r[k] for k in ('rec_uid','comp_uid','ordem','occ_destino','rev_uid','responsavel','justificativa','evidencia','data_utc')) for r in recs]),
        'VALIDACOES_PROPOSTAS':(('VAL_UID','PROP_UID','HIST_UID','ORIGEM','DESTINO','PERSPECTIVA','RESULTADO','CENARIOS_COMPARAVEIS','IDENTIDADES_PRESERVADAS','DATA_UTC'),[
            tuple(v[k] for k in ('uid','prop_uid','hist_uid','origem','destino','modo','resultado','cenarios_comparaveis','identidades_preservadas','data_utc')) for v in vals])}
    from .decisoes import registros
    rs=registros(base,ig)
    tabelas['ANOTACOES_PRELIMINARES']=(('REG_UID','OCC_UID','PERSPECTIVA','TIPO','CLASSIFICACAO','OBSERVACAO','RESPONSAVEL','DATA_UTC','ASSINATURA'),[tuple(r[k] for k in ('reg_uid','occ_uid','modo','tipo','classificacao','observacao','responsavel','data_utc','assinatura')) for r in rs])
    from . import operacional as op
    from .filtros import ContextoFiltros
    hh=op.historico(base,ig);atuais_op={(h['occ_uid'],h['modo']):h for h in hh};contexto=ContextoFiltros(pacote);contexto.restaurar_persistidas(base)
    campos=('UID','OCC_UID','PERSPECTIVA','ANTERIOR','RESULTADO','MOTIVO','OBSERVACAO','PRIOR_AUTO','CRITERIO','PRIOR_TRAB','TOPO_UID','CENARIO','DATA_UTC')
    chaves=('uid','occ_uid','modo','anterior','resultado','motivo','observacao','prioridade_auto','criterio_auto','prioridade_trabalho','topo_uid','cenario','data_utc')
    tabelas['HIST_ANALISES']=(campos,[tuple(h[k] for k in chaves) for h in hh])
    linhas=[];res=[]
    for modo in MODOS:
        for caso in casos:
            h=atuais_op.get((caso['uid'],modo),{});sugestao,criterio=op.sugerir(caso,contexto)
            linhas.append((caso['uid'],caso['titulo'],modo,op.estado(h),h.get('resultado','PENDENTE'),h.get('motivo',''),h.get('observacao',''),h.get('prioridade_auto',sugestao),h.get('criterio_auto',criterio),h.get('prioridade_trabalho'),h.get('data_utc','')))
        res.extend((modo,estado,sum(op.estado(atuais_op.get((caso['uid'],modo)))==estado for caso in casos)) for estado in op.ESTADOS)
    tabelas['RESULTADOS_INVESTIGATIVOS']=(('OCC_UID','DIAGNOSTICO','PERSPECTIVA','ANDAMENTO','RESULTADO','MOTIVO','OBSERVACAO','PRIOR_AUTO','CRITERIO','PRIOR_TRAB','DATA_UTC'),linhas)
    tabelas['RESUMO_ANALISES']=(('PERSPECTIVA','ESTADO','QUANTIDADE'),res)
    tabelas['RELACOES_PARA_FILTROS']=(('LOCAL_UID','AREA_UID','EVENTO_UID','RELACAO','ORIGEM'),[(r['local'],r['area'],r['evento'],r['relacao'],r['origem']) for r in contexto.relacoes])
    return tabelas


def exportar_acompanhamento(base,pacote,pasta,xlsx=True,gpkg=False,shp=False):
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=False);novas=tabelas_decisoes(base,pacote)
    if xlsx:
        abas=tabelas_integracao(pacote);abas.update(novas)
        exportar_tabelas_xlsx(abas,pasta/'ACOMPANHAMENTO.xlsx',larguras={'DIAGNOSTICO':60,'JUSTIFICATIVA':65,'EVIDENCIA':65,'DESCRICAO':65,'MOTIVOS':65,'REQUISITOS':65})
    for nome,(cab,linhas) in novas.items():
        with (pasta/(nome+'.csv')).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';');w.writerow(cab);w.writerows(linhas)
    if gpkg:exportar_gpkg(pasta/'ACOMPANHAMENTO.gpkg',pacote['dossie'],base_origem=base)
    avisos=[]
    if shp:
        from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsGeometry
        from qgis.PyQt.QtCore import QVariant
        from .saidas import exportar_geografico
        c=QgsVectorLayer('Point?crs='+pacote['dossie']['contexto']['parametros']['crs'],'DECISOES_OCORRENCIAS','memory')
        c.dataProvider().addAttributes([QgsField(n,QVariant.String,len=l) for n,l in [('FEAT_UID',80),('OCC_UID',80),('IG_UID',40),('MODO',30),('SITUACAO',80),('CONCLUSAO',80)]]);c.updateFields()
        locais={l['uid']:l for l in pacote['resultado']['locais']};casos={o['uid']:o for o in catalogar(pacote)};fs=[]
        from .operacional import indice,estado
        resultados_op=indice(base,pacote['resultado']['meta']['uid'])
        for row in novas['DECISOES_TOPOLOGICAS'][1]:
            o=casos[row[0]];g=None
            if o['local_uid']:
                rr=locais[o['local_uid']]['registro'];g=QgsGeometry.fromWkt(f"POINT({rr['X']} {rr['Y']})")
            elif o['tipo']=='GIS':
                pend=next((p for p in pacote['resultado']['pendencias'] if p['gis_uid']==o['chave']),None)
                if pend and pend['geometria_wkb']:
                    original=QgsGeometry();original.fromWkb(bytes.fromhex(pend['geometria_wkb']));g=original.centroid()
            elif pacote.get('geometrias'):
                gs=[pacote['geometrias'][i] for i in o['wg_ids'] if i in pacote['geometrias']]
                if gs:g=QgsGeometry.collectGeometry(gs).centroid()
            if g is None or g.isEmpty():avisos.append('Sem representação espacial segura: '+row[0]+' / '+row[2]);continue
            from .decisoes import digest
            f=QgsFeature(c.fields());f.setGeometry(g);h=resultados_op.get((row[0],row[2]));f.setAttributes([digest([row[0],row[2]]),row[0],pacote['resultado']['meta']['uid'],row[2],estado(h) if h else row[3],h['resultado'] if h else row[4]]);fs.append(f)
        c.dataProvider().addFeatures(fs);c.updateExtents();exportar_geografico([c],pasta/'SHP','SHP',campo_chave='FEAT_UID')
        (pasta/'SHP/DICIONARIO_DECISOES.json').write_text(json.dumps(dict(FEAT_UID='Chave desta representação',OCC_UID='Ocorrência investigativa',IG_UID='Execução integrada',MODO='Perspectiva',SITUACAO='Andamento investigativo; legado administrativo quando não houver novo registro',CONCLUSAO='Resultado investigativo ou conclusão histórica; não comprova condição hidráulica',geometria='Ponto original do local ou centroide de elementos com CRS validado. Auditoria, sem alterações hidráulicas.'),ensure_ascii=False,indent=2),encoding='utf8')
    (pasta/'METADADOS.json').write_text(json.dumps(dict(execucao=pacote['resultado']['meta']['uid'],data=datetime.now().astimezone().isoformat(),avisos=avisos,intervencoes_executadas=False),ensure_ascii=False,indent=2),encoding='utf8')
    return pasta


from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QCheckBox,QPushButton,QFileDialog,QMessageBox
class DialogExportarDecisoes(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.setWindowTitle('Exportar acompanhamento');v=QVBoxLayout(self)
        self.xlsx=QCheckBox('XLSX e tabelas de acompanhamento');self.xlsx.setChecked(True);v.addWidget(self.xlsx)
        self.gpkg=QCheckBox('Cópia completa GPKG com históricos');v.addWidget(self.gpkg)
        self.shp=QCheckBox('SHP de ocorrências espaciais — sem intervenções');v.addWidget(self.shp)
        b=QPushButton('Escolher pasta e gerar nova exportação…');b.clicked.connect(lambda checked=False:self.exportar());v.addWidget(b)
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)
    from auditoria_fronteiras.atividade import acompanhada
    @acompanhada('Exportando acompanhamento e históricos')
    def exportar(self):
        if not any(w.isChecked() for w in (self.xlsx,self.gpkg,self.shp)):QMessageBox.warning(self,'Formato','Selecione pelo menos um formato.');return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de destino')
        if not pasta:return False
        try:
            destino=Path(pasta)/('acompanhamento_'+uuid4().hex[:10]);exportar_acompanhamento(self.painel.base,self.painel.pacote,destino,self.xlsx.isChecked(),self.gpkg.isChecked(),self.shp.isChecked())
            QMessageBox.information(self,'Exportação concluída',str(destino));self.accept()
        except Exception as e:
            from auditoria_fronteiras.atividade import falha
            falha(self,e);QMessageBox.warning(self,'Exportação incompleta',str(e))
