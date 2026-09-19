"""
Ícone de bandeja (system tray) — Seção 5 da proposta, Opção A/B: "Roda em segundo plano, com
ícone perto do relógio: Iniciar, Parar e Sair".
================================================================================================

pystray roda o ícone numa thread própria, com o próprio laço de eventos do sistema operacional
(igual ao Monitor com o asyncio) — então nenhum callback do menu pode tocar um widget Tkinter
direto: cada um só agenda a ação de verdade na thread principal via ``root.after(0, ...)``, a
mesma regra de threading do resto do app (ver o docstring de janela.py).

Se não houver suporte a bandeja no ambiente (ex.: Linux sem área de notificação/Xvfb sem tray
host), a criação do ``pystray.Icon`` ou a chamada a ``.run()`` levanta uma exceção — quem usa
este módulo (``janela.Aplicativo``) trata isso e cai de volta no comportamento antigo (fechar a
janela encerra o app), em vez de fingir que a bandeja está funcionando.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from janela import Aplicativo

log = logging.getLogger("alerta.bandeja")


def icone_padrao() -> Image.Image:
    """Ícone genérico (fundo escuro + linha ascendente) — placeholder até a Blumenau TI
    fornecer uma logo oficial para usar aqui."""
    tamanho = 64
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, tamanho - 2, tamanho - 2), fill=(17, 24, 39, 255))
    d.line([(14, 46), (26, 32), (37, 40), (51, 15)], fill=(34, 197, 94, 255), width=5, joint="curve")
    return img


class Bandeja:
    """Ícone de bandeja com menu Abrir / Iniciar / Parar / Sair. ``iniciar()`` sobe a thread do
    ícone; ``parar()`` a encerra (chamado ao sair de vez, nunca ao só minimizar)."""

    def __init__(self, root: tk.Tk, aplicativo: "Aplicativo", caminho_icone: Path | None = None):
        self.root = root
        self.app = aplicativo
        imagem = Image.open(caminho_icone) if caminho_icone else icone_padrao()
        self.icone = pystray.Icon(
            "AlertaFuturos",
            imagem,
            "Alerta Futuros",
            menu=pystray.Menu(
                pystray.MenuItem("Abrir", self._abrir, default=True),
                pystray.MenuItem("Iniciar Monitoramento", self._iniciar, enabled=self._parado),
                pystray.MenuItem("Parar Monitoramento", self._parar, enabled=self._rodando),
                pystray.MenuItem("Sair", self._sair),
            ),
        )
        self._thread = threading.Thread(target=self.icone.run, daemon=True)

    def iniciar(self) -> None:
        self._thread.start()

    def parar(self) -> None:
        self.icone.stop()

    # ───────────────────────── estado (avaliado a cada abertura do menu) ─────────────────────────

    def _parado(self, _item) -> bool:
        return not (self.app.thread_motor and self.app.thread_motor.is_alive())

    def _rodando(self, _item) -> bool:
        return bool(self.app.thread_motor and self.app.thread_motor.is_alive())

    # ───────────────────────── callbacks do menu (thread da bandeja) ─────────────────────────

    def _abrir(self, _icone, _item) -> None:
        self.root.after(0, self._mostrar_janela)

    def _mostrar_janela(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _iniciar(self, _icone, _item) -> None:
        self.root.after(0, self._iniciar_e_mostrar_erro_se_falhar)

    def _iniciar_e_mostrar_erro_se_falhar(self) -> None:
        self.app.iniciar()
        if self.app.rotulo_erro.cget("text"):
            # parâmetro inválido salvo de uma sessão anterior: sem a janela aberta o usuário não
            # veria o erro, então mostramos a janela pra ele poder corrigir.
            self._mostrar_janela()

    def _parar(self, _icone, _item) -> None:
        self.root.after(0, self.app.parar)

    def _sair(self, _icone, _item) -> None:
        self.root.after(0, self.app.encerrar_de_vez)
