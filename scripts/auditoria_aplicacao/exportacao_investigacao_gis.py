"""Tabelas de acompanhamento separadas dos diagnósticos geométricos."""
import csv
from pathlib import Path
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.revisoes_ocorrencias import existe
from .investigacao_gis import IndiceInvestigacao


def exportar_tabelas(dossie,pasta,base):
    from auditoria_fronteiras.persistencia import carregar_execucao
    def escrever(nome,colunas,linhas):
        with (Path(pasta)/nome).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(colunas);w.writerows(linhas)
    with abrir_ro(base) as con:
        import sqlite3
        con.execute('BEGIN');con.row_factory=sqlite3.Row
        atual=carregar_execucao(base,dossie['execucao_uid'],conexao=con)
        rs=[dict(r) for r in con.execute('SELECT * FROM REVISOES_OCORRENCIAS WHERE exe_uid=? ORDER BY rowid',(dossie['execucao_uid'],))] if existe(con) else []
        revs={r['evt_uid']:r for r in rs}
        if {l['uid']:l['revisao'].get('uid') for l in atual['locais']}!={l['uid']:l['revisao'].get('uid') for l in dossie['locais']} or {u:r['rev_uid'] for u,r in revs.items()}!={u:r['rev_uid'] for u,r in dossie.get('revisoes_ocorrencias',{}).items()}:
            raise ValueError('As decisões mudaram em outra sessão. Reabra o trabalho antes de exportar; saídas anteriores preservadas.')
        indice=IndiceInvestigacao(atual,revs)
        escrever('RELEVANCIA_EVENTOS.csv',['EXE_UID','EVT_UID','CLASSIFICACAO_GEOMETRICA','RELEVANCIA','MOTIVO','CRITERIO','REGRA','ASSINATURA_ENTRADA'],
            ((atual['execucao_uid'],e['uid'],e['tecnico']['classificacao'],r['categoria'],r['motivo'],r['criterio'],r['regra'],r['assinatura_entrada'])
             for e in atual['eventos'] for r in (indice.relevancias[e['uid']],)))
        escrever('SITUACOES_LOCAIS.csv',['EXE_UID','LOC_UID','LOCAL','SITUACAO_AGRUPAMENTO','SITUACAO_ACOMPANHAMENTO','OBSERVACAO'],
            ((atual['execucao_uid'],l['uid'],l['registro']['LOCAL'],l['revisao']['situacao'],indice.situacao(l['uid']),l['revisao']['observacoes']) for l in atual['locais']))
        cols=['rev_uid','exe_uid','evt_uid','situacao','observacoes','data_utc','anterior_uid']
        escrever('HISTORICO_OCORRENCIAS.csv',cols,([r.get(k) for k in cols] for r in rs))
        escrever('DECISOES_OCORRENCIAS.csv',cols,([r.get(k) for k in cols] for r in revs.values()))
        cur=con.execute('SELECT * FROM REVISOES WHERE exe_uid=? ORDER BY rowid',(dossie['execucao_uid'],))
        escrever('HISTORICO_LOCAIS.csv',[c[0] for c in cur.description],cur)


def copiar_gpkg(base,temporario,exe,cancelar):
    import sqlite3
    from contextlib import closing
    if Path(temporario).exists():raise FileExistsError(temporario)
    with abrir_ro(base) as origem,closing(sqlite3.connect(temporario)) as copia:
        def progresso(*_):
            if cancelar():raise InterruptedError('Exportação cancelada.')
        origem.backup(copia,pages=256,progress=progresso)
        if copia.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Integridade da cópia não confirmada.')
        if not copia.execute('SELECT 1 FROM EXECUCOES WHERE exe_uid=?',(exe,)).fetchone():raise ValueError('Execução ausente na cópia.')
        from auditoria_fronteiras.persistencia import carregar_execucao
        from .relevancia_gis import calcular
        d=carregar_execucao(temporario,exe,conexao=copia)
        copia.execute('CREATE TABLE IF NOT EXISTS WNA_RELEVANCIA_EVENTOS (exe_uid TEXT,evt_uid TEXT,categoria TEXT,motivo TEXT,criterio TEXT,regra TEXT,assinatura_entrada TEXT,PRIMARY KEY(exe_uid,evt_uid))')
        copia.executemany('INSERT OR REPLACE INTO WNA_RELEVANCIA_EVENTOS VALUES (?,?,?,?,?,?,?)',
            ((exe,u,r['categoria'],r['motivo'],r['criterio'],r['regra'],r['assinatura_entrada']) for u,r in calcular(d).items()))
        if cancelar():raise InterruptedError('Exportação cancelada.')
        copia.commit()
