"""Selection Sets HMI: leitura sobre Banco existente, sem avaliar Queries."""
import struct
from collections import Counter
from pathlib import Path
from .leitura import Banco
from . import decisoes as db
from .arquivos import hash_arquivo

REGRA='selection-hmi-1'
REFERENCIA='b3205a2579eee782375b757f7a0b96f40f7a88ff'


def decodificar(blob,quantidade):
    if quantidade<0:raise ValueError('Contagem negativa')
    if blob is None:
        if quantidade:raise ValueError('Membros declarados sem BLOB')
        return []
    if not isinstance(blob,bytes) or len(blob)%4 or len(blob)//4!=quantidade:raise ValueError('Contagem ou comprimento do BLOB incompatível')
    return [v[0] for v in struct.iter_unpack('<I',blob)]


def firma_elemento(e):
    return db.digest([e.get(k) for k in ('uid','tipo','geometria','topologia','excluido')])


def ler(caminho,selecionados=None,cancelado=None,cenario=None):
    from tempfile import TemporaryDirectory
    from .bases import snapshot
    with TemporaryDirectory(prefix='wna_selection_') as pasta:
        arquivo=Path(pasta)/'consulta.sqlite';prova=snapshot(caminho,arquivo,cancelado)
        r=_ler_snapshot(arquivo,selecionados,cancelado,cenario);r['origem']=str(Path(caminho).resolve());r['snapshot']=dict(sha256=prova['sha256_snapshot'],metodo=prova['metodo']);return r


def _ler_snapshot(caminho,selecionados=None,cancelado=None,cenario=None):
    b=Banco(caminho)
    try:
        antes=hash_arquivo(caminho);tabelas=b.tabelas
        b.con.set_progress_handler(lambda:1 if cancelado and cancelado() else 0,10000)
        modelo=b.ler(cenario if cenario is not None else b.ativo);elementos=modelo['elementos']
        if 'HMISelectionSet' not in tabelas:raise ValueError('Modelo sem tabela de Selection Sets; utilize uma lista exportada e identificada pelo WaterGEMS')
        rows=b.linhas('HMISelectionSet');ativos={r['SelectionSetID']:r for r in rows if r.get('IsDeleted')==0};saida=[];avisos=[]
        hierarquia=all('ParentID' in r and 'SelectionSetElementType' in r for r in rows)
        def caminho_item(i):
            vistos={i};partes=[];r=ativos[i];pai=r.get('ParentID',0)
            while pai:
                if pai in vistos:return [],'CICLO'
                vistos.add(pai);a=ativos.get(pai)
                if not a or a.get('SelectionSetElementType')!=1:return [],'PASTA_AUSENTE_OU_INCOMPATIVEL'
                partes.insert(0,pai);pai=a.get('ParentID',0)
            return partes,'RECUPERADA' if hierarquia else 'NAO_RECUPERADA'
        for i,r in sorted(ativos.items()):
            if cancelado and cancelado():raise InterruptedError('Leitura cancelada; modelo preservado')
            m=b.rotulos.get(i,{});nome=m.get('Label');pasta=r.get('SelectionSetElementType')==1;ancestrais,estado=caminho_item(i)
            v=dict(id=i,nome_original=nome,nome=nome if nome is not None and str(nome).strip() else 'Selection Set '+str(i),nome_resolvido=nome is not None and bool(str(nome).strip()),pasta=pasta,pai=r.get('ParentID'),ancestrais=ancestrais,hierarquia=estado,tipo_bruto=r.get('SelectionSetType'),tipo='PASTA' if pasta else 'ESTATICO' if r.get('SelectionSetType')==1 else 'DINAMICO_OU_DESCONHECIDO',quantidade=r.get('SelectionSetCount'),membros=[],por_tipo={},situacao='PASTA' if pasta else 'COMPOSICAO_NAO_VERIFICADA',definicao={k:x for k,x in r.items() if k!='SelectionSetElementIDs'},blob_sha256=db.digest(r['SelectionSetElementIDs'].hex()) if isinstance(r.get('SelectionSetElementIDs'),bytes) else None)
            if pasta and (r.get('SelectionSetCount') or r.get('SelectionSetElementIDs')):v['situacao']='PASTA_COM_DADOS_INCONSISTENTES';v['erro']='Marcador de pasta com membros declarados: revisar o formato antes de interpretar'
            v['blob_original_hex']=r['SelectionSetElementIDs'].hex() if isinstance(r.get('SelectionSetElementIDs'),bytes) else None
            if not pasta and (selecionados is None or i in selecionados):
                if v['tipo']=='ESTATICO':
                    try:ids=decodificar(r.get('SelectionSetElementIDs'),r['SelectionSetCount']);v['situacao']='MEMBROS_EXPLICITOS';v['duplicados']=len(ids)-len(set(ids))
                    except ValueError as e:ids=[];v['erro']=str(e)
                else:ids=[];v['erro']='Tipo não validado: definição preservada, Query não executada; exporte lista de IDs no WaterGEMS.'
                v['ids_brutos']=ids
                for id in dict.fromkeys(ids):
                    d=b.dominio.get(id);rot=b.rotulos.get(id);e=elementos.get(id,{});v['membros'].append(dict(tipo=e.get('tipo'),firma=firma_elemento(e) if e else None,id=id,uid=f'{b.projeto}:{id}',label=(rot or {}).get('Label'),excluido=None if d is None or rot is None else bool(d.get('IsDeleted') or rot.get('IsDeleted')),situacao='AUSENTE' if d is None or rot is None else 'EXCLUIDO' if d.get('IsDeleted') or rot.get('IsDeleted') else 'PRESENTE'))
            saida.append(v)
        if hash_arquivo(caminho)!=antes:raise ValueError('Modelo mudou durante a leitura; nenhuma importação publicada')
        return dict(nome_modelo=b.linhas('HMIDomainDataSet')[0].get('Name') or b.projeto,formato=b.linhas('HMISchemaVersionInfo'),regra=REGRA,referencia_composer=REFERENCIA,modelo=b.projeto,assinatura=antes,origem=str(Path(caminho).resolve()),data=db.agora(),cenario=modelo['cenario'],alternativas=modelo['alternativas'],hierarquia='RECUPERADA' if hierarquia else 'NAO_RECUPERADA',itens=saida,avisos=avisos)
    finally:b.close()


