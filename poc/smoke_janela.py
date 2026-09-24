"""Smoke test visual da janela: abre com uma lista de pares qualquer, preenche o quadro com
avaliações de exemplo e fecha sozinha. Serve pra conferir num Xvfb (ou num Windows de verdade)
que o quadro cabe na tela, que o cabeçalho fica parado e que a rolagem aparece só quando precisa
— coisas que os testes automáticos não pegam, porque nenhum deles monta um tk.Tk() real.

  xvfb-run -s "-screen 0 1366x768x24" python smoke_janela.py --pares 16
  xvfb-run -s "-screen 0 1920x1080x24" python smoke_janela.py --pares 8 --segundos 3
"""

from __future__ import annotations

import argparse
import json
import tempfile
import tkinter as tk
from pathlib import Path

from alerta_futuros import MS_5M, Avaliacao, Parametros, cruzamento, formatar_preco
from janela import Aplicativo
from tema import preparar_dpi

# 16 pares plausíveis (os 8 do cliente + 8 das maiores altcoins de Futuros) só pra ter o que
# desenhar; a lista de verdade quem manda é o cliente.
EXEMPLO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "LTCUSDT", "DOGEUSDT",
           "ADAUSDT", "AVAXUSDT", "TRXUSDT", "DOTUSDT", "POLUSDT", "NEARUSDT", "ATOMUSDT", "UNIUSDT"]
PRECOS = [76718.8, 2505.19, 101.93, 721.82, 1.3688, 11.534, 650.39, 0.08506,
          0.4312, 18.77, 0.2914, 3.512, 0.2277, 2.884, 3.917, 6.442]


def avaliacoes(pares: list[str]) -> list[Avaliacao]:
    p = Parametros()
    abertura = 1_758_000_000_000 // MS_5M * MS_5M
    saida = []
    for i, simbolo in enumerate(pares):
        fech = PRECOS[i % len(PRECOS)]
        if i % 3 == 0:
            faixa, setor, rsi = "ACIMA", "A", 94.7
        elif i % 3 == 1:
            faixa, setor, rsi = "ABAIXO", "C", 3.2
        else:
            faixa, setor, rsi = None, "B", 46.1
        cruz = cruzamento(faixa, setor, fech, p)
        sinal, alvo = cruz if cruz else (None, None)
        saida.append(Avaliacao(simbolo, abertura, fech, rsi, faixa, fech * 1.01, fech * 0.99, 0.9,
                               setor, sinal, alvo,
                               formatar_preco(alvo, 2) if alvo else "", formatar_preco(fech, 2)))
    return saida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pares", type=int, default=16)
    ap.add_argument("--segundos", type=float, default=2.0)
    ap.add_argument("--salvar-em", type=Path, default=None, help="só imprime a geometria e sai")
    args = ap.parse_args()

    pares = EXEMPLO[:args.pares]
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "config.json"
        caminho.write_text(json.dumps({"parametros": {}, "iniciar_com_windows": False, "pares": pares}),
                           encoding="utf-8")
        preparar_dpi()
        root = tk.Tk()
        app = Aplicativo(root, caminho)
        for av in avaliacoes(pares):
            app.painel.atualizar(av)
        root.update_idletasks()
        print(f"pares={len(pares)} janela={root.winfo_reqwidth()}x{root.winfo_reqheight()} "
              f"tela={root.winfo_screenwidth()}x{root.winfo_screenheight()} "
              f"quadro_rola={app.painel.rolagem} quadro_natural={app.painel.altura_natural}")
        root.after(int(args.segundos * 1000), root.destroy)
        root.mainloop()


if __name__ == "__main__":
    main()
