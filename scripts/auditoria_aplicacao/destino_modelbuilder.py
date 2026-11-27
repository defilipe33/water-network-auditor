"""Validação da pasta pai e identidade reservada na tela do pacote ModelBuilder."""

from pathlib import Path
import re
from tempfile import TemporaryFile
from uuid import uuid4


def nome_pacote(execucao):
    trecho=re.sub('[^A-Za-z0-9_-]', '', execucao[:8]) or 'execucao'
    return f'Cadastro_modelagem_{trecho}_{uuid4().hex[:8]}'


def caminho_pasta(texto):
    if not texto.strip():
        raise ValueError('Indique a pasta de destino do pacote.')
    pasta=Path(texto.strip().strip('"')).expanduser()
    if not pasta.is_absolute():
        raise ValueError('Indique um caminho absoluto, incluindo a unidade ou o compartilhamento de rede.')
    return pasta


def preparar(pasta,nome,*,criar=False):
    if not re.fullmatch(r'Cadastro_modelagem_[A-Za-z0-9_-]+_[0-9a-f]{8}',nome):
        raise ValueError('Nome de pacote inválido.')
    if criar:
        pasta.mkdir(parents=True,exist_ok=True)
    if not pasta.is_dir():
        raise ValueError('A pasta de destino está indisponível ou o caminho não é um diretório.')
    if (pasta/nome).exists():
        raise FileExistsError('Já existe um pacote com esse nome na pasta escolhida.')
    try:
        with TemporaryFile(dir=pasta) as teste:
            teste.write(b'WNA')
            teste.flush()
    except OSError as erro:
        raise OSError(f'Sem acesso de gravação à pasta escolhida. {erro.strerror or erro}') from erro
    return pasta/nome
