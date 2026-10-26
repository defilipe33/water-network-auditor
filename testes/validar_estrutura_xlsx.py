"""Verificações OOXML dirigidas às tabelas/filtros do exportador.

Não é validação integral do esquema ISO nem substitui Excel desktop.
Não usa openpyxl: examina CRC, XML, relações e conteúdo do pacote ZIP.
"""
import argparse
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'


def limites(ref):
    m = re.fullmatch(r'([A-Z]+)([1-9][0-9]*):([A-Z]+)([1-9][0-9]*)', ref or '')
    if not m:
        raise ValueError(f'Intervalo inválido: {ref}')
    def coluna(nome):
        n=0
        for letra in nome:
            n=n*26+ord(letra)-64
        return n
    a,b,c,d=coluna(m[1]),int(m[2]),coluna(m[3]),int(m[4])
    if not (1<=a<=c<=16384 and 1<=b<=d<=1048576):
        raise ValueError(f'Intervalo fora dos limites: {ref}')
    return a,b,c,d


def sobrepoe(a,b):
    return a[0]<=b[2] and b[0]<=a[2] and a[1]<=b[3] and b[1]<=a[3]


def validar_xlsx(caminho):
    erros, abas = [], []
    with zipfile.ZipFile(caminho) as z:
        if z.testzip():
            erros.append('CRC inválido no pacote')
        nomes=z.namelist()
        if len(nomes)!=len(set(nomes)):
            erros.append('Partes ZIP duplicadas')
        xml={n:ET.fromstring(z.read(n)) for n in nomes if n.endswith(('.xml','.rels'))}
        overrides={v.get('PartName').lstrip('/'):v.get('ContentType')
                   for v in xml['[Content_Types].xml'].findall(f'{{{C}}}Override')}
        strings=[]
        if 'xl/sharedStrings.xml' in xml:
            strings=[''.join(e.itertext()) for e in xml['xl/sharedStrings.xml'].findall(f'{{{S}}}si')]
        def relacoes(parte):
            diretorio=posixpath.dirname(parte)
            nome=posixpath.join(diretorio,'_rels',posixpath.basename(parte)+'.rels')
            return {r.get('Id'):r for r in xml.get(nome,ET.Element('vazio'))}
        def destino(parte,relacao):
            alvo=relacao.get('Target')
            return (alvo.lstrip('/') if alvo.startswith('/') else
                    posixpath.normpath(posixpath.join(posixpath.dirname(parte),alvo)))
        def texto(celula):
            if celula is None:
                return None
            if celula.get('t')=='inlineStr':
                return ''.join(e.text or '' for e in celula.findall(f'.//{{{S}}}t'))
            v=celula.find(f'{{{S}}}v')
            if v is None:
                return None
            return strings[int(v.text)] if celula.get('t')=='s' else v.text
        workbook=xml['xl/workbook.xml']
        wb_rels=relacoes('xl/workbook.xml')
        tabelas_vistas, ids, nomes_tabelas = set(), set(), set()
        for sheet in workbook.findall(f'{{{S}}}sheets/{{{S}}}sheet'):
            parte=destino('xl/workbook.xml',wb_rels[sheet.get(f'{{{R}}}id')])
            ws=xml[parte]
            celulas={c.get('r'):c for c in ws.findall(f'{{{S}}}sheetData/{{{S}}}row/{{{S}}}c')}
            refs=relacoes(parte)
            tabelas=[]
            parts=ws.find(f'{{{S}}}tableParts')
            if parts is not None and int(parts.get('count'))!=len(parts):
                erros.append(f'{sheet.get("name")}: tableParts count incompatível')
            for tp in parts if parts is not None else []:
                rel=refs.get(tp.get(f'{{{R}}}id'))
                if rel is None or not rel.get('Type','').endswith('/table') or rel.get('TargetMode')=='External':
                    erros.append('Relação de tabela ausente ou inválida')
                    continue
                alvo=destino(parte,rel)
                if alvo not in xml:
                    erros.append(f'Tabela ausente: {alvo}')
                    continue
                tabelas_vistas.add(alvo)
                t=xml[alvo]
                if t.tag!=f'{{{S}}}table' or overrides.get(alvo)!='application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml':
                    erros.append(f'Tipo/namespace inválido: {alvo}')
                ident=int(t.get('id','0'))
                nome=t.get('displayName','')
                if ident<=0 or ident in ids:
                    erros.append('ID de tabela inválido/duplicado')
                ids.add(ident)
                if (not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',nome) or len(nome)>255
                        or nome.casefold() in nomes_tabelas
                        or re.fullmatch(r'[A-Za-z]{1,3}[1-9][0-9]*',nome)
                        or re.fullmatch(r'R[0-9]+C[0-9]+',nome,re.I)
                        or t.get('name')!=nome):
                    erros.append(f'Nome de tabela inválido/duplicado: {nome}')
                nomes_tabelas.add(nome.casefold())
                ref=limites(t.get('ref'))
                if any(sobrepoe(ref,outra['limites']) for outra in tabelas):
                    erros.append('Tabelas sobrepostas')
                cols=t.find(f'{{{S}}}tableColumns')
                if cols is None or int(cols.get('count','0'))!=len(cols) or len(cols)!=ref[2]-ref[0]+1:
                    erros.append(f'{nome}: tableColumns count incompatível')
                    continue
                headers=[]
                for i,col in enumerate(cols,ref[0]):
                    letra=''
                    n=i
                    while n:
                        n,d=divmod(n-1,26)
                        letra=chr(65+d)+letra
                    h=texto(celulas.get(f'{letra}{ref[1]}'))
                    headers.append(h)
                    if not h or h!=col.get('name'):
                        erros.append(f'{nome}: cabeçalho XML difere da célula {letra}{ref[1]}')
                if len({h.casefold() for h in headers if h})!=len(headers):
                    erros.append(f'{nome}: cabeçalhos não únicos')
                col_ids=[int(c.get('id','0')) for c in cols]
                if any(i<=0 for i in col_ids) or len(set(col_ids))!=len(col_ids):
                    erros.append(f'{nome}: IDs de colunas inválidos')
                filtro=t.find(f'{{{S}}}autoFilter')
                if filtro is None or filtro.get('ref')!=t.get('ref'):
                    erros.append(f'{nome}: filtro da tabela não coincide com seu intervalo')
                if int(t.get('headerRowCount','1'))!=1 or ref[3]<=ref[1]:
                    erros.append(f'{nome}: cabeçalho/linhas de dados inválidos')
                tabelas.append(dict(nome=nome,ref=t.get('ref'),limites=ref,
                                    registros=ref[3]-ref[1],colunas=len(cols)))
            filtro=ws.find(f'{{{S}}}autoFilter')
            if filtro is not None:
                ref=limites(filtro.get('ref'))
                if any(sobrepoe(ref,t['limites']) for t in tabelas):
                    erros.append(f'{sheet.get("name")}: autofiltro da planilha sobreposto ao filtro da tabela')
            pane=ws.find(f'{{{S}}}sheetViews/{{{S}}}sheetView/{{{S}}}pane')
            if pane is None or pane.get('state')!='frozen' or pane.get('ySplit')!='1':
                erros.append(f'{sheet.get("name")}: cabeçalho não congelado')
            grupos=0
            if sheet.get('name')=='DETALHAMENTO_LOCAIS':
                if tabelas or filtro is not None:
                    erros.append('Detalhamento expansível não pode concorrer com tabelas/autofiltros')
                outline=ws.find(f'{{{S}}}sheetPr/{{{S}}}outlinePr')
                if outline is None or outline.get('summaryBelow')!='0':
                    erros.append('Resumo de agrupamento deve estar acima dos detalhes')
                pai=None
                for linha in ws.findall(f'{{{S}}}sheetData/{{{S}}}row'):
                    numero=int(linha.get('r'))
                    nivel=int(linha.get('outlineLevel','0'))
                    if numero==1:
                        continue
                    tipo=texto(celulas.get(f'A{numero}'))
                    if tipo=='LOCAL':
                        grupos+=1
                        pai=numero
                        if nivel or linha.get('hidden','0')=='1' or linha.get('collapsed')!='1':
                            erros.append('Linha principal de local não está visível/recolhida corretamente')
                    elif pai is None or nivel!=1 or linha.get('hidden')!='1':
                        erros.append('Detalhe sem local pai ou não recolhido no outline')
            abas.append(dict(nome=sheet.get('name'),tabelas=tabelas,
                             filtro_planilha=filtro.get('ref') if filtro is not None else None,
                             grupos_linhas=grupos))
        partes_tabela={n for n in xml if n.startswith('xl/tables/') and n.endswith('.xml')}
        if partes_tabela!=tabelas_vistas:
            erros.append('Tabelas órfãs ou não referenciadas')
    return dict(valido=not erros,erros=erros,abas=abas)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('arquivo')
    r=validar_xlsx(p.parse_args().arquivo)
    print(json.dumps(r,ensure_ascii=False,indent=2))
    raise SystemExit(0 if r['valido'] else 1)
