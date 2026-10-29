"""Lista alternativa por identidade explícita; não recupera pastas WaterGEMS."""
import csv
from . import decisoes as db
from .arquivos import hash_arquivo
from .selection_sets import firma_elemento


def ler_csv(caminho,p,nome):
    if not nome.strip():raise ValueError('Informe o nome da lista')
    modelo=p['topologia']['modelo'];ms=[];vistos=set()
    with open(caminho,encoding='utf-8-sig',newline='') as f:
        amostra=f.read(4096);f.seek(0);dialeto=csv.Sniffer().sniff(amostra,delimiters=',;\t');r=csv.DictReader(f,dialect=dialeto)
        if not {'DomainElementID','Tipo','Modelo'}<=set(r.fieldnames or []):raise ValueError('CSV exige DomainElementID, Tipo e Modelo (identidade técnica). Label é opcional; não serve como chave')
        for row in r:
            if row['Modelo']!=modelo['projeto']:raise ValueError('Modelo do CSV incompatível; nenhuma associação por nome ou proximidade será feita')
            if not row['DomainElementID'].isdecimal():raise ValueError('DomainElementID inválido')
            i=int(row['DomainElementID']);e=modelo['elementos'].get(i)
            if i in vistos:continue
            vistos.add(i);ms.append(dict(id=i,uid=modelo['projeto']+':'+str(i),tipo=row['Tipo'],label=row.get('Label'),firma=firma_elemento(e) if e and e['tipo']==row['Tipo'] else None,excluido=e.get('excluido') if e else None,situacao='PRESENTE' if e and e['tipo']==row['Tipo'] and e['excluido'] is False else 'AUSENTE_OU_TIPO_INCOMPATIVEL'))
    sha=hash_arquivo(caminho);return dict(regra='lista-csv-1',modelo=modelo['projeto'],cenario=modelo['cenario'],alternativas=modelo.get('alternativas'),assinatura=sha,origem=str(caminho),data=db.agora(),hierarquia='NAO_RECUPERADA',avisos=['Importação alternativa: nomes de pastas e Query original não foram recuperados'],itens=[dict(id='CSV:'+sha,nome=nome,nome_resolvido=True,pasta=False,pai=None,ancestrais=[],hierarquia='NAO_RECUPERADA',tipo='ESTATICO',tipo_bruto=None,quantidade=len(ms),membros=ms,por_tipo={},situacao='MEMBROS_EXPLICITOS',definicao=dict(origem='CSV_EXTERNO',campos=['DomainElementID','Tipo','Modelo']),blob_sha256=None)])
