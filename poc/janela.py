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
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from alerta_futuros import (
    ATRASO_MAX_POPUP_MS, LIMITE_PARES, MS_5M, PARES, Avaliacao, Monitor, Parametros, Popups, Registro,
    _exemplos, baixar_casas_decimais, pares_desconhecidos, resolver_pares,
)
from campos_formulario import (
    CAMPOS, CampoInvalido, pares_do_texto, parametros_dos_textos, texto_dos_pares, textos_de,
)
from componentes import (
    BarraEspera, DiagramaVela15, Indicador, PainelPares, contagem_regressiva, estado_do_monitor,
    fracao_do_intervalo, proxima_avaliacao,
)
from configuracao import Configuracao, carregar, pasta_configuracao, salvar, validar, validar_pares
from tema import (
    BORDA, CAMINHO_ICONE, CAMPO, CIANO, FUNDO, LINHA, OURO, OURO_ATIVO, OURO_TEXTO, PAINEL, TEXTO,
    TEXTO_APAGADO, TEXTO_FRACO, VERMELHO, Tema, preparar_dpi,
)

log = logging.getLogger("alerta.janela")

# Onde o histórico CSV é gravado. No .exe NÃO pode ser ao lado de __file__: o PyInstaller
# --onefile extrai o código numa pasta temporária (_MEIxxxx) que é apagada quando o app fecha — o
# histórico sumia a cada "Sair". Achado no teste de usabilidade de 21/09/2026; a correção ficou só
# numa branch local e foi reintroduzida aqui em 24/09/2026. No .exe vai para
# %APPDATA%\AlertaFuturos\logs, junto da configuração; rodando do código-fonte continua em poc/logs.
def _pasta_logs() -> Path:
    if getattr(sys, "frozen", False):
        return pasta_configuracao() / "logs"
    return Path(__file__).with_name("logs")


PASTA_LOGS = _pasta_logs()

# Depois de quantos segundos "Conectando…" vira um aviso de demora (com o que conferir).
SEGUNDOS_CONEXAO_DEMORADA = 30


def mensagens_de_status(chave: str, n_pares: int, ultima: str | None, demorando: bool,
                        reconexoes: int) -> tuple[str, str]:
    """(título, orientação) do bloco de status, a partir da chave de estado_do_monitor().

    Existe porque o indicador sozinho ("Conectado") não responde à dúvida que o teste de
    usabilidade de 21/09/2026 mostrou ser a principal: "está funcionando ou travou?". O quadro só
    muda nos fechamentos de 15 min e pode passar horas sem sinal — então o texto diz, em cada
    estado, o que está acontecendo e o que esperar. Nunca promete sinal."""
    pares = "1 par" if n_pares == 1 else f"{n_pares} pares"
    if chave == "conectado":
        if ultima is None:
            return (f"Monitoramento ativo · {pares}",
                    "Tudo pronto. O quadro é preenchido no próximo fechamento de 15 minutos. "
                    "Um aviso só aparece se a regra acontecer.")
        return (f"Monitoramento ativo · {pares}",
                f"Última avaliação às {ultima}. \u201cSem sinal\u201d é normal — o aviso só aparece "
                "quando as duas condições coincidem.")
    if chave == "reconectando":
        return ("Sem conexão · tentando de novo",
                f"Confira a internet. A reconexão é automática ({reconexoes} tentativa(s)); os "
                "fechamentos perdidos são avaliados quando ela voltar.")
    if chave == "conectando":
        if demorando:
            return ("A conexão está demorando",
                    "Ainda buscando os dados da Binance. Confira a internet; se quiser, clique em "
                    "Parar e depois em Iniciar de novo.")
        return ("Conectando e preparando os dados…",
                "Buscando o histórico recente de cada par na Binance. Leva alguns segundos.")
    if chave == "encerrado":
        return ("Monitoramento interrompido",
                "A sessão terminou por uma falha (veja a mensagem abaixo). Clique em Iniciar para "
                "tentar de novo.")
    return ("Pronto para começar",
            "Confira os valores (ou mantenha os combinados) e clique em Iniciar monitoramento.")


