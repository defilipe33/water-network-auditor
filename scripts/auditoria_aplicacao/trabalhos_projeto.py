"""Referências de trabalhos do projeto e verificação explícita de integridade."""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import sqlite3

from auditoria_fronteiras.modelos import verificar_cancelamento
from auditoria_fronteiras.versoes import abrir_ro


ROTULOS = {
    'TOPOLOGIA_GIS': 'Conectividade GIS', 'ESTRUTURA_GIS': 'Redes estruturantes GIS',
    'AUDITORIA_GIS': 'Auditoria GIS', 'INTEGRADA': 'Investigação integrada',
    'TOPOLOGIA_WG': 'Topologia WaterGEMS',
}
TABELAS = {'TOPOLOGIA_GIS': 'TG_EXECUCAO', 'ESTRUTURA_GIS': 'TG_ESTRUTURA'}
CAMPOS = ('uuid','tipo','base','nome','data','versao','situacao','projeto_uid','hipotese_uid',
          'hipotese_nome','hipotese_rev','topologia_uid','referencia','componentes','origens',
          'conexoes','corredores','eventos','locais','cenario','modelo_uid','modelo_rev')


def chave(r):
    return r['tipo'], r['uuid']


def referencia(r):
    return {k:r[k] for k in CAMPOS if k in r}


def resumo_gis(d):
    foto = d.get('foto', d)
    hip = foto.get('hipotese') or {}
    return dict(hipotese_uid=hip.get('uuid'), hipotese_nome=hip.get('nome'), hipotese_rev=hip.get('rev'),
                modelo_rev=foto.get('modelo_rev'), topologia_uid=d.get('topologia_uid'),
                referencia=d.get('referencia'), componentes=len(foto.get('componentes', ())),
                origens=len(d.get('fontes', ())) if 'foto' in d else len(foto.get('origens_validas', ())),
                conexoes=sum(r.get('tipo')=='CONEXAO' for r in foto.get('participantes', ())),
                corredores=len(d.get('agrupamento', {}).get('corredores', ())))


def resumo_legado(con, tabela, uid):
    """Lê campos de uma fotografia anterior sem materializá-la em Python."""
    prefixo = '$.foto' if tabela=='TG_ESTRUTURA' else '$'
    hip = prefixo+'.hipotese.'
    caminhos = [hip+'uuid',hip+'nome',hip+'rev',prefixo+'.modelo_rev','$.topologia_uid','$.referencia',
                prefixo+'.componentes','$.fontes' if tabela=='TG_ESTRUTURA' else '$.origens_validas',
                '$.agrupamento.corredores',prefixo+'.resolucoes_conexoes']
    vals = con.execute(f"""
        SELECT json_extract(snapshot, ?), json_extract(snapshot, ?), json_extract(snapshot, ?),
            json_extract(snapshot, ?), json_extract(snapshot, ?), json_extract(snapshot, ?),
            json_array_length(snapshot, ?), json_array_length(snapshot, ?), json_array_length(snapshot, ?),
            (SELECT COUNT(*) FROM json_each(snapshot, ?))
        FROM {tabela} WHERE uuid=?""", (*caminhos,uid)).fetchone()
    nomes = ('hipotese_uid','hipotese_nome','hipotese_rev','modelo_rev','topologia_uid','referencia',
             'componentes','origens','corredores','conexoes')
    return dict(zip(nomes, vals)) if vals else {}


def assinatura(caminho):
    s=Path(caminho).stat()
    wal=Path(str(caminho)+'-wal')
    w=wal.stat() if wal.exists() else None
    return s.st_size,s.st_mtime_ns,(w.st_size,w.st_mtime_ns) if w else None


@lru_cache(maxsize=512)
def _identificar(caminho, marca, legado):
    from auditoria_topologica_watergems.gerenciamento import identificar
    return identificar(caminho, detalhes_legados=legado)


def identificar(caminho, *, legado=False):
    caminho=str(Path(caminho).resolve())
    return [dict(r) for r in _identificar(caminho,assinatura(caminho),legado)]


