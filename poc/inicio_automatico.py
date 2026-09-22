"""
Iniciar junto com o Windows (Seção 5, Opção B).
================================================

A fonte da verdade é o próprio Registro do Windows, não o config.json: se o
usuário desmarcar a entrada por fora (ex.: um "gerenciador de inicialização"
de terceiros), a janela deve refletir isso ao abrir, em vez de reimpor
silenciosamente o que estava salvo. Por isso `esta_ativo()` sempre lê o
Registro, e o valor do config.json serve só de pré-seleção antes da 1ª leitura.

A parte que fala com o `winreg` só existe no Windows; nas outras plataformas
(cloud sandbox, CI, o Ubuntu do Hugo) as funções continuam existindo e são
testáveis, mas levantam RuntimeError se alguém tentar de fato ligar/desligar
a inicialização automática — não faz sentido fingir sucesso.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAVE_REGISTRO = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME_VALOR = "AlertaFuturos"


def _no_windows() -> bool:
    return sys.platform == "win32"


def comando_de_inicializacao(caminho_executavel: Path) -> str:
    """Valor gravado no Registro. Entre aspas: o caminho de instalação pode ter espaços
    (ex.: 'C:\\Program Files\\...' ou o nome do usuário). ``--minimizado`` faz o app subir
    direto na bandeja (ícone perto do relógio) em vez de abrir a janela — ninguém que ligou
    "iniciar com o Windows" quer ver a janela de configuração aparecer sozinha no login."""
    return f'"{caminho_executavel}" --minimizado'


def definir(ativo: bool, caminho_executavel: Path) -> None:
    if not _no_windows():
        raise RuntimeError("Iniciar com o Windows só é aplicável no Windows.")
    import winreg  # import local: módulo só existe no Windows

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_REGISTRO, 0, winreg.KEY_SET_VALUE) as chave:
        if ativo:
            winreg.SetValueEx(chave, NOME_VALOR, 0, winreg.REG_SZ, comando_de_inicializacao(caminho_executavel))
        else:
            try:
                winreg.DeleteValue(chave, NOME_VALOR)
            except FileNotFoundError:
                pass  # já estava desligado — não é erro


def esta_ativo() -> bool:
    """Fonte da verdade: existe uma entrada AlertaFuturos no Registro agora?
    Fora do Windows, sempre False (não há onde essa entrada existir)."""
    if not _no_windows():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_REGISTRO, 0, winreg.KEY_QUERY_VALUE) as chave:
            winreg.QueryValueEx(chave, NOME_VALOR)
            return True
    except FileNotFoundError:
        return False