def zoom_para(base: tuple[int, int], disponivel: tuple[int, int], maximo: float = 2.2) -> float:
    """Quanto ampliar o conteúdo (base = tamanho natural, em px, com zoom 1) para ocupar a área
    `disponivel` da janela maximizada sem cortar nada: a menor das duas proporções, com 4% de
    folga pras bordas. Nunca menos que 1,0 (maximizar não encolhe) nem mais que `maximo`."""
    bw, bh = base
    dw, dh = disponivel
    if bw <= 0 or bh <= 0 or dw <= 0 or dh <= 0:
        return 1.0
    z = min(dw / bw, dh / bh) * 0.96
    return round(min(max(z, 1.0), maximo), 2)


def executar_motor(monitor: Monitor, erros: "queue.Queue[str]") -> None:
    """Corpo da thread do motor. Uma exceção aqui antes só aparecia no console — sem console (o
    .exe é --windowed), a janela ficava com o botão "Parar" aceso e nada acontecendo. Agora a
    falha vira mensagem pra janela mostrar, e a janela libera o Iniciar de novo."""
    try:
        asyncio.run(monitor.executar())
    except Exception:
        log.exception("Falha no monitoramento")
        erros.put("O monitoramento foi interrompido por uma falha inesperada. "
                  "Clique em Iniciar para tentar de novo; se repetir, fale com a Blumenau TI.")

