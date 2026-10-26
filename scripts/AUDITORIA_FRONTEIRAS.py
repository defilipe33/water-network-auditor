"""Entrada pública do núcleo e da interface mínima. Ver LEIA_ME.md."""
from auditoria_fronteiras import CamadaEntrada, Modo, Parametros, Resultado, auditar


def abrir_interface(recarregar=False):
    if recarregar:
        import importlib
        import sys
        modulo = sys.modules.get('auditoria_fronteiras.interface')
        janela = getattr(modulo, '_janela', None)
        if janela is not None:
            if janela._executando:
                raise RuntimeError('Aguarde ou cancele a execução antes de atualizar a interface')
            if not janela.close():
                raise RuntimeError('Atualização cancelada: resolva as alterações pendentes antes de recarregar.')
            janela.deleteLater()
        # Atualiza somente apresentação/interface; o núcleo continua carregado.
        for nome in ('apresentacao', 'investigacao', 'inspecao', 'ciclo', 'versoes', 'persistencia', 'catalogo', 'estados', 'seletor_versoes', 'fluxos', 'exportacao', 'painel',
                     'visualizacao', 'visualizacao_locais', 'relatorio_detalhado', 'relatorio', 'interface'):
            modulo = sys.modules.get('auditoria_fronteiras.' + nome)
            if modulo is not None:
                importlib.reload(modulo)
    from auditoria_fronteiras.interface import abrir_interface as abrir
    return abrir()


__all__ = ["CamadaEntrada", "Modo", "Parametros", "Resultado", "auditar", "abrir_interface"]


if __name__ == '__main__':
    abrir_interface()
