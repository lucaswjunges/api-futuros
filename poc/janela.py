"""
Janela de configuração — Opção B (Completa), Seção 5 da proposta.
===================================================================

Fica só a parte de UI aqui: os campos usam campos_formulario.py (texto <->
Parametros) e a configuração salva usa configuracao.py — nenhuma lógica de
RSI/setor/cruzamento é duplicada, tudo isso continua só em alerta_futuros.py.

Fluxo de threads (igual ao --sem-popup/--demo do CLI, já usado em produção):
  Monitor.executar() roda numa thread própria (asyncio); a única coisa que
  ela faz que toca a janela é colocar cada Avaliacao numa queue.Queue. Quem
  lê a fila e atualiza os widgets é sempre a thread principal, via
  root.after — Tkinter não é thread-safe, então nada de rede/asyncio pode
  chamar métodos de widget diretamente.

Uso:
  python janela.py
"""

from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from alerta_futuros import ATRASO_MAX_POPUP_MS, MS_5M, PARES, Avaliacao, Monitor, Popups, formatar_num
from campos_formulario import CAMPOS, ROTULOS, CampoInvalido, parametros_dos_textos, textos_de
from configuracao import Configuracao, carregar, salvar, validar

log = logging.getLogger("alerta.janela")

FUNDO = "#111827"
FUNDO_CAMPO = "#1f2937"
TEXTO = "#f9fafb"
TEXTO_FRACO = "#9ca3af"
VERDE = "#22c55e"
VERMELHO = "#ef4444"
FONTE = ("Segoe UI", 10)