def metadados(projeto_uid, r, *, caminho=None, legado=False):
    base=Path(caminho or r['base'])
    alvo=next((x for x in identificar(base,legado=legado) if chave(x)==chave(r)),None)
    if alvo is None:
        raise ValueError(f'{base} não contém {r["tipo"]} com UUID {r["uuid"]}.')
    if alvo.get('projeto_uid') and alvo['projeto_uid']!=projeto_uid:
        raise ValueError(f'{base} pertence a outro projeto.')
    if alvo['tipo'] in TABELAS and alvo.get('versao')!=1:
        raise ValueError(f'{base} usa um esquema GIS incompatível.')
    return alvo


def conferir(projeto_uid,r,caminho=None):
    from .contexto_trabalho import validar_registro
    alvo=metadados(projeto_uid,r,caminho=caminho,legado=True)
    integridade=validar_registro(alvo)
    if not integridade['valido']:
        raise ValueError(f"{alvo['base']} · {integridade['erro']}")
    if alvo['tipo'] in TABELAS:
        tabela=TABELAS[alvo['tipo']]
        with abrir_ro(alvo['base']) as con:
            interno=con.execute(f"""SELECT json_extract(snapshot,'$.uuid'),
                json_extract(snapshot,'$.projeto_uid'),json_extract(snapshot,'$.topologia_uid'),
                json_extract(snapshot,'$.foto.uuid'),json_extract(snapshot,'$.foto.projeto_uid')
                FROM {tabela} WHERE uuid=?""",(alvo['uuid'],)).fetchone()
        if (interno is None or interno[:2]!=(alvo['uuid'],projeto_uid) or
                (tabela=='TG_ESTRUTURA' and (not interno[2] or interno[3:]!=(interno[2],projeto_uid)))):
            raise ValueError(f"{alvo['base']} · Fotografia interna diverge da identidade do trabalho.")
    return alvo


def registros(projeto, catalogo=(), adicionais=None):
    """Consulta de lista baseada em referências e índice, sem abrir fotografias."""
    if not projeto:
        fontes=catalogo
    else:
        indice={(chave(r),str(Path(r['base']).resolve())):r for r in catalogo}
        for r in catalogo:
            for c in r.get('caminhos', ()):
                indice.setdefault((chave(r),str(Path(c).resolve())),r)
        fontes=[]
        for r in projeto.get('bases', ()):
            if not r.get('base'):continue
            info=indice.get((chave(r),str(Path(r['base']).resolve())),{})
            extra=(adicionais or {}).get(chave(r),{})
            fontes.append(dict(info,**{**r,**extra,'base':r['base']}))
    saida={}
    for r in fontes:
        if not r.get('base'):continue
        if r.get('estado_catalogo') in ('ARQUIVADA','RETIRADA') or r.get('classe_arquivo') in ('BACKUP_TECNICO','BACKUP_CANDIDATO'):
            continue
        if projeto and r.get('projeto_uid') and r['projeto_uid']!=projeto['uuid']:
            r=dict(r, erro='A referência identifica outro projeto.')
        base=Path(r['base'])
        identidade=chave(r) if projeto else (*chave(r),r['base'])
        anterior=saida.get(identidade)
        if anterior and anterior['base']!=r['base']:
            anterior['erro']=f"Identidade em dois caminhos do projeto: {anterior['base']} e {base}. Relocalize o trabalho."
        else:
            saida.setdefault(identidade,dict(r,nome=r.get('nome') or base.stem,disponivel=base.is_file()))
    return sorted(saida.values(),key=lambda r:(r.get('data') or '',r['nome'],r['uuid']),reverse=True)


def descobrir(projeto, pastas, cancelar=None):
    """Só oferece trabalhos com identidade de projeto confirmada no arquivo."""
    existentes={chave(r) for r in projeto.get('bases',())}
    candidatos={}
    for pasta in pastas:
        for base in Path(pasta).rglob('*.gpkg'):
            verificar_cancelamento(cancelar)
            if (base.name.startswith('.') or '_antes_' in base.stem
                    or any(s.lower()=='backups' for s in base.parts)):
                continue
            try:
                for r in identificar(base):
                    if r.get('projeto_uid')==projeto['uuid'] and chave(r) not in existentes:
                        candidatos[(chave(r),r['base'])]=r
            except (ValueError,OSError,sqlite3.Error):
                continue
    return list(candidatos.values())


def agora():
    return datetime.now(timezone.utc).isoformat()
