"""
Janela de configuração — Opção B (Completa), Seção 5 da proposta.
===================================================================

Fica só a parte de UI aqui: os campos usam campos_formulario.py (texto <->
Parametros) e a configuração salva usa configuracao.py — nenhuma lógica de
RSI/setor/cruzamento é duplicada, tudo isso continua só em alerta_futuros.py.
As cores, fontes e a escala de DPI vêm de tema.py; as partes desenhadas (eixo de
RSI por par, diagrama da vela de 15m, indicador de estado) de componentes.py.
A gravação em CSV usa o mesmo Registro do CLI (--sem-popup): cada "Iniciar"
abre um arquivo novo em poc/logs/, "Parar" ou fechar de vez grava e fecha —
sem isso o item "Registro CSV de fechamentos e sinais" da proposta ficaria
descumprido quando o app roda pela janela (era o caso até 19/09/2026).

Como a janela é organizada (redesenho de 22/09/2026, ver tema.py pra paleta):
  - a regra do cliente aparece como frases, com os números como lacunas
    ("Abaixo: RSI até [5]") — em vez de "rótulo: caixa" numa grade;
  - o diagrama da vela de 15m e a régua do RSI no quadro de situação se
    redesenham a cada tecla digitada, mostrando o que cada número significa;
  - só um botão "chama" por vez (o dourado): Iniciar antes, Parar durante.

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
from datetime import datetime
from pathlib import Path

from alerta_futuros import (
    ATRASO_MAX_POPUP_MS, LIMITE_PARES, PARES, Avaliacao, Monitor, Parametros, Popups, Registro,
    baixar_casas_decimais, pares_desconhecidos, resolver_pares,
)
from campos_formulario import (
    CAMPOS, CampoInvalido, pares_do_texto, parametros_dos_textos, texto_dos_pares, textos_de,
)
from componentes import DiagramaVela15, Indicador, PainelPares, estado_do_monitor, proxima_avaliacao
from configuracao import Configuracao, carregar, salvar, validar, validar_pares
from tema import (
    BORDA, CAMINHO_ICONE, CAMPO, FUNDO, LINHA, OURO, OURO_ATIVO, OURO_TEXTO, PAINEL, TEXTO, TEXTO_APAGADO,
    TEXTO_FRACO, VERMELHO, Tema, preparar_dpi,
)

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
    """Callback do link "Conhecer outras versões" — abre no navegador padrão do usuário.
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


# Largura de tela a partir da qual a janela usa duas colunas (regra à esquerda, quadro de
# situação à direita) em vez de empilhar tudo. Com 16 pares (pedido do cliente em 23/09/2026) o
# empilhado passa de 1000 px de altura e não cabe num notebook; lado a lado o mesmo conteúdo fica
# em ~620 px de altura e sobra tela de sobra. Abaixo desta largura volta ao empilhado de sempre.
LARGURA_MIN_LADO_A_LADO = 1280


