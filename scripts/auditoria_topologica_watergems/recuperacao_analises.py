"""Inventário somente leitura; não confunde visibilidade com perda de registros."""
import json
import sqlite3
from .decisoes import abrir_ro,registros,historico
from .operacional import historico as analises
from .conjuntos_investigacao import atuais


def inventariar(base,pacote,casos=()):
    ig=pacote['resultado']['meta']['uid'];hs=analises(base,ig);notas=registros(base,ig);heads={(h['occ_uid'],h['modo']):h for h in hs};casos={c['uid']:c for c in casos};armazenados={}
    with abrir_ro(base) as c:
        c.row_factory=sqlite3.Row
        revisoes=[dict(r) for r in c.execute('SELECT * FROM IGD_REVISOES WHERE ig_uid=? ORDER BY rowid',(ig,))] if c.execute("select 1 from sqlite_master where name='IGD_REVISOES'").fetchone() else []
        faltantes=sorted({r['occ_uid'] for r in hs+notas+revisoes}-set(casos))
        if faltantes and c.execute("select 1 from sqlite_master where name='IGD_OCORRENCIAS'").fetchone():
            for n in range(0,len(faltantes),500):
                lote=faltantes[n:n+500];sql='SELECT occ_uid,modo,dados FROM IGD_OCORRENCIAS WHERE ig_uid=? AND occ_uid IN ('+','.join('?' for _ in lote)+')'
                armazenados.update({(r['occ_uid'],r['modo']):json.loads(r['dados']) for r in c.execute(sql,[ig]+lote)})
        quantidades={}
        if c.execute("select 1 from sqlite_master where name='IGD_OBJETOS'").fetchone():
            quantidades=dict(c.execute('''SELECT o.tipo,count(*) FROM IGD_OBJETOS o JOIN IGD_OBJ_HIST h ON h.obj_uid=o.uid WHERE o.ig_uid=? AND h.excluido=0 AND NOT EXISTS(SELECT 1 FROM IGD_OBJ_HIST n WHERE n.obj_uid=h.obj_uid AND n.rowid>h.rowid) GROUP BY o.tipo''',(ig,)).fetchall())
    linhas=[]
    for h in hs:
        uid=h['occ_uid'];modo=h['modo']
        caso=casos.get(uid) or armazenados.get((uid,modo),{})
        linhas.append(dict(occ_uid=uid,modo=modo,titulo=caso.get('titulo',uid)+(' [histórico]' if heads[uid,modo]['uid']!=h['uid'] else ''),resultado=h['resultado'],observacao=h['observacao'],motivo=h['motivo'],data=h['data_utc'],origem='RESULTADO',registro_uid=h['uid'],localizavel=uid in casos))
    for n in notas:
        uid=n['occ_uid'];modo=n['modo'];caso=casos.get(uid) or armazenados.get((uid,modo),{})
        linhas.append(dict(occ_uid=uid,modo=modo,titulo=caso.get('titulo',uid),resultado=n.get('classificacao') or n.get('tipo','Anotação'),observacao=n.get('observacao',''),motivo='',data=n['data_utc'],origem='ANOTACAO_LEGADA',registro_uid=n['reg_uid'],localizavel=uid in casos))
    for n in revisoes:
        uid=n['occ_uid'];modo=n['modo'];caso=casos.get(uid) or armazenados.get((uid,modo),{})
        linhas.append(dict(occ_uid=uid,modo=modo,titulo=caso.get('titulo',uid)+' [revisão legada]',resultado=n['conclusao'],observacao=n['justificativa'],motivo=n['situacao'],data=n['data_utc'],origem='REVISAO_LEGADA',registro_uid=n['rev_uid'],localizavel=uid in casos))
    return dict(nome=pacote['resultado']['meta'].get('nome') or 'Investigação',ig_uid=ig,topo_uid=pacote['resultado']['meta']['topologia']['execucao_uid'],
        locais_automaticos=len(pacote['resultado']['locais']),locais_manuais=quantidades.get('LOCAL_MANUAL',0),conjuntos=quantidades.get('REDE_PRINCIPAL',0),
        analises=len(hs),contextos_analisados=len(heads),revisoes_legadas=len(revisoes),observacoes=sum(bool(h.get('observacao','').strip()) for h in hs)+sum(bool(n.get('observacao','').strip()) for n in notas)+sum(bool(n['justificativa'].strip()) for n in revisoes),
        anotacoes_legadas=len(notas),por_perspectiva={modo:sum(h['modo']==modo for h in hs) for modo in ('ESTRUTURAL','TODAS_VALVULAS_ABERTAS')},linhas=linhas)


def abrir_consulta(painel):
    from qgis.PyQt import sip
    existente=getattr(painel,'_consulta_analises',None)
    if existente is not None and not sip.isdeleted(existente) and existente.isVisible():existente.raise_();existente.activateWindow();return existente
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QPushButton,QAbstractItemView,QMessageBox
    from auditoria_fronteiras.ui_comum import adaptar_janela
    inv=inventariar(painel.base,painel.pacote,painel.casos);d=QDialog(painel);d.setAttribute(Qt.WA_DeleteOnClose,True);d.setWindowTitle('Análises salvas · '+inv['nome']+' · topologia '+inv['topo_uid'][:8]);d.resize(1000,600);v=QVBoxLayout(d)
    aviso=QLabel(f"{inv['analises']} registros de análise, {inv['observacoes']} registros com observações. Todas as perspectivas desta investigação; nenhuma transferência de conclusão.");aviso.setWordWrap(True);v.addWidget(aviso)
    busca=QLineEdit();busca.setPlaceholderText('Buscar título, observação, resultado ou UUID');v.addWidget(busca);t=QTableWidget(len(inv['linhas']),6);t.setHorizontalHeaderLabels(['Ocorrência','Perspectiva','Resultado / tipo','Motivo','Observação','Data']);t.setEditTriggers(QAbstractItemView.NoEditTriggers);t.setSelectionBehavior(QAbstractItemView.SelectRows);v.addWidget(t,1)
    for n,r in enumerate(inv['linhas']):
        for c,k in enumerate(('titulo','modo','resultado','motivo','observacao','data')):
            i=QTableWidgetItem(str(r.get(k) or ''));i.setToolTip(i.text()+'\nUUID: '+r['occ_uid']);i.setData(Qt.UserRole,r);t.setItem(n,c,i)
    t.setSortingEnabled(True);t.setColumnWidth(0,200);t.setColumnWidth(4,350)
    def filtrar():
        texto=busca.text().casefold()
        for n in range(t.rowCount()):t.setRowHidden(n,not any(texto in t.item(n,c).text().casefold() for c in range(t.columnCount())) and texto not in t.item(n,0).data(Qt.UserRole)['occ_uid'])
    busca.textChanged.connect(filtrar);acoes=QHBoxLayout();v.addLayout(acoes);abrir=QPushButton('Abrir ocorrência nesta perspectiva');acoes.addWidget(abrir)
    def escolher():
        if t.currentRow()<0:return
        r=t.item(t.currentRow(),0).data(Qt.UserRole)
        if not r['localizavel']:QMessageBox.information(d,'Histórico preservado','O registro pertence a um contexto antigo que não está na lista atual. O texto permanece disponível nesta consulta e nas exportações; não será associado por proximidade.');return
        if painel.mostrar_registro_salvo(r['occ_uid'],r['modo']):d.accept()
    abrir.clicked.connect(escolher);fechar=QPushButton('Fechar');fechar.clicked.connect(d.reject);acoes.addWidget(fechar);adaptar_janela(d);painel._consulta_analises=d;d.show();return d
