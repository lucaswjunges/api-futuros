"""
Ícone de bandeja (system tray) — Seção 5 da proposta, Opção A/B: "Roda em segundo plano, com
ícone perto do relógio: Iniciar, Parar e Sair".
================================================================================================

pystray roda o ícone numa thread própria, com o próprio laço de eventos do sistema operacional
(igual ao Monitor com o asyncio) — então nenhum callback do menu pode tocar um widget Tkinter
direto: cada um só agenda a ação de verdade na thread principal via ``root.after(0, ...)``, a
mesma regra de threading do resto do app (ver o docstring de janela.py).

Se não houver suporte a bandeja no ambiente (ex.: Linux sem área de notificação/Xvfb sem tray
host), a criação do ``pystray.Icon`` levanta uma exceção — quem usa este módulo
(``janela.Aplicativo``) trata isso e cai de volta no comportamento antigo (fechar a janela encerra
o app), em vez de fingir que a bandeja está funcionando.

Achado em 19/09/2026 (teste ao vivo do Hugo): a criação do ``pystray.Icon`` pode dar certo, mas o
``.run()`` de verdade — que roda numa thread separada e é o que efetivamente desenha o ícone — pode
falhar *depois*, sem levantar nada no código que criou a bandeja (a exceção fica isolada na thread).
Resultado: a janela fica configurada pra minimizar ao fechar, mas nenhum ícone aparece — o usuário
fica sem jeito de reabrir o app. Por isso ``_executar()`` embrulha o ``.run()`` num try/except que
avisa ``janela.Aplicativo`` de volta (via ``root.after``) se a thread morrer, e ``thread_viva()``
deixa ``janela.py`` conferir logo depois de iniciar se ela já não nasceu morta.

Investigando esse achado (mesmo dia), veio a confirmação de que o ícone sempre esteve funcionando:
ele fica na área de ícones ocultos (o "^" ao lado do relógio), pequeno e sem nome óbvio — fácil de
passar batido no meio de Bluetooth/Teams/OneDrive. Por isso trocamos o placeholder genérico pela
logo oficial da Blumenau TI (``carregar_icone()``/``assets/icone_bandeja.png``): mais reconhecível
mesmo minúsculo.
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


CAMINHO_ICONE_PADRAO = Path(__file__).with_name("assets") / "icone_bandeja.png"


def icone_padrao() -> Image.Image:
    """Ícone de reserva (fundo escuro + linha ascendente) — só entra em cena se o arquivo de
    CAMINHO_ICONE_PADRAO não existir (ex.: alguém rodando de uma cópia incompleta do repo, sem a
    pasta assets/). Nunca deixa a falta de um arquivo de imagem derrubar o app."""
    tamanho = 64
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, tamanho - 2, tamanho - 2), fill=(17, 24, 39, 255))
    d.line([(14, 46), (26, 32), (37, 40), (51, 15)], fill=(34, 197, 94, 255), width=5, joint="curve")
    return img


def carregar_icone(caminho: Path | None = None) -> Image.Image:
    """Carrega o ícone da bandeja — por padrão a logo oficial da Blumenau TI (achada em 19/09/2026,
    baixada de blumenauti.com.br/favico2.png: mesmo azul-marinho #1a1a2e do site, "B" branco e a
    barrinha de gráfico ascendente — a mesma linguagem visual do próprio app). Se o arquivo não
    existir por algum motivo, cai em icone_padrao() em vez de quebrar."""
    caminho = caminho or CAMINHO_ICONE_PADRAO
    try:
        return Image.open(caminho).convert("RGBA")
    except (FileNotFoundError, OSError) as e:
        log.warning("Ícone %s não encontrado (%s); usando o placeholder.", caminho, e)
        return icone_padrao()


class Bandeja:
    """Ícone de bandeja com menu Abrir / Iniciar / Parar / Sair. ``iniciar()`` sobe a thread do
    ícone; ``parar()`` a encerra (chamado ao sair de vez, nunca ao só minimizar)."""

    def __init__(self, root: tk.Tk, aplicativo: "Aplicativo", caminho_icone: Path | None = None):
        self.root = root
        self.app = aplicativo
        imagem = carregar_icone(caminho_icone)
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
        self._thread = threading.Thread(target=self._executar, daemon=True)

    def iniciar(self) -> None:
        self._thread.start()

    def thread_viva(self) -> bool:
        """Chamado por janela.py logo depois de iniciar(), pra pegar o caso em que o .run() já
        morreu quase imediatamente (o caso mais comum de falha — ver docstring do módulo)."""
        return self._thread.is_alive()

    def parar(self) -> None:
        self.icone.stop()

    def _executar(self) -> None:
        try:
            self.icone.run()
        except Exception:
            log.exception("Ícone de bandeja: .run() falhou depois de a thread já ter iniciado.")
            self.root.after(0, self.app._bandeja_falhou_em_tempo_de_execucao)

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