TEXTO_COMO_USAR = """O que o aplicativo faz
Acompanha dados públicos dos pares da Binance Futuros que estão na lista e mostra um aviso no canto da tela quando a sua regra acontece. Não pede senha, não acessa conta e não compra nem vende nada.

Cliquei em Iniciar. E agora?
Primeiro ele conecta e busca o histórico recente de cada par (alguns segundos). Quando aparecer "Monitoramento ativo", é só aguardar: a regra é conferida nos fechamentos de 15 minutos — :00, :15, :30 e :45. O quadro começa vazio e se preenche no primeiro fechamento.

Passou um fechamento e não apareceu aviso. Travou?
Provavelmente não. Avaliar não é o mesmo que dar sinal: se as duas condições não coincidirem, a linha do par mostra "sem sinal". Confira o status, a hora da última avaliação e a barra — enquanto ela avança até o próximo fechamento, o app está trabalhando. Horas sem nenhum aviso podem ser normais.

Como é um aviso?
Clique em "Ver exemplo de alerta". O exemplo é uma simulação: aparece no mesmo canto e do mesmo jeito que um aviso real, mas não entra no histórico. W (verde) = alvo acima do fechamento; Z (vermelho) = alvo abaixo.

Trocar ou acrescentar moedas
No campo "Pares acompanhados", escreva os símbolos como aparecem na Binance (ex.: BTCUSDT), separados por espaço ou vírgula — até 16. Vale no próximo Iniciar. Se um símbolo não existir em Futuros, a janela avisa qual é.

Tela cheia
Maximize a janela, clique em "Tela cheia" no rodapé ou aperte F11: tudo fica maior e ocupa a tela. De novo (ou F11) volta ao normal.

Posso fechar a janela?
Sim. O X só esconde a janela: o app continua rodando, com o ícone perto do relógio (às vezes dentro da setinha ^). Clique com o botão direito nele para abrir de novo ou para Sair. Mantenha o computador ligado, sem suspensão e com internet.

Histórico
Cada fechamento avaliado vai para um arquivo CSV (abre no Excel). O botão "Abrir registros" mostra a pasta.

Os avisos não são recomendação de investimento; as decisões continuam sendo suas.
Dúvidas: Blumenau TI · WhatsApp (47) 98867-7798"""

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
        # estado da sessão, lido pelo laço _verificar_fila
        self.erros_motor: "queue.Queue[str]" = queue.Queue()
        self.sessao_ativa = False
        self.inicio_sessao = 0.0
        self.avaliacoes = 0
        self.sinais = 0
        self.ultima_avaliacao: str | None = None
        self.reduzir_movimento = tk.BooleanVar(value=False)
        self.aviso_bandeja_mostrado = False
        self.janela_ajuda: tk.Toplevel | None = None
        self._laco: str | None = None
        # tela cheia: zoom atual, tamanho natural do conteúdo (medido com zoom 1) e a última
        # avaliação de cada par (pra redesenhar o quadro quando a janela é refeita no novo zoom)
        self.zoom = 1.0
        self._tamanho_base: tuple[int, int] | None = None
        self._ultimas: dict[str, Avaliacao] = {}

        self._montar(root)
        self._medir_base()
        root.bind("<F11>", lambda _e: self.alternar_tela_cheia())
        self.popups = Popups(root, self.config.parametros.popup_segundos)
        self._configurar_bandeja(root)
        # o laço roda sempre (não só com o motor vivo): é ele que percebe o motor morrer sozinho e
        # devolve a janela ao estado "pode iniciar de novo"
        self._laco = self.root.after(200, self._verificar_fila)

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
        """Na primeira vez explica pra onde a janela foi — no teste de usabilidade (21/09/2026) o
        X sem explicação foi lido como "fechei o programa", e o ícone na setinha ^ não foi achado."""
        if not self.aviso_bandeja_mostrado:
            self.aviso_bandeja_mostrado = True
            messagebox.showinfo(
                "O Alerta Futuros continua rodando",
                "Fechar esta janela não desliga o aplicativo — o monitoramento continua.\n\n"
                "Para abrir de novo: clique com o botão direito no ícone da Blumenau TI perto do "
                "relógio (ele pode estar dentro da setinha ^) e escolha Abrir.\n\n"
                "Para desligar de vez: use Sair, no mesmo menu ou no rodapé da janela.",
                parent=self.root)
        self.root.withdraw()

    # ───────────────────────────── montagem da janela ─────────────────────────────

    def _montar(self, root: tk.Tk, reconstruindo: bool = False) -> None:
        self.tema = Tema(root)
        self.tema.zoom = self.zoom
        px = self.tema.px
        root.title("Alerta Futuros")
        root.configure(bg=FUNDO)
        # Redimensionável desde 24/09/2026: o cliente pediu a janela "até da tela toda". O que
        # importa é o botão maximizar (ou F11 / "Tela cheia"): aí o conteúdo inteiro é refeito
        # ampliado (ver _acompanhar_tamanho). Arrastar a borda só dá mais fundo em volta.
        root.resizable(True, True)
        if not reconstruindo:
            self._definir_icone(root)
        # tudo mora neste quadro, centralizado: é o que é destruído e refeito ao mudar o zoom
        self.conteudo = tk.Frame(root, bg=FUNDO)
        self.conteudo.pack(expand=True)

        # Duas colunas em tela larga (ver LARGURA_MIN_LADO_A_LADO): a regra fica à esquerda e o
        # quadro de situação à direita, em altura cheia. É o que dá lugar aos 16 pares sem a
        # janela virar uma coluna de mais de mil pixels.
        self.lado_a_lado = root.winfo_screenwidth() >= LARGURA_MIN_LADO_A_LADO
        corpo = tk.Frame(self.conteudo, bg=FUNDO)
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
        # bloco de status: empilhado, logo abaixo dos botões; lado a lado, embaixo do quadro na
        # coluna da direita — a esquerda já ocupa quase toda a altura de um notebook de 768 px
        if not self.lado_a_lado:
            self._montar_status(corpo)
        # o rodapé é montado antes do quadro de propósito: o quadro precisa saber quanto de
        # altura sobra na tela, e isso só dá pra medir com todo o resto da janela já montado
        # (ver _montar_quadro_situacao). No empilhado ele entra no lugar certo com pack(before=),
        # e por isso precisa morar no MESMO pai do quadro — pack(before=) não atravessa pais.
        self._montar_rodape(self.conteudo if self.lado_a_lado else corpo)
        if self.lado_a_lado:
            self._montar_status(self.coluna_direita)
        self._montar_quadro_situacao(root)
        if not reconstruindo:
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
        regra = self.frame_regra = tk.Frame(root, bg=FUNDO, padx=px(20))
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
        acoes = self.frame_acoes = tk.Frame(root, bg=FUNDO, padx=px(20))
        acoes.pack(fill="x", pady=(px(14), 0))
        # empilhado (tela < LARGURA_MIN_LADO_A_LADO), enquanto o monitor roda, a regra — travada
        # mesmo — dá lugar a uma linha de resumo: é o que faz o quadro e o rodapé caberem num
        # 1024x768 (medido: 966 px de janela com a regra aberta). Ver _recolher_regra.
        self.rotulo_regra_resumida = tk.Label(root, text="", bg=FUNDO, fg=TEXTO_FRACO, font=tema.texto(9),
                                              anchor="w", justify="left", padx=px(20))
        opcoes = dict(relief="flat", bd=0, padx=px(16), pady=px(6), font=tema.texto(10, "bold"),
                      highlightthickness=1, highlightcolor=TEXTO)
        self.botao_iniciar = tk.Button(acoes, text="Iniciar monitoramento", command=self.iniciar, **opcoes)
        self.botao_iniciar.pack(side="left")
        self.botao_parar = tk.Button(acoes, text="Parar monitoramento", command=self.parar, **opcoes)
        self.botao_parar.pack(side="left", padx=(px(10), 0))
        self._estilizar_botoes(rodando=False)
        exemplo = tk.Label(acoes, text="Ver exemplo de alerta", bg=FUNDO, fg=TEXTO_FRACO,
                           font=tema.texto(9, "underline"), cursor="hand2")
        exemplo.pack(side="right")
        exemplo.bind("<Button-1>", lambda _evt: self.mostrar_exemplo())

        self.rotulo_erro = tk.Label(root, text="", bg=FUNDO, fg=VERMELHO, font=tema.texto(9),
                                    wraplength=px(392), justify="left", anchor="w")
        self.rotulo_erro.pack(fill="x", padx=px(20), pady=(px(4), 0))

    def _montar_status(self, root: tk.Misc) -> None:
        """Bloco "o que está acontecendo agora": título, orientação, barra de espera e o resumo da
        sessão. Veio do teste de usabilidade de 21/09/2026 (branch local nunca publicada) e foi
        reintroduzido em 24/09/2026 por cima do redesenho visual e dos 16 pares."""
        px, tema = self.tema.px, self.tema
        caixa = self.caixa_status = tk.Frame(root, bg=PAINEL, padx=px(14), pady=px(10), highlightthickness=1,
                                             highlightbackground=LINHA)
        if self.lado_a_lado:
            caixa.pack(fill="x", pady=(px(10), 0))
        else:
            caixa.configure(pady=px(7))
            caixa.pack(fill="x", padx=px(20), pady=(px(10), 0))
        largura_texto = px(580)  # as duas disposições têm ~600 px úteis nesta caixa
        titulo, orientacao = mensagens_de_status("parado", len(self.config.pares), None, False, 0)
        self.rotulo_status = tk.Label(caixa, text=titulo, bg=PAINEL, fg=TEXTO, font=tema.texto(11, "bold"),
                                      anchor="w", justify="left")
        self.rotulo_status.pack(fill="x")
        self.rotulo_orientacao = tk.Label(caixa, text=orientacao, bg=PAINEL, fg=TEXTO_FRACO, font=tema.texto(9),
                                          anchor="w", justify="left", wraplength=largura_texto)
        self.rotulo_orientacao.pack(fill="x", pady=(px(3), 0))
        self.barra_espera = BarraEspera(caixa, tema)
        self.barra_espera.configure(bg=PAINEL)
        self.barra_espera.pack(fill="x", pady=(px(9), px(5)))
        linha = tk.Frame(caixa, bg=PAINEL)
        linha.pack(fill="x")
        self.rotulo_proxima = tk.Label(linha, text="Avaliações às :00, :15, :30 e :45.", bg=PAINEL, fg=TEXTO_FRACO,
                                       font=tema.texto(9), anchor="w")
        self.rotulo_proxima.pack(side="left")
        tk.Checkbutton(linha, text="Reduzir movimento", variable=self.reduzir_movimento,
                       command=self._atualizar_barra, bg=PAINEL, fg=TEXTO_APAGADO, selectcolor=CAMPO,
                       activebackground=PAINEL, activeforeground=TEXTO, highlightthickness=0,
                       font=tema.texto(8)).pack(side="right")
        self.rotulo_resumo = tk.Label(caixa, text="", bg=PAINEL, fg=TEXTO_APAGADO, font=tema.texto(8), anchor="w")
        self.rotulo_resumo.pack(fill="x", pady=(px(2), 0))

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
        if self.lado_a_lado:
            resto = self.rodape.winfo_reqheight() + self.caixa_status.winfo_reqheight() + px(34)
        else:
            resto = root.winfo_reqheight()
        # ampliada (tela cheia), o zoom já foi calculado pra caber tudo: sem teto nem rolagem
        altura_max = None if self.zoom > 1.0 else altura_maxima_do_quadro(root.winfo_screenheight(), resto)
        p = self.config.parametros
        self.painel = PainelPares(self.coluna_direita, self.tema, self.config.pares,
                                  p.rsi_abaixo, p.rsi_acima, altura_max)
        posicao = {"before": self.caixa_status} if self.lado_a_lado else {"before": self.rodape}
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
        # da direita pra esquerda: Sair · outras versões · Abrir registros · Como usar
        for texto, acao in (("Sair", self.encerrar_de_vez),
                            ("Conhecer outras versões", abrir_outras_versoes),
                            ("Abrir registros", self.abrir_registros),
                            ("Como usar", self.mostrar_ajuda),
                            ("Tela cheia", self.alternar_tela_cheia)):
            link = tk.Label(rodape, text=texto, bg=FUNDO, fg=TEXTO_FRACO,
                            font=tema.texto(9, "underline"), cursor="hand2")
            link.pack(side="right", padx=(px(14), 0))
            link.bind("<Button-1>", lambda _evt, a=acao: a())

    @staticmethod
    def _texto_rodape_parado() -> str:
        return "Histórico em CSV: botão Abrir registros."

    # ───────────────────────────── ajuda, exemplo, registros ─────────────────────────────

    def mostrar_exemplo(self) -> None:
        """Mostra o MESMO pop-up de um sinal real, no mesmo canto, com o título trocado por
        "SIMULAÇÃO" — é pra o cliente reconhecer o aviso quando ele vier de verdade. Não passa pela
        fila nem pelo Registro: não entra no CSV nem nos contadores."""
        av = _exemplos()[0]
        self.popups.mostrar(av, titulo="SIMULAÇÃO · exemplo, não é sinal real")

    def mostrar_ajuda(self) -> None:
        if self.janela_ajuda is not None and self.janela_ajuda.winfo_exists():
            self.janela_ajuda.deiconify()
            self.janela_ajuda.lift()
            return
        px, tema = self.tema.px, self.tema
        janela = self.janela_ajuda = tk.Toplevel(self.root)
        janela.title("Alerta Futuros — Como usar")
        janela.configure(bg=FUNDO)
        janela.transient(self.root)
        texto = tk.Text(janela, wrap="word", bg=FUNDO, fg=TEXTO, font=tema.texto(10), relief="flat", bd=0,
                        padx=px(18), pady=px(14), width=62, height=26, highlightthickness=0,
                        spacing1=px(1), spacing3=px(3))
        barra = tk.Scrollbar(janela, command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        texto.pack(fill="both", expand=True)
        texto.tag_configure("titulo", font=tema.texto(11, "bold"), foreground=OURO, spacing1=px(10))
        for bloco in TEXTO_COMO_USAR.split("\n\n"):
            primeira, _, resto = bloco.partition("\n")
            if resto:
                texto.insert("end", primeira + "\n", "titulo")
                texto.insert("end", resto + "\n")
            else:
                texto.insert("end", "\n" + primeira + "\n")
        texto.config(state="disabled")
        janela.bind("<Escape>", lambda _e: janela.destroy())

    def abrir_registros(self) -> None:
        try:
            PASTA_LOGS.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(PASTA_LOGS)  # noqa: S606 (abre o Explorer na pasta)
            else:
                webbrowser.open(PASTA_LOGS.resolve().as_uri())
        except OSError as e:
            log.warning("Não foi possível abrir a pasta de registros: %s", e)
            self.rotulo_erro.config(text=f"Não foi possível abrir a pasta de registros ({PASTA_LOGS}).")

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
        if self.thread_motor is not None and self.thread_motor.is_alive():
            # ainda terminando a sessão anterior (Parar leva até ~1 s pra o motor sair do laço)
            self.rotulo_erro.config(text="Aguarde um instante: a sessão anterior ainda está sendo finalizada.")
            return
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

        try:
            self.registro = Registro(PASTA_LOGS)
        except OSError as e:
            log.warning("Não foi possível criar o histórico em %s: %s", PASTA_LOGS, e)
            self.rotulo_erro.config(text="Não foi possível criar o arquivo de histórico. Confira o espaço em "
                                         "disco e a permissão da pasta de registros.")
            return
        self.fila = queue.Queue()
        self.erros_motor = queue.Queue()
        self.monitor = Monitor(parametros, construir_ao_avaliar(self.registro, self.fila),
                               resolver_pares(pares))
        self.thread_motor = threading.Thread(target=executar_motor, args=(self.monitor, self.erros_motor),
                                             daemon=True)
        self.sessao_ativa = True
        self.inicio_sessao = time.monotonic()
        self.avaliacoes = self.sinais = 0
        self.ultima_avaliacao = None
        self._ultimas = {}
        self.thread_motor.start()

        self._habilitar_campos(False)
        self._recolher_regra(True)
        self._estilizar_botoes(rodando=True)
        self.indicador.definir("conectando", "Conectando…")
        self._atualizar_status("conectando")

    def parar(self) -> None:
        self.sessao_ativa = False
        if self.monitor:
            self.monitor.parar.set()
        if self.registro:
            self.registro.fechar()  # seguro mesmo com o motor gravando: Registro tem lock (7497ac8)
            self.registro = None
        self._estilizar_botoes(rodando=False)
        self._habilitar_campos(True)
        self._recolher_regra(False)
        self.indicador.definir("parado", "Parado")
        self.rotulo_rodape.config(text=self._texto_rodape_parado())
        self.rotulo_status.config(text="Monitoramento parado", fg=TEXTO)
        self.rotulo_orientacao.config(text="Nenhum aviso novo será mostrado. Clique em Iniciar para retomar.")
        self.rotulo_proxima.config(text="Avaliações às :00, :15, :30 e :45.")
        self.barra_espera.parado()

    def _recolher_regra(self, recolher: bool) -> None:
        if self.lado_a_lado:
            return
        if recolher:
            p = self.config.parametros
            num = lambda v: f"{v:g}".replace(".", ",")  # noqa: E731
            self.rotulo_regra_resumida.config(
                text=f"Regra: RSI(2) até {num(p.rsi_abaixo)} ou a partir de {num(p.rsi_acima)} · setores "
                     f"{num(p.setor_pct)}% · alvo {num(p.ajuste_pct)}% — pare o monitoramento para editar.")
            self.frame_regra.pack_forget()
            self.rotulo_regra_resumida.pack(fill="x", pady=(self.tema.px(10), 0), before=self.frame_acoes)
        else:
            self.rotulo_regra_resumida.pack_forget()
            self.frame_regra.pack(fill="x", pady=(self.tema.px(12), 0), before=self.frame_acoes)

    def _fim_inesperado(self) -> None:
        """O motor morreu sem o usuário clicar em Parar: devolve a janela ao estado "pode iniciar",
        com a explicação no bloco de status e a mensagem de erro (se houver) embaixo."""
        self.sessao_ativa = False
        if self.registro:
            self.registro.fechar()
            self.registro = None
        self._estilizar_botoes(rodando=False)
        self._habilitar_campos(True)
        self._recolher_regra(False)
        self.indicador.definir("encerrado", "Encerrado")
        self._atualizar_status("encerrado")
        self.rotulo_proxima.config(text="Avaliações às :00, :15, :30 e :45.")
        self.rotulo_rodape.config(text=self._texto_rodape_parado())
        self.barra_espera.parado()

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
        try:
            self._acompanhar_tamanho()
            self._processar()
        except tk.TclError:  # janela sendo destruída no meio do laço
            return
        except Exception:  # um erro de exibição nunca pode parar o laço (e com ele os avisos)
            log.exception("Erro ao atualizar a janela")
        self._laco = self.root.after(200, self._verificar_fila)

    def _processar(self) -> None:
        while not self.fila.empty():
            av = self.fila.get_nowait()
            if not self.sessao_ativa:
                continue  # chegou depois do Parar: não mostra aviso de uma sessão já encerrada
            self.painel.atualizar(av)
            self._ultimas[av.simbolo] = av
            self.avaliacoes += 1
            self.sinais += av.sinal is not None
            try:
                self.ultima_avaliacao = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000).strftime("%H:%M")
            except (OverflowError, OSError, ValueError):
                pass
            if av.sinal and (av.latencia_ms or 0) < ATRASO_MAX_POPUP_MS:
                self.popups.mostrar(av)
        while not self.erros_motor.empty():
            self.rotulo_erro.config(text=self.erros_motor.get_nowait())

        if not self.sessao_ativa or self.monitor is None:
            return
        motor_vivo = bool(self.thread_motor and self.thread_motor.is_alive())
        if not motor_vivo:
            self._fim_inesperado()
            return
        chave, texto = estado_do_monitor(True, True, self.monitor.conectado.is_set(), self.monitor.reconexoes)
        self.indicador.definir(chave, texto)
        self._atualizar_status(chave)

    # ───────────────────────────── tela cheia ─────────────────────────────

    def _medir_base(self) -> None:
        self.root.update_idletasks()
        self._tamanho_base = (self.conteudo.winfo_reqwidth(), self.conteudo.winfo_reqheight())

    def _esta_maximizada(self) -> bool:
        try:
            if self.root.state() == "zoomed":  # Windows (e macOS)
                return True
        except tk.TclError:
            pass
        for atributo in ("-zoomed", "-fullscreen"):  # X11 não tem o estado "zoomed"
            try:
                if int(self.root.attributes(atributo)):
                    return True
            except (tk.TclError, ValueError):
                pass
        return False

    def alternar_tela_cheia(self) -> None:
        """Link "Tela cheia" e tecla F11: maximiza (ou volta ao normal). O zoom em si é aplicado
        por _acompanhar_tamanho, que também pega o botão maximizar da própria janela."""
        maximizar = not self._esta_maximizada()
        try:
            self.root.state("zoomed" if maximizar else "normal")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", maximizar)
            except tk.TclError:
                self.root.attributes("-fullscreen", maximizar)

    def _acompanhar_tamanho(self) -> None:
        maximizada = self._esta_maximizada()
        if maximizada and self.zoom == 1.0 and self._tamanho_base:
            self.root.update_idletasks()
            disponivel = (self.root.winfo_width(), self.root.winfo_height())
            z = zoom_para(self._tamanho_base, disponivel)
            if z >= 1.08:  # ganho pequeno demais não compensa refazer a janela
                self.aplicar_zoom(z)
        elif not maximizada and self.zoom != 1.0:
            self.aplicar_zoom(1.0)

    def aplicar_zoom(self, zoom: float) -> None:
        """Refaz a janela inteira no novo zoom, preservando o que o usuário vê e digitou: campos
        (mesmo a meio de uma edição), lista de pares, mensagens, estado da sessão e a última
        avaliação de cada par. O motor, a fila e o CSV não são tocados — só a parte visual."""
        textos = {campo: entrada.get() for campo, entrada in self.entradas.items()}
        pares = self.entrada_pares.get("1.0", "end-1c")
        rotulos = {nome: (getattr(self, nome).cget("text"), getattr(self, nome).cget("fg"))
                   for nome in ("rotulo_erro", "rotulo_status", "rotulo_orientacao", "rotulo_proxima",
                                "rotulo_resumo", "rotulo_rodape")}
        indicador = (self.indicador.chave, self.indicador.rotulo.cget("text"))

        self.barra_espera.parado()
        self.conteudo.destroy()
        self.entradas = {}
        self.zoom = zoom
        self._montar(self.root, reconstruindo=True)

        for campo, texto in textos.items():
            self.entradas[campo].delete(0, "end")
            self.entradas[campo].insert(0, texto)
        self.entrada_pares.delete("1.0", "end")
        self.entrada_pares.insert("1.0", pares)
        for nome, (texto, cor) in rotulos.items():
            getattr(self, nome).config(text=texto, fg=cor)
        self.indicador.definir(*indicador)
        self.diagrama.atualizar(self._parametros_desenho.setor_pct)
        self.painel.definir_faixas(self._parametros_desenho.rsi_abaixo, self._parametros_desenho.rsi_acima)
        for av in self._ultimas.values():
            self.painel.atualizar(av)
        if self.sessao_ativa:
            self._habilitar_campos(False)
            self._recolher_regra(True)
            self._estilizar_botoes(rodando=True)
            self._atualizar_barra(indicador[0])

    def _atualizar_status(self, chave: str) -> None:
        demorando = time.monotonic() - self.inicio_sessao > SEGUNDOS_CONEXAO_DEMORADA
        reconexoes = self.monitor.reconexoes if self.monitor else 0
        titulo, orientacao = mensagens_de_status(chave, len(self.config.pares), self.ultima_avaliacao,
                                                 demorando, reconexoes)
        cor = {"conectado": CIANO, "encerrado": VERMELHO, "conectando": OURO, "reconectando": OURO}.get(chave, TEXTO)
        if chave == "conectando" and not demorando:
            cor = TEXTO
        self.rotulo_status.config(text=titulo, fg=cor)
        self.rotulo_orientacao.config(text=orientacao)
        if self.sessao_ativa:
            self.rotulo_resumo.config(text=f"Nesta sessão: {self.avaliacoes} avaliações · {self.sinais} sinais")
        agora = datetime.now()
        if chave == "conectado":
            proxima = proxima_avaliacao(agora)
            texto = f"Próxima avaliação às {proxima:%H:%M} · em {contagem_regressiva(agora, proxima)}"
            self.rotulo_proxima.config(text=texto)
            self.rotulo_rodape.config(text=f"Próxima avaliação às {proxima:%H:%M}.")
        elif chave in ("conectando", "reconectando"):
            self.rotulo_proxima.config(text="Previsão da próxima avaliação: assim que conectar.")
        self._atualizar_barra(chave)

    def _atualizar_barra(self, chave: str | None = None) -> None:
        """Conectando/reconectando: animação (a não ser com "Reduzir movimento"). Conectado: barra
        enche até o próximo fechamento de 15 min — o tempo, não a chance de sinal."""
        if chave is None:
            chave = self.indicador.chave
        if not self.sessao_ativa:
            self.barra_espera.parado()
        elif chave == "conectado":
            self.barra_espera.progresso(fracao_do_intervalo(datetime.now()))
        elif self.reduzir_movimento.get():
            self.barra_espera.parado()
        else:
            self.barra_espera.animar()

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
        if self._laco is not None:
            try:
                self.root.after_cancel(self._laco)
            except tk.TclError:
                pass
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
