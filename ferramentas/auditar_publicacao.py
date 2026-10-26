"""Inspeciona blobs do índice/histórico, sem enviar conteúdo ou apagar arquivos.

Barreira complementar: revisão humana de contexto ainda é obrigatória.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import re
import subprocess

RAIZ=Path(__file__).resolve().parents[1]
RAIZES={'scripts','testes','complemento_qgis','documentacao','ferramentas','.github'}
ARQUIVOS_RAIZ={'.gitignore','.gitattributes','README.md','CONTRIBUTING.md','SECURITY.md','THIRD_PARTY_NOTICES.md','publicacao_permitidos.json'}
SEGREDOS=[re.compile(x) for x in (
    r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',
    r'AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    r'(?i)https?://[^\s/:]+:[^\s/@]+@',
    r'''(?i)(?:password|passwd|api_key|access_token|client_secret)\s*[:=]\s*["'][^"'\r\n]{12,}["']''')]
PESSOAL=re.compile(r'(?i)(?:[a-z]:[\\/](?:users|documents and settings)[\\/]|/'+r'home/[^/\s]+/)')

def git(*args):return subprocess.run(['git',*args],cwd=RAIZ,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout

def verificar(nome,dados,modo,pdfs):
    p=PurePosixPath(nome);erros=[]
    if modo not in ('100644','100755'):erros.append('Modo não permitido: links e submódulos exigem revisão')
    if p.parts[0] not in RAIZES and nome not in ARQUIVOS_RAIZ:erros.append('Caminho fora do conjunto público permitido')
    if len(dados)>1024*1024:erros.append('Arquivo acima de 1 MiB exige revisão específica')
    if p.suffix=='.pdf':
        if pdfs.get(nome)!=sha256(dados).hexdigest():erros.append('PDF sem hash de revisão autorizado')
        return erros
    if p.suffix.lower() not in ('.py','.md','.txt','.svg','.json','.yaml','.yml') and nome not in ARQUIVOS_RAIZ:erros.append('Formato não permitido na distribuição pública')
    if nome.startswith('documentacao/') and not nome.startswith('documentacao/publica/'):erros.append('Documento original local fora da documentação pública revisada')
    if nome=='scripts/LEIA_ME.md':erros.append('Manual local com informações operacionais')
    if nome.startswith('testes/') and not (p.name.startswith('test_') or p.name in {'empacotar_plugin.py','validar_estrutura_xlsx.py','validar_relatorio_locais.py','validar_excel_desktop.py','ensaio_versionamento_bases.py'}):erros.append('Ensaio não aprovado para distribuição pública')
    try:conteudo=dados.decode('utf8')
    except UnicodeDecodeError:return erros+['Binário inesperado']
    if '\x00' in conteudo:erros.append('Conteúdo binário inesperado')
    if PESSOAL.search(conteudo):erros.append('Possível caminho pessoal absoluto')
    if any(r.search(conteudo) for r in SEGREDOS):erros.append('Possível credencial; valor não exibido')
    return erros

def entradas(revisao=None):
    if revisao:
        for item in git('ls-tree','-r','-z',revisao).split(b'\0'):
            if item:
                info,nome=item.split(b'\t',1);modo,tipo,oid=info.decode().split();yield nome.decode('utf8'),modo,oid
    else:
        for item in git('ls-files','--stage','-z').split(b'\0'):
            if item:
                info,nome=item.split(b'\t',1);modo,oid,stage=info.decode().split()
                if stage!='0':raise ValueError('Conflito no índice')
                yield nome.decode('utf8'),modo,oid

def executar(historico=False):
    permitidos=json.loads(git('show',':publicacao_permitidos.json').decode())['pdfs_revisados']
    falhas=[];vistos=set();arquivos=[]
    revisoes=[None]
    if historico:
        refs=git('rev-list','--all').decode().splitlines();revisoes+=refs
    for ref in revisoes:
        for nome,modo,oid in entradas(ref):
            if ref is None:arquivos.append(dict(caminho=nome,blob=oid,bytes=int(git('cat-file','-s',oid))))
            chave=(nome,modo,oid)
            if chave in vistos:continue
            vistos.add(chave)
            for motivo in verificar(nome,git('cat-file','blob',oid),modo,permitidos):falhas.append(dict(caminho=nome,motivo=motivo,revisao=ref or 'INDEX'))
    return dict(arquivos=len(arquivos),bytes=sum(x['bytes'] for x in arquivos),blobs_revisados=len(vistos),historico=historico,falhas=falhas,lista=arquivos)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tracked',action='store_true',help='Examinar todo o índice (também é o padrão)');p.add_argument('--history',action='store_true');p.add_argument('--json',action='store_true');a=p.parse_args()
    r=executar(a.history)
    print(json.dumps(r if a.json else {k:v for k,v in r.items() if k!='lista'},ensure_ascii=False,indent=2))
    raise SystemExit(bool(r['falhas']))