def caminho_do_executavel() -> Path:
    """Em desenvolvimento aponta pro script; depois de empacotado com PyInstaller
    (sys.frozen), aponta pro .exe — é isso que vai pro Registro em 'iniciar com o Windows'."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.argv[0]).resolve()


class Aplicativo:
    def __init__(self, root: tk.Tk, caminho_config: Path | None = None):
        self.root = root
        self.caminho_config = caminho_config
        self.config: Configuracao = carregar(caminho_config)
        self.monitor: Monitor | None = None
        self.thread_motor: threading.Thread | None = None
        self.fila: queue.Queue[Avaliacao] = queue.Queue()
        self.linhas_status: dict[str, str] = {}
        self.entradas: dict[str, tk.Entry] = {}
        self.var_iniciar_windows = tk.BooleanVar(value=self.config.iniciar_com_windows)

        self._montar(root)
        self.popups = Popups(root, self.config.parametros.popup_segundos)
        root.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ───────────────────────────── montagem da janela ─────────────────────────────

    def _montar(self, root: tk.Tk) -> None:
        root.title("Alerta Futuros — Configuração")
        root.configure(bg=FUNDO)

        campos = tk.Frame(root, bg=FUNDO, padx=16, pady=12)
        campos.pack(fill="x")
        textos_iniciais = textos_de(self.config.parametros)
        for linha, campo in enumerate(CAMPOS):
            tk.Label(campos, text=ROTULOS[campo], bg=FUNDO, fg=TEXTO_FRACO, font=FONTE, anchor="w").grid(
                row=linha, column=0, sticky="w", pady=3
            )
            entrada = tk.Entry(campos, bg=FUNDO_CAMPO, fg=TEXTO, insertbackground=TEXTO,
                                relief="flat", font=FONTE, width=12, justify="right")
            entrada.insert(0, textos_iniciais[campo])
            entrada.grid(row=linha, column=1, sticky="e", padx=(12, 0), pady=3)
            self.entradas[campo] = entrada

        tk.Checkbutton(campos, text="Iniciar junto com o Windows", variable=self.var_iniciar_windows,
                        bg=FUNDO, fg=TEXTO, selectcolor=FUNDO_CAMPO, activebackground=FUNDO,
                        activeforeground=TEXTO, font=FONTE).grid(
            row=len(CAMPOS), column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        if sys.platform != "win32":
            tk.Label(campos, text="(disponível só no Windows)", bg=FUNDO, fg=TEXTO_FRACO,
                      font=("Segoe UI", 8)).grid(row=len(CAMPOS) + 1, column=0, columnspan=2, sticky="w")

        self.rotulo_erro = tk.Label(root, text="", bg=FUNDO, fg=VERMELHO, font=FONTE, wraplength=360, justify="left")
        self.rotulo_erro.pack(fill="x", padx=16)

        botoes = tk.Frame(root, bg=FUNDO, padx=16, pady=8)
        botoes.pack(fill="x")
        self.botao_iniciar = tk.Button(botoes, text="Iniciar Monitoramento", command=self.iniciar,
                                        bg=VERDE, fg="#052e16", font=(*FONTE, "bold"), relief="flat", padx=10)
        self.botao_iniciar.pack(side="left")
        self.botao_parar = tk.Button(botoes, text="Parar Monitoramento", command=self.parar,
                                      bg=VERMELHO, fg="#450a0a", font=(*FONTE, "bold"), relief="flat",
                                      padx=10, state="disabled")
        self.botao_parar.pack(side="left", padx=(8, 0))

        self.rotulo_conexao = tk.Label(root, text="Parado", bg=FUNDO, fg=TEXTO_FRACO, font=FONTE)
        self.rotulo_conexao.pack(anchor="w", padx=16)

        self._montar_quadro_situacao(root)

    def _montar_quadro_situacao(self, root: tk.Tk) -> None:
        estilo = ttk.Style(root)
        estilo.theme_use("clam")
        estilo.configure("Situacao.Treeview", background=FUNDO_CAMPO, fieldbackground=FUNDO_CAMPO,
                          foreground=TEXTO, rowheight=24, font=FONTE)
        estilo.configure("Situacao.Treeview.Heading", background=FUNDO, foreground=TEXTO_FRACO, font=FONTE)

        colunas = ("rsi", "setor", "fechamento", "horario")
        self.tabela = ttk.Treeview(root, columns=colunas, show="tree headings", height=len(PARES),
                                    style="Situacao.Treeview")
        self.tabela.heading("#0", text="Par")
        self.tabela.heading("rsi", text="RSI(2)")
        self.tabela.heading("setor", text="Setor")
        self.tabela.heading("fechamento", text="Fechamento")
        self.tabela.heading("horario", text="Horário")
        for coluna in colunas:
            self.tabela.column(coluna, anchor="center", width=90)
        self.tabela.column("#0", width=110)
        for simbolo in PARES:
            self.tabela.insert("", "end", iid=simbolo, text=simbolo, values=("—", "—", "—", "—"))
            self.linhas_status[simbolo] = simbolo
        self.tabela.pack(fill="both", expand=True, padx=16, pady=(4, 16))

    # ───────────────────────────── ações ─────────────────────────────

    def _ler_parametros(self):
        textos = {campo: self.entradas[campo].get() for campo in CAMPOS}
        return parametros_dos_textos(textos, self.config.parametros)

    def iniciar(self) -> None:
        self.rotulo_erro.config(text="")
        try:
            parametros = self._ler_parametros()
        except CampoInvalido as e:
            self.rotulo_erro.config(text=str(e))
            return
        erros = validar(parametros)
        if erros:
            self.rotulo_erro.config(text=" · ".join(erros))
            return

        self.config = Configuracao(parametros=parametros, iniciar_com_windows=self.var_iniciar_windows.get())
        try:
            salvar(self.config, self.caminho_config)
        except OSError as e:
            log.warning("Não foi possível salvar a configuração: %s", e)
        self._aplicar_inicio_automatico()

        self.monitor = Monitor(parametros, self.fila.put)
        self.thread_motor = threading.Thread(target=lambda: asyncio.run(self.monitor.executar()), daemon=True)
        self.thread_motor.start()

        for campo in self.entradas.values():
            campo.config(state="disabled")
        self.botao_iniciar.config(state="disabled")
        self.botao_parar.config(state="normal")
        self.rotulo_conexao.config(text="Conectando…")
        self.root.after(200, self._verificar_fila)

    def parar(self) -> None:
        if self.monitor:
            self.monitor.parar.set()
        self.botao_parar.config(state="disabled")
        self.botao_iniciar.config(state="normal")
        for campo in self.entradas.values():
            campo.config(state="normal")
        self.rotulo_conexao.config(text="Parado")

    def _aplicar_inicio_automatico(self) -> None:
        if sys.platform != "win32":
            return
        import inicio_automatico  # import local: só faz sentido (e só importa winreg) no Windows
        try:
            inicio_automatico.definir(self.config.iniciar_com_windows, caminho_do_executavel())
        except OSError as e:
            log.warning("Não foi possível ajustar a inicialização automática: %s", e)

    # ───────────────────────────── laço de atualização ─────────────────────────────

    def _verificar_fila(self) -> None:
        while not self.fila.empty():
            av = self.fila.get_nowait()
            self._atualizar_linha(av)
            if av.sinal and (av.latencia_ms or 0) < ATRASO_MAX_POPUP_MS:
                self.popups.mostrar(av)

        motor_vivo = bool(self.thread_motor and self.thread_motor.is_alive())
        if self.monitor is not None:
            if not motor_vivo:
                self.rotulo_conexao.config(text="Encerrado")
            elif self.monitor.conectado.is_set():
                self.rotulo_conexao.config(text="Conectado")
            else:
                self.rotulo_conexao.config(
                    text=f"Reconectando… ({self.monitor.reconexoes} tentativa(s))"
                )
        if motor_vivo:
            self.root.after(200, self._verificar_fila)

    def _atualizar_linha(self, av: Avaliacao) -> None:
        try:
            from datetime import datetime

            hora = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000).strftime("%H:%M")
        except Exception:  # nunca deixa uma falha de formatação derrubar a janela
            hora = "—"
        rsi_texto = formatar_num(av.rsi) if av.rsi is not None else "—"
        setor_texto = av.setor or "—"
        if av.simbolo in self.linhas_status:
            self.tabela.item(av.simbolo, values=(rsi_texto, setor_texto, av.fechamento_texto, hora))

    def _ao_fechar(self) -> None:
        if self.monitor:
            self.monitor.parar.set()
            if self.thread_motor:
                self.thread_motor.join(timeout=2)
        self.root.destroy()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    root = tk.Tk()
    Aplicativo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