def preparar(pacote,leitura):
    if leitura['modelo']!=pacote['topologia']['modelo']['projeto']:raise ValueError('Selection Sets pertencem a outro modelo; IDs não serão associados')
    el=pacote['topologia']['modelo']['elementos'];itens=[]
    for raw in leitura['itens']:
        r=dict(raw,membros=[dict(m) for m in raw['membros']]);cont=Counter()
        for m in r['membros']:
            e=el.get(m['id'])
            tipo_origem=m.get('tipo');m['tipo']=tipo_origem or (e.get('tipo') if e else None)
            if m['situacao']=='PRESENTE':m['situacao']='CORRESPONDENCIA_VALIDA' if e and e.get('uid')==m['uid'] and e.get('excluido') is False and tipo_origem==e.get('tipo') and m.get('firma')==firma_elemento(e) else 'INCOMPATIVEL_COM_VERSAO_TOPOLOGICA'
            if m['tipo']:cont[m['tipo']]+=1
        r['por_tipo']=dict(cont);r['compatibilidade']=dict(Counter(m['situacao'] for m in r['membros']));itens.append(r)
    return dict(leitura,itens=itens,topo_uid=pacote['resultado']['meta']['topologia']['execucao_uid'])


def ids_validos(itens):return {m['id'] for r in itens for m in r['membros'] if m['situacao']=='CORRESPONDENCIA_VALIDA' and r['situacao']=='MEMBROS_EXPLICITOS'}


def comparar(a,b):
    if a['modelo']!=b['modelo']:raise ValueError('Modelos distintos: correspondência por ID não comprovada')
    aa={r['id']:r for r in a['itens']};bb={r['id']:r for r in b['itens']};linhas=[]
    for i in sorted(aa.keys()|bb.keys(),key=str):
        x=aa.get(i);y=bb.get(i);mudancas=[]
        if x is None:mudancas=['NOVA_PASTA' if y['pasta'] else 'NOVO_CONJUNTO']
        elif y is None:mudancas=['PASTA_REMOVIDA' if x['pasta'] else 'CONJUNTO_REMOVIDO']
        else:
            if x['nome']!=y['nome']:mudancas.append('RENOMEADO')
            if x.get('pai')!=y.get('pai'):mudancas.append('MOVIDO')
            if x['pasta']!=y['pasta'] or x['tipo']!=y['tipo']:mudancas.append('TIPO_ALTERADO')
        si={m['uid'] for m in (x or {}).get('membros',[])};sj={m['uid'] for m in (y or {}).get('membros',[])}
        linhas.append(dict(id=i,antes=(x or {}).get('nome'),depois=(y or {}).get('nome'),mudancas=mudancas,incluidos=sorted(sj-si),retirados=sorted(si-sj),composicao_verificada=all(r is None or r['pasta'] or r['situacao']=='MEMBROS_EXPLICITOS' for r in (x,y))))
    return dict(modelo=a['modelo'],origem=a['assinatura'],destino=b['assinatura'],linhas=linhas,interpretacao='Mudança cadastral; não comprova alteração hidráulica')
