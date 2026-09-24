"""
Tema visual do app — cores, fontes e escala de DPI compartilhadas por janela.py e pelos pop-ups.
=================================================================================================

De onde vêm as escolhas (redesenho de 22/09/2026):

- Azul-marinho + dourado é a identidade da Blumenau TI que o cliente já conhece: o ícone da bandeja
  (fundo #021F50) e a capa da proposta (navy #0B1426, dourado #FFB700). O dourado é o ÚNICO
  destaque de interface (botão principal, foco dos campos, estado "conectando"). Verde e vermelho
  ficam reservados para o que o documento do cliente define como verde/vermelho: os sinais W e Z.
- Verde #0ECB81 e vermelho #F6465D são as cores de vela da própria Binance — o alerta fica com a
  mesma cor que o cliente vê no gráfico que ele acompanha.
- Números em Bahnschrift (fonte DIN que já vem no Windows 10/11): o conteúdo deste app são
  números, então é a fonte deles que dá a cara de instrumento. Textos em Segoe UI, a fonte do
  próprio Windows. Fora do Windows (este sandbox, o Ubuntu do Lucas) nenhuma das duas existe, e o
  Tk cai num fallback que renderiza blocos ilegíveis (achado em 20/09/2026) — por isso a lista de
  famílias termina em 'Helvetica', alias que o Tk resolve pra alguma sans-serif em qualquer
  plataforma. No Windows de verdade (plataforma de destino) nada disso muda o que aparece.
- Escala de DPI: o Windows moderno usa 125%/150% em quase todo notebook. Sem avisar que o
  processo entende DPI, o Windows estica o bitmap da janela inteira (borrado). preparar_dpi() faz
  esse aviso ANTES de criar o tk.Tk(); depois disso as fontes (em pontos) crescem sozinhas e toda
  medida em pixel do nosso desenho passa por Tema.px(), que multiplica pela escala real. Fora do
  Windows a escala fica 1,0 e nada muda.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("alerta.tema")

# ───────────────────────────── paleta ─────────────────────────────

FUNDO = "#0F1B2E"          # azul-marinho da marca, fundo da janela
PAINEL = "#142440"         # superfície do quadro de situação e do pop-up
CAMPO = "#1B2F52"          # fundo dos campos de texto
BORDA = "#2A4472"          # contorno de campos, botão secundário e pop-up
LINHA = "#1C2E4E"          # separadores discretos
TRILHO = "#22375C"         # trilho do eixo de RSI (parte "neutra" da escala)

TEXTO = "#ECF1FA"
TEXTO_FRACO = "#8FA6CC"    # rótulos e informação secundária (contraste 7:1 sobre FUNDO)
TEXTO_APAGADO = "#5C7096"  # placeholders, estado "parado", valores ainda não recebidos

OURO = "#FFB700"           # o único destaque de interface
OURO_ATIVO = "#E5A400"     # botão dourado pressionado
OURO_TEXTO = "#0F1B2E"     # texto sobre dourado
CIANO = "#36C5F0"          # "Conectado" — online sem parecer sinal de compra

VERDE = "#0ECB81"          # sinal X / alvo W (verde de vela da Binance)
VERMELHO = "#F6465D"       # sinal Y / alvo Z (vermelho de vela da Binance)
VERDE_FAIXA = "#0F4743"    # faixa "Acima" no eixo (verde misturado com o fundo)
VERMELHO_FAIXA = "#49263A" # faixa "Abaixo" no eixo
VERDE_LINHA = "#10333A"    # fundo da linha do par quando o último fechamento deu sinal X
VERMELHO_LINHA = "#32213A" # idem para sinal Y

CAMINHO_ICONE = Path(__file__).with_name("assets") / "icone_bandeja.png"

# Ordem de preferência; o último item de cada lista é um alias que o Tk sempre resolve.
FAMILIAS_TEXTO = ("Segoe UI", "Helvetica")
FAMILIAS_NUMEROS = ("Bahnschrift", "Segoe UI Semibold", "Segoe UI", "Helvetica")


def preparar_dpi() -> None:
    """Avisa o Windows que o processo entende DPI (chamar ANTES de tk.Tk()). Fora do Windows não
    faz nada. Se a chamada falhar (Windows antigo, ou DPI já definido por manifesto do .exe), o
    app continua como sempre foi: o Windows estica o bitmap da janela."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 1 = system DPI aware
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as e:  # nunca impede o app de abrir por causa disso
            log.debug("Não foi possível declarar DPI awareness: %s", e)


def primeira_familia_disponivel(preferidas: tuple[str, ...], disponiveis) -> str:
    """Primeira família da lista que existe no sistema; se nenhuma existir, devolve a última da
    lista (um alias como 'Helvetica', que o Tk sempre resolve pra alguma fonte)."""
    disponiveis = set(disponiveis)
    for familia in preferidas:
        if familia in disponiveis:
            return familia
    return preferidas[-1]


class Tema:
    """Fontes resolvidas e escala de pixels de UMA instância de tk.Tk (cada root tem as suas)."""

    def __init__(self, root):
        from tkinter import font as tkfont

        familias = tkfont.families(root)
        self.familia_texto = primeira_familia_disponivel(FAMILIAS_TEXTO, familias)
        self.familia_numeros = primeira_familia_disponivel(FAMILIAS_NUMEROS, familias)
        self.escala = escala_de(root.winfo_fpixels("1i"))
        # Ampliação da janela maximizada (pedido do cliente em 23/09/2026: "usar a tela toda", num
        # notebook dedicado ao app). 1,0 = tamanho normal; a janela aumenta tudo junto — medidas
        # e fontes — em vez de só esticar o fundo e deixar o conteúdo pequeno num canto.
        self.zoom = 1.0

    def px(self, n: float) -> int:
        """Medida em 'pixels de projeto' (96 dpi) -> pixels reais desta tela (já com o zoom)."""
        return int(round(n * self.escala * self.zoom))

    def _tamanho(self, tamanho: int) -> int:
        return max(1, int(round(tamanho * self.zoom)))

    def texto(self, tamanho: int = 10, peso: str = "normal") -> tuple[str, int, str]:
        return (self.familia_texto, self._tamanho(tamanho), peso)

    def numeros(self, tamanho: int = 11, peso: str = "normal") -> tuple[str, int, str]:
        return (self.familia_numeros, self._tamanho(tamanho), peso)


def escala_de(pixels_por_polegada: float) -> float:
    """96 dpi -> 1,0 · 120 dpi (125%) -> 1,25 · 144 dpi (150%) -> 1,5. Valores absurdos (Xvfb sem
    DPI, tela virtual) caem em 1,0 em vez de sumir com a janela."""
    escala = pixels_por_polegada / 96.0
    if not (0.5 <= escala <= 4.0):
        return 1.0
    return escala


def retangulo_arredondado(canvas, x1: float, y1: float, x2: float, y2: float, raio: float, **opcoes):
    """Retângulo de cantos arredondados num Canvas (polígono suavizado). O Tk 8.6 não tem cantos
    arredondados nativos, e é isso que dá ao pop-up a cara de janela do Windows 11."""
    r = max(0, min(raio, (x2 - x1) / 2, (y2 - y1) / 2))
    pontos = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pontos, smooth=True, **opcoes)
