"""Reserva Labels únicos por projeto sem modificar os UIDs ou revisões anteriores."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from auditoria_fronteiras.modelos import verificar_cancelamento
from . import persistencia_grafo_gis as pg


PREFIXOS={'PIPE':'P','JUNCTION':'J','RESERVOIR':'R','TANK':'T','HYDRANT':'H'}
_ACEITO=re.compile(r'[A-Za-z0-9][A-Za-z0-9_ .-]{0,31}',re.ASCII)


def _adequado(s):
    return isinstance(s,str) and s==s.strip() and _ACEITO.fullmatch(s)


def validar_prefixos(prefixos):
    if set(prefixos)-PREFIXOS.keys() or any(not isinstance(v,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9]{0,5}',v)
                                           for v in prefixos.values()):
        raise ValueError('Os prefixos devem começar com uma letra e ter até seis letras ou algarismos ASCII.')


def _atribuir(elementos, existentes, prefixos, preservar, anteriores, cancelar):
    usados={r[0].casefold() for r in existentes.values()}
    alvos={r['uid']:r for r in elementos}
    if len(alvos)!=len(elementos):raise ValueError('Há mais de um elemento exportável com o mesmo WNA_UID.')
    novos={}
    reservas_anteriores=set()
    for u,nome in sorted(anteriores.items()):
        verificar_cancelamento(cancelar)
        if not _adequado(nome) or nome.casefold() in reservas_anteriores:
            raise ValueError('O pacote de referência contém Labels inválidos ou ambíguos.')
        reservas_anteriores.add(nome.casefold())
        if u in existentes:
            if existentes[u][0]!=nome:
                raise ValueError(f'O Label reservado para {u} diverge do pacote de referência. Reconcilie os Labels antes de atualizar.')
        elif nome.casefold() in usados:
            raise ValueError(f'O Label do pacote de referência para {u} já está reservado para outra identidade.')
        elif u in alvos:
            r=alvos[u]
            novos[u]=(nome,r['tipo'],r.get('original'))
    usados.update(reservas_anteriores)
    pendentes=[]
    cont=Counter(r['label'].casefold() for r in elementos if _adequado(r.get('label')))
    for u,r in sorted(alvos.items()):
        verificar_cancelamento(cancelar)
        if u in existentes or u in novos:continue
        original=r.get('label')
        if preservar and _adequado(original) and cont[original.casefold()]==1 and original.casefold() not in usados:
            novos[u]=(original,r['tipo'],r.get('original'))
            usados.add(original.casefold())
        else:
            pendentes.append((u,r))
    indices=Counter()
    for u,r in pendentes:
        verificar_cancelamento(cancelar)
        prefixo=prefixos[r['tipo']]
        chave=prefixo.casefold()
        while True:
            indices[chave]+=1
            label=f'{prefixo}-{indices[chave]:06d}'
            if label.casefold() not in usados:break
        usados.add(label.casefold())
        novos[u]=(label,r['tipo'],r.get('original'))
    return {u:(existentes.get(u) or novos[u])[0] for u in alvos},novos


def reservar(elementos,projeto,contexto,*,base=None,gravar=False,prefixos=None,preservar=True,anteriores=None,cancelar=None):
    prefixos=prefixos or {}
    validar_prefixos(prefixos)
    regras={**PREFIXOS,**prefixos}
    if base is None:
        return _atribuir(elementos,{},regras,preservar,anteriores or {},cancelar)[0]
    with closing(sqlite3.connect(base)) as con, con:
        if gravar:con.execute('BEGIN IMMEDIATE')
        pg._identidade(con,projeto)
        tabela=con.execute("SELECT 1 FROM sqlite_master WHERE name='WNA_ROTULOS'").fetchone()
        existentes={u:(l,t,o) for u,l,t,o in con.execute(
            'SELECT uid,label,tipo,original FROM WNA_ROTULOS')} if tabela else {}
        saida,novos=_atribuir(elementos,existentes,regras,preservar,anteriores or {},cancelar)
        if gravar and novos:
            if not tabela:
                pasta=Path(base).parent/'backups'
                pasta.mkdir(exist_ok=True)
                backup=pasta/('antes_rotulos_'+uuid4().hex[:10]+'.gpkg')
                with closing(sqlite3.connect(base)) as anterior,closing(sqlite3.connect(backup)) as destino:
                    anterior.backup(destino,pages=128,progress=lambda *_:verificar_cancelamento(cancelar))
                    pg._verificar(destino)
                con.execute('''CREATE TABLE WNA_ROTULOS (fid INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
                    label TEXT COLLATE NOCASE NOT NULL UNIQUE,tipo TEXT NOT NULL,original TEXT,
                    contexto TEXT,data_utc TEXT,estado TEXT NOT NULL)''')
                pg._registrar(con,'WNA_ROTULOS')
            data=pg._agora()
            con.executemany('INSERT INTO WNA_ROTULOS (uid,label,tipo,original,contexto,data_utc,estado) VALUES (?,?,?,?,?,?,?)',
                           ((u,*v,contexto,data,'RESERVADO') for u,v in novos.items()))
        return saida