def altura_maxima_do_quadro(altura_tela: int, altura_do_resto: int, minimo: int = 120) -> int:
    """Quanto o quadro de situação pode ocupar sem que a janela passe da tela.

    Existe por causa do teto de 16 pares (23/09/2026): o quadro dobra de altura e, num notebook
    de 768 px, a janela inteira passaria de 830 px — os botões Iniciar/Parar ficariam abaixo da
    borda de baixo, fora do alcance. `altura_do_resto` é tudo que não é o quadro (cabeçalho,
    regra, botões, rodapé) e os 10% descontados cobrem barra de tarefas e moldura da janela.
    Nunca devolve menos que `minimo`: é melhor a janela ficar um pouco alta numa tela minúscula
    do que o quadro virar uma fresta de uma linha."""
    disponivel = int(altura_tela * 0.90) - altura_do_resto
    return max(minimo, disponivel)


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
        self.entradas: dict[str, tk.Entry] = {}
        self.var_iniciar_windows = tk.BooleanVar(value=self.config.iniciar_com_windows)
        self.registro: Registro | None = None
        self.bandeja = None  # type: "bandeja.Bandeja | None"  # noqa: F821 (import tardio, ver _configurar_bandeja)
        # últimos parâmetros coerentes digitados: é o que o diagrama e a régua desenham enquanto o
        # usuário edita (um campo pela metade não apaga o desenho, só não o atualiza)
        self._parametros_desenho: Parametros = self.config.parametros

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
        self.tema = Tema(root)
        px = self.tema.px
        root.title("Alerta Futuros")
        root.configure(bg=FUNDO)
        root.resizable(False, False)
        self._definir_icone(root)

        # Duas colunas em tela larga (ver LARGURA_MIN_LADO_A_LADO): a regra fica à esquerda e o
        # quadro de situação à direita, em altura cheia. É o que dá lugar aos 16 pares sem a
        # janela virar uma coluna de mais de mil pixels.
        self.lado_a_lado = root.winfo_screenwidth() >= LARGURA_MIN_LADO_A_LADO
        corpo = tk.Frame(root, bg=FUNDO)
        corpo.pack(fill="both", expand=True)
        if self.lado_a_lado:
            self.coluna_esquerda = tk.Frame(corpo, bg=FUNDO)
            self.coluna_esquerda.grid(row=0, column=0, sticky="nw")
            self.coluna_direita = tk.Frame(corpo, bg=FUNDO)
            self.coluna_direita.grid(row=0, column=1, sticky="nw", padx=(px(8), 0))
        else:
            self.coluna_esquerda = self.coluna_direita = corpo

        self._montar_cabecalho(self.coluna_esquerda)
        self._montar_regra(self.coluna_esquerda)
        self._montar_acoes(self.coluna_esquerda)
        # o rodapé é montado antes do quadro de propósito: o quadro precisa saber quanto de
        # altura sobra na tela, e isso só dá pra medir com todo o resto da janela já montado
        # (ver _montar_quadro_situacao). No empilhado ele entra no lugar certo com pack(before=),
        # e por isso precisa morar no MESMO pai do quadro — pack(before=) não atravessa pais.
        self._montar_rodape(root if self.lado_a_lado else corpo)
        self._montar_quadro_situacao(root)
        self._aquecer_casas_decimais()

    def _definir_icone(self, root: tk.Tk) -> None:
        """Logo da Blumenau TI na barra de título e na barra de tarefas (sem isso o Tk mostra a
        pena genérica dele). Mesmo arquivo do ícone de bandeja; se faltar, segue sem ícone."""
        try:
            self._icone = tk.PhotoImage(file=str(CAMINHO_ICONE))
            root.iconphoto(True, self._icone)
        except tk.TclError as e:
            log.debug("Ícone da janela não carregado (%s).", e)

    def _montar_cabecalho(self, root: tk.Misc) -> None:
        px, tema = self.tema.px, self.tema
        cabecalho = tk.Frame(root, bg=FUNDO, padx=px(20))
        cabecalho.pack(fill="x", pady=(px(12), 0))
        linha = tk.Frame(cabecalho, bg=FUNDO)
        linha.pack(fill="x")
        tk.Label(linha, text="Alerta Futuros", bg=FUNDO, fg=TEXTO, font=tema.numeros(17)).pack(side="left")
        self.indicador = Indicador(linha, tema)
        self.indicador.pack(side="right")
        self.rotulo_subtitulo = tk.Label(cabecalho, text=self._texto_subtitulo(), bg=FUNDO, fg=TEXTO_FRACO,
                                         font=tema.texto(9))
        self.rotulo_subtitulo.pack(anchor="w", pady=(px(2), 0))

    def _texto_subtitulo(self) -> str:
        n = len(self.config.pares)
        pares = "1 par" if n == 1 else f"{n} pares"
        return f"Acompanha {pares} da Binance Futuros e avisa quando a regra acontece."

    def _montar_regra(self, root: tk.Misc) -> None:
        px, tema = self.tema.px, self.tema
        textos = textos_de(self.config.parametros)
        regra = tk.Frame(root, bg=FUNDO, padx=px(20))
        regra.pack(fill="x", pady=(px(12), 0))

        self._titulo(regra, "RSI(2) no fechamento da vela de 5 minutos")
        frase = self._frase(regra)
        self._palavras(frase, "Abaixo: RSI até")
        self._campo(frase, "rsi_abaixo", textos)
        self._palavras(frase, "Acima: RSI a partir de", antes=px(18))
        self._campo(frase, "rsi_acima", textos)

        grupo = tk.Frame(regra, bg=FUNDO)
        grupo.pack(fill="x", pady=(px(10), 0))
        coluna = tk.Frame(grupo, bg=FUNDO)
        coluna.pack(side="left")
        self._titulo(coluna, "Vela de 15 minutos")
        frase = self._frase(coluna)
        self._palavras(frase, "Setores A e C:")
        self._campo(frase, "setor_pct", textos)
        self._palavras(frase, "% da vela em cada ponta")
        frase = self._frase(coluna)
        self._palavras(frase, "Só conta se a vela tiver ao menos")
        self._campo(frase, "tamanho_min_pct", textos)
        self._palavras(frase, "% de tamanho")
        self.diagrama = DiagramaVela15(grupo, tema, self.config.parametros.setor_pct)
        self.diagrama.pack(side="left", padx=(px(22), 0))

        self._titulo(regra, "Preço-alvo", acima=px(10))
        frase = self._frase(regra)
        self._campo(frase, "ajuste_pct", textos, primeiro=True)
        self._palavras(frase, "% acima do fechamento (W) ou abaixo dele (Z)")

        self._montar_campo_pares(regra)

        tk.Checkbutton(regra, text="Iniciar junto com o Windows", variable=self.var_iniciar_windows,
                       bg=FUNDO, fg=TEXTO, selectcolor=CAMPO, activebackground=FUNDO, activeforeground=TEXTO,
                       highlightthickness=0, font=tema.texto(10)).pack(anchor="w", pady=(px(12), 0))
        if sys.platform != "win32":
            tk.Label(regra, text="(disponível só no Windows)", bg=FUNDO, fg=TEXTO_APAGADO,
                     font=tema.texto(8)).pack(anchor="w", padx=(px(24), 0))

    def _montar_campo_pares(self, regra: tk.Frame) -> None:
        """Lista de pares acompanhados — editável desde 23/09/2026, quando o teto subiu de 8 para
        16. É um Text de 3 linhas, e não um Entry de uma linha, porque 16 símbolos dão ~130
        caracteres: numa linha só o cliente teria que rolar o campo de lado para enxergar o que
        digitou. Aceita espaço, vírgula ou quebra de linha (ver campos_formulario.pares_do_texto),
        pra poder colar a lista do jeito que ele tiver em mãos."""
        px, tema = self.tema.px, self.tema
        self._titulo(regra, "Pares acompanhados", acima=px(10))
        # width em caracteres: o padrão do Text é 80, o que sozinho esticaria a coluna da regra
        # para ~660 px e estouraria a largura da tela no layout lado a lado. O fill="x" do pack
        # faz o campo acompanhar a coluna de qualquer jeito.
        self.entrada_pares = tk.Text(regra, height=3, width=40, wrap="word", font=tema.numeros(10),
                                     bg=CAMPO, fg=TEXTO, insertbackground=OURO, relief="flat", bd=0,
                                     highlightthickness=1, highlightbackground=BORDA, highlightcolor=OURO,
                                     padx=px(6), pady=px(5))
        self.entrada_pares.insert("1.0", texto_dos_pares(self.config.pares))
        self.entrada_pares.pack(fill="x", pady=(px(3), 0))
        self.entrada_pares.bind("<KeyRelease>", lambda _evt: self._marcar_erro_pares(False))
        tk.Label(regra, text=f"Símbolo como aparece na Binance (BTCUSDT), separados por espaço ou vírgula. "
                             f"No máximo {LIMITE_PARES}. Vale a partir do próximo “Iniciar”.",
                 bg=FUNDO, fg=TEXTO_APAGADO, font=tema.texto(8), wraplength=px(392),
                 justify="left").pack(anchor="w", pady=(px(3), 0))

    def _titulo(self, master: tk.Misc, texto: str, acima: int = 0) -> None:
        tk.Label(master, text=texto, bg=FUNDO, fg=TEXTO, font=self.tema.texto(10, "bold")).pack(
            anchor="w", pady=(acima, self.tema.px(2)))

    def _frase(self, master: tk.Misc) -> tk.Frame:
        frase = tk.Frame(master, bg=FUNDO)
        frase.pack(anchor="w", pady=(self.tema.px(3), 0))
        return frase

    def _palavras(self, frase: tk.Frame, texto: str, antes: int = 0) -> None:
        tk.Label(frase, text=texto, bg=FUNDO, fg=TEXTO_FRACO, font=self.tema.texto(10)).pack(
            side="left", padx=(antes, 0))

    def _campo(self, frase: tk.Frame, campo: str, textos: dict[str, str], primeiro: bool = False) -> None:
        """Lacuna numérica dentro da frase: número em Bahnschrift, borda que fica dourada com o
        foco e vermelha quando o valor não é aceito (ver _marcar_erro)."""
        px = self.tema.px
        entrada = tk.Entry(frase, width=5, justify="right", font=self.tema.numeros(11),
                           bg=CAMPO, fg=TEXTO, insertbackground=OURO, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDA, highlightcolor=OURO,
                           disabledbackground=PAINEL, disabledforeground=TEXTO_FRACO)
        entrada.insert(0, textos[campo])
        entrada.pack(side="left", padx=(0 if primeiro else px(6), px(6)), ipady=px(3))
        entrada.bind("<KeyRelease>", lambda _evt, c=campo: self._ao_editar(c))
        self.entradas[campo] = entrada

    def _montar_acoes(self, root: tk.Misc) -> None:
        px, tema = self.tema.px, self.tema
        acoes = tk.Frame(root, bg=FUNDO, padx=px(20))
        acoes.pack(fill="x", pady=(px(14), 0))
        opcoes = dict(relief="flat", bd=0, padx=px(16), pady=px(6), font=tema.texto(10, "bold"),
                      highlightthickness=1, highlightcolor=TEXTO)
        self.botao_iniciar = tk.Button(acoes, text="Iniciar monitoramento", command=self.iniciar, **opcoes)
        self.botao_iniciar.pack(side="left")
        self.botao_parar = tk.Button(acoes, text="Parar monitoramento", command=self.parar, **opcoes)
        self.botao_parar.pack(side="left", padx=(px(10), 0))
        self._estilizar_botoes(rodando=False)

        self.rotulo_erro = tk.Label(root, text="", bg=FUNDO, fg=VERMELHO, font=tema.texto(9),
                                    wraplength=px(392), justify="left", anchor="w")
        self.rotulo_erro.pack(fill="x", padx=px(20), pady=(px(4), 0))

    def _estilizar_botoes(self, rodando: bool) -> None:
        """Só um botão "chama" por vez — o dourado é o que faz sentido apertar agora."""
        principal, secundario = (self.botao_parar, self.botao_iniciar) if rodando else (self.botao_iniciar, self.botao_parar)
        principal.configure(state="normal", bg=OURO, fg=OURO_TEXTO, activebackground=OURO_ATIVO,
                            activeforeground=OURO_TEXTO, highlightbackground=OURO, cursor="hand2")
        secundario.configure(state="disabled", bg=FUNDO, fg=TEXTO_APAGADO, disabledforeground=TEXTO_APAGADO,
                             activebackground=FUNDO, highlightbackground=BORDA, cursor="")

    def _montar_quadro_situacao(self, root: tk.Tk) -> None:
        """Monta o quadro com a lista de pares atual, limitado ao que sobra de tela. Chamado de
        novo (via _reconstruir_quadro) sempre que a lista de pares muda — o quadro tem uma linha
        fixa por par, então trocar a lista é refazer o quadro."""
        px = self.tema.px
        root.update_idletasks()  # sem isso winfo_reqheight() ainda devolve o "1" inicial do Tk
        # Empilhado, o quadro divide a altura com tudo que já está montado; lado a lado ele tem a
        # coluna inteira, e só o rodapé (que atravessa as duas) desconta.
        resto = self.rodape.winfo_reqheight() + px(24) if self.lado_a_lado else root.winfo_reqheight()
        altura_max = altura_maxima_do_quadro(root.winfo_screenheight(), resto)
        p = self.config.parametros
        self.painel = PainelPares(self.coluna_direita, self.tema, self.config.pares,
                                  p.rsi_abaixo, p.rsi_acima, altura_max)
        posicao = {} if self.lado_a_lado else {"before": self.rodape}
        self.painel.pack(fill="x", pady=(px(10), 0), **posicao)

    def _reconstruir_quadro(self) -> None:
        self.painel.destroy()
        self._montar_quadro_situacao(self.root)
        self.rotulo_subtitulo.config(text=self._texto_subtitulo())

    def _aquecer_casas_decimais(self) -> None:
        """Baixa em segundo plano as casas decimais dos pares da Binance, se a lista tiver algum
        par fora da tabela do cliente. É só pra que o clique em "Iniciar" não fique esperando um
        download de alguns MB — se não der tempo (ou não tiver internet), iniciar() consulta na
        hora e, no pior caso, o par novo sai com CASAS_PADRAO casas."""
        if all(s in PARES for s in self.config.pares):
            return
        threading.Thread(target=baixar_casas_decimais, daemon=True).start()

    def _montar_rodape(self, root: tk.Misc) -> None:
        """Esquerda: onde o registro é gravado (parado) ou a hora da próxima avaliação (rodando).
        Direita: link pra página de "outras versões" (Opção A, Opção B, versão com IA) — pedido do
        Hugo/Lucas em 19/09/2026 pra já ir acessível a partir da versão que vai pro cliente agora
        como MVP (ver URL_OUTRAS_VERSOES)."""
        px, tema = self.tema.px, self.tema
        rodape = self.rodape = tk.Frame(root, bg=FUNDO, padx=px(20))
        rodape.pack(fill="x", pady=(px(8), px(8)))
        self.rotulo_rodape = tk.Label(rodape, text=self._texto_rodape_parado(), bg=FUNDO, fg=TEXTO_APAGADO,
                                      font=tema.texto(9))
        self.rotulo_rodape.pack(side="left")
        link = tk.Label(rodape, text="Conhecer outras versões", bg=FUNDO, fg=TEXTO_FRACO,
                        font=tema.texto(9, "underline"), cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda _evt: abrir_outras_versoes())

    @staticmethod
    def _texto_rodape_parado() -> str:
        return f"Cada fechamento avaliado é gravado na pasta {PASTA_LOGS.name}."

    # ───────────────────────────── ações ─────────────────────────────

    def _ler_parametros(self):
        textos = {campo: self.entradas[campo].get() for campo in CAMPOS}
        return parametros_dos_textos(textos, self.config.parametros)

    def _parametros_validos(self) -> Parametros | None:
        """Parametros dos campos se todos forem números aceitos e coerentes entre si; senão None
        (usado pelo redesenho ao vivo, que nunca mostra erro — isso é papel de iniciar())."""
        try:
            p = self._ler_parametros()
        except CampoInvalido:
            return None
        return None if validar(p) else p

    def _ao_editar(self, campo: str) -> None:
        self._marcar_erro(campo, False)
        p = self._parametros_validos()
        if p is None:
            return
        self._parametros_desenho = p
        self.diagrama.atualizar(p.setor_pct)
        self.painel.definir_faixas(p.rsi_abaixo, p.rsi_acima)

    def _habilitar_campos(self, habilitar: bool) -> None:
        """Enquanto o monitor roda os campos ficam travados e visivelmente apagados (borda some):
        mudar um número no meio da execução não teria efeito até o próximo Iniciar."""
        for entrada in self.entradas.values():
            entrada.config(state="normal" if habilitar else "disabled",
                           highlightbackground=BORDA if habilitar else LINHA)
        self.entrada_pares.config(state="normal" if habilitar else "disabled",
                                  highlightbackground=BORDA if habilitar else LINHA)

    def _marcar_erro(self, campo: str, com_erro: bool) -> None:
        cor = VERMELHO if com_erro else BORDA
        self.entradas[campo].configure(highlightbackground=cor, highlightcolor=VERMELHO if com_erro else OURO)

    def _marcar_erro_pares(self, com_erro: bool) -> None:
        self.entrada_pares.configure(highlightbackground=VERMELHO if com_erro else BORDA,
                                     highlightcolor=VERMELHO if com_erro else OURO)

    def _ler_pares(self) -> list[str]:
        return pares_do_texto(self.entrada_pares.get("1.0", "end"))

    def iniciar(self) -> None:
        self.rotulo_erro.config(text="")
        for campo in CAMPOS:
            self._marcar_erro(campo, False)
        self._marcar_erro_pares(False)
        try:
            parametros = self._ler_parametros()
        except CampoInvalido as e:
            if e.campo in self.entradas:
                self._marcar_erro(e.campo, True)
            self.rotulo_erro.config(text=str(e))
            return
        erros = validar(parametros)
        pares = self._ler_pares()
        erros_pares = validar_pares(pares)
        if not erros_pares:
            # só depois do formato estar certo: esta checagem custa uma consulta à Binance
            desconhecidos = pares_desconhecidos(pares)
            if desconhecidos:
                erros_pares.append(f"A Binance não tem esses pares em Futuros: {', '.join(desconhecidos)}. "
                                   "Confira a grafia (o nome costuma terminar em USDT).")
        if erros_pares:
            self._marcar_erro_pares(True)
        if erros or erros_pares:
            self.rotulo_erro.config(text="\n".join(erros + erros_pares))
            return

        mudou_pares = pares != list(self.config.pares)
        self.config = Configuracao(parametros=parametros, iniciar_com_windows=self.var_iniciar_windows.get(),
                                   pares=pares)
        try:
            salvar(self.config, self.caminho_config)
        except OSError as e:
            log.warning("Não foi possível salvar a configuração: %s", e)
        self._aplicar_inicio_automatico()
        self._parametros_desenho = parametros
        self.diagrama.atualizar(parametros.setor_pct)
        if mudou_pares:
            self._reconstruir_quadro()  # uma linha por par: lista nova = quadro novo
        self.painel.definir_faixas(parametros.rsi_abaixo, parametros.rsi_acima)

        self.registro = Registro(PASTA_LOGS)
        self.monitor = Monitor(parametros, construir_ao_avaliar(self.registro, self.fila),
                               resolver_pares(pares))
        self.thread_motor = threading.Thread(target=lambda: asyncio.run(self.monitor.executar()), daemon=True)
        self.thread_motor.start()

        self._habilitar_campos(False)
        self._estilizar_botoes(rodando=True)
        self.indicador.definir("conectando", "Conectando…")
        self.root.after(200, self._verificar_fila)

    def parar(self) -> None:
        if self.monitor:
            self.monitor.parar.set()
        if self.registro:
            self.registro.fechar()
            self.registro = None
        self._estilizar_botoes(rodando=False)
        self._habilitar_campos(True)
        self.indicador.definir("parado", "Parado")
        self.rotulo_rodape.config(text=self._texto_rodape_parado())

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
            self.painel.atualizar(av)
            if av.sinal and (av.latencia_ms or 0) < ATRASO_MAX_POPUP_MS:
                self.popups.mostrar(av)

        motor_vivo = bool(self.thread_motor and self.thread_motor.is_alive())
        if self.monitor is not None:
            chave, texto = estado_do_monitor(True, motor_vivo, self.monitor.conectado.is_set(), self.monitor.reconexoes)
            self.indicador.definir(chave, texto)
        if motor_vivo:
            proxima = proxima_avaliacao(datetime.now()).strftime("%H:%M")
            self.rotulo_rodape.config(text=f"Próxima avaliação às {proxima}.")
            self.root.after(200, self._verificar_fila)

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
    preparar_dpi()  # antes do tk.Tk(): é o que deixa a janela nítida em telas 125%/150%
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
