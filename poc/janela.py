"""
Janela de configuração — Opção B (Completa), Seção 5 da proposta.
===================================================================

Fica só a parte de UI aqui: os campos usam campos_formulario.py (texto <->
Parametros) e a configuração salva usa configuracao.py — nenhuma lógica de
RSI/setor/cruzamento é duplicada, tudo isso continua só em alerta_futuros.py.
A gravação em CSV usa o mesmo Registro do CLI (--sem-popup): cada "Iniciar"
abre um arquivo novo em poc/logs/, "Parar" ou fechar de vez grava e fecha —
sem isso o item "Registro CSV de fechamentos e sinais" da proposta ficaria
descumprido quando o app roda pela janela (era o caso até 19/09/2026).

Fluxo de threads (igual ao --sem-popup/--demo do CLI, já usado em produção):
  Monitor.executar() roda numa thread própria (asyncio); a única coisa que
  ela faz que toca a janela é colocar cada Avaliacao numa queue.Queue. Quem
  lê a fila e atualiza os widgets é sempre a thread principal, via
  root.after — Tkinter não é thread-safe, então nada de rede/asyncio pode
  chamar métodos de widget diretamente. A mesma regra vale para o ícone de
  bandeja (bandeja.py): seus callbacks rodam na thread do pystray.

Bandeja do sistema (ícone perto do relógio, Seção 5): ao fechar a janela
(X), o app minimiza para a bandeja em vez de encerrar — "Sair" é só pelo
menu da bandeja (ou Ctrl+C no console). Se a bandeja não estiver disponível
no ambiente (sem suporte de tray, ex.: alguns Linux sem área de notificação),
cai no comportamento antigo: fechar a janela encerra o app de vez.

Uso:
  python janela.py               # abre a janela
  python janela.py --minimizado  # já sobe minimizado na bandeja (usado pelo início automático)
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from alerta_futuros import ATRASO_MAX_POPUP_MS, MS_5M, PARES, Avaliacao, Monitor, Popups, Registro, formatar_num
from campos_formulario import CAMPOS, ROTULOS, CampoInvalido, parametros_dos_textos, textos_de
from configuracao import Configuracao, carregar, salvar, validar

log = logging.getLogger("alerta.janela")

PASTA_LOGS = Path(__file__).with_name("logs")

# O ícone de bandeja (pystray) sobe um laço GTK que, fora do Windows, compete com o laço de
# eventos do Tk e faz os botões pararem de responder a cliques (relato do Lucas no Ubuntu 26 em
# 20/09/2026, reproduzido com clique sintético via XTEST: 1/5 com bandeja, 4/5 sem). O Windows
# é a plataforma de destino do .exe e usa o backend win32 do pystray, sem GTK no meio — lá a
# bandeja continua ligada. ALERTA_FUTUROS_BANDEJA=1 força ligar (para testar), =0 força desligar.
def _bandeja_habilitada() -> bool:
    forcado = os.environ.get("ALERTA_FUTUROS_BANDEJA")
    if forcado is not None:
        return forcado.strip() not in ("", "0", "nao", "não", "false")
    return sys.platform == "win32"


BANDEJA_HABILITADA = _bandeja_habilitada()

# Página de "outras versões" (Opção A, Opção B, versão com IA) — subdomínio publicado em
# 20/09/2026 (Cloudflare Pages, projeto "alerta-futuros-versoes"). Conteúdo comercial (preços/
# escopo da Opção A e da versão com IA) ainda é rascunho — ver aviso na própria página.
URL_OUTRAS_VERSOES = "https://futuros.blumenauti.com.br/"


def abrir_outras_versoes() -> None:
    """Callback do link/botão "Conhecer outras versões" — abre no navegador padrão do usuário.
    Função separada (em vez de webbrowser.open direto no bind) só pra dar pra testar sem precisar
    de um tk.Tk() real (ver test_janela.py)."""
    webbrowser.open(URL_OUTRAS_VERSOES)


def construir_ao_avaliar(registro: Registro, fila: "queue.Queue[Avaliacao]"):
    """Callback passado ao Monitor: grava no CSV (igual ao CLI) e só depois publica na fila da
    UI. Separado de Aplicativo.iniciar() de propósito — assim dá pra testar sem precisar de um
    tk.Tk() real (ver test_janela.py)."""

    def ao_avaliar(av: Avaliacao) -> None:
        registro.gravar(av)
        fila.put(av)

    return ao_avaliar

FUNDO = "#111827"
FUNDO_CAMPO = "#1f2937"
TEXTO = "#f9fafb"
TEXTO_FRACO = "#9ca3af"
VERDE = "#22c55e"
VERMELHO = "#ef4444"
FONTE = ("Segoe UI", 10)


def _resolver_fonte(root: tk.Tk) -> tuple[str, int]:
    """'Segoe UI' só existe no Windows (a plataforma de destino do .exe) — num Linux sem essa
    fonte instalada (achado em 20/09/2026, teste do Lucas no Ubuntu), o Tk cai num fallback que
    renderiza os campos como blocos cinza ilegíveis em vez de dígitos, em vez de simplesmente usar
    outra fonte legível. 'Helvetica' é um alias que o Tk sempre resolve pra alguma sans-serif
    disponível em qualquer plataforma (inclusive Windows/Mac), então serve de rede de segurança
    sem mudar nada de como o app aparece no Windows de verdade."""
    familia, tamanho = FONTE
    if familia in tkfont.families(root):
        return FONTE
    return ("Helvetica", tamanho)


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
        self.registro: Registro | None = None
        self.bandeja = None  # type: "bandeja.Bandeja | None"  # noqa: F821 (import tardio, ver _configurar_bandeja)

        self._montar(root)
        self.popups = Popups(root, self.config.parametros.popup_segundos)
        self._configurar_bandeja(root)

    def _configurar_bandeja(self, root: tk.Tk) -> None:
        if not BANDEJA_HABILITADA:
            log.info("Bandeja desligada nesta plataforma (%s): fechar a janela encerra o app. "
                     "Motivo: o laço GTK do pystray engole cliques do Tk fora do Windows "
                     "(medido em 20/09/2026 no Ubuntu: 1 de 5 cliques respondia com bandeja, "
                     "4 de 5 sem ela). Force com ALERTA_FUTUROS_BANDEJA=1.", sys.platform)
            self.bandeja = None
            root.protocol("WM_DELETE_WINDOW", self.encerrar_de_vez)
            return
        try:
            from bandeja import Bandeja

            self.bandeja = Bandeja(root, self)
            self.bandeja.iniciar()
            root.protocol("WM_DELETE_WINDOW", self._minimizar_para_bandeja)
            # a criação do ícone pode dar certo e o .run() falhar logo depois, numa thread
            # separada (achado em 19/09/2026) — confere em 300ms se a thread já não nasceu morta,
            # senão a janela fica "configurada" pra minimizar sem nenhum ícone real pra reabrir.
            root.after(300, self._verificar_bandeja_subiu)
        except Exception as e:  # sem suporte de bandeja no ambiente — cai no fechar-de-vez antigo
            log.warning("Ícone de bandeja não disponível (%s); fechar a janela agora encerra o app.", e)
            self.bandeja = None
            root.protocol("WM_DELETE_WINDOW", self.encerrar_de_vez)

    def _verificar_bandeja_subiu(self) -> None:
        if self.bandeja is not None and not self.bandeja.thread_viva():
            log.warning("A thread do ícone de bandeja morreu logo após iniciar; fechar a janela "
                        "agora encerra o app, como se não houvesse bandeja.")
            self._bandeja_falhou_em_tempo_de_execucao()

    def _bandeja_falhou_em_tempo_de_execucao(self) -> None:
        """Chamado por bandeja.py (ou por _verificar_bandeja_subiu) quando a thread do pystray
        morre — na criação parecia ter dado certo, mas nenhum ícone real existe. Sem isso, fechar
        a janela (X) minimizaria pra um ícone que não existe, deixando o usuário sem jeito de
        reabrir o app a não ser matando o processo."""
        self.bandeja = None
        self.root.protocol("WM_DELETE_WINDOW", self.encerrar_de_vez)
        self.root.deiconify()
        self.root.lift()

    def _minimizar_para_bandeja(self) -> None:
        self.root.withdraw()

    # ───────────────────────────── montagem da janela ─────────────────────────────

    def _montar(self, root: tk.Tk) -> None:
        global FONTE
        FONTE = _resolver_fonte(root)

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
            # Nota: este label só aparece justamente na plataforma (não-Windows) onde 'Segoe UI'
            # normalmente não existe — por isso usa FONTE (já resolvido por _resolver_fonte()
            # acima) em vez de hardcodar a fonte de novo aqui.
            tk.Label(campos, text="(disponível só no Windows)", bg=FUNDO, fg=TEXTO_FRACO,
                      font=(FONTE[0], 8)).grid(row=len(CAMPOS) + 1, column=0, columnspan=2, sticky="w")

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
        self._montar_rodape(root)

    def _montar_rodape(self, root: tk.Tk) -> None:
        """Link pra página de "outras versões" (Opção A, Opção B, versão com IA) — pedido do
        Hugo/Lucas em 19/09/2026 pra já ir acessível a partir da versão que vai pro cliente
        agora como MVP, mesmo a página em si ainda não existindo (ver URL_OUTRAS_VERSOES)."""
        rodape = tk.Frame(root, bg=FUNDO, padx=16)
        rodape.pack(fill="x", pady=(0, 10))
        link = tk.Label(rodape, text="Conhecer outras versões →", bg=FUNDO,
                          fg=TEXTO_FRACO, font=(FONTE[0], 9, "underline"), cursor="hand2")
        link.pack(anchor="e")
        link.bind("<Button-1>", lambda _evt: abrir_outras_versoes())

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

        self.registro = Registro(PASTA_LOGS)
        self.monitor = Monitor(parametros, construir_ao_avaliar(self.registro, self.fila))
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
        if self.registro:
            self.registro.fechar()
            self.registro = None
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

    def encerrar_de_vez(self) -> None:
        """Sai de verdade: para o monitor, fecha o CSV, derruba o ícone de bandeja (se houver)
        e destrói a janela. Chamado pelo "Sair" da bandeja, por Ctrl+C no console, ou ao fechar
        a janela quando não há bandeja disponível neste ambiente."""
        if self.monitor:
            self.monitor.parar.set()
            if self.thread_motor:
                self.thread_motor.join(timeout=2)
        if self.registro:
            self.registro.fechar()
            self.registro = None
        if self.bandeja:
            self.bandeja.parar()
        self.root.destroy()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    root = tk.Tk()
    app = Aplicativo(root)
    if "--minimizado" in sys.argv[1:]:
        root.withdraw()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        # mesmo tratamento do --sem-popup/--demo no CLI: Ctrl+C no console encerra o
        # monitor de forma limpa (thread parada, CSV fechado) em vez de deixar o
        # traceback do KeyboardInterrupt subir a partir do mainloop.
        app.encerrar_de_vez()


if __name__ == "__main__":
    main()
