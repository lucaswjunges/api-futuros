# PoC — Alerta Futuros (Binance USDⓈ-M)

Prova de conceito do app de alertas: lê **somente dados públicos** da Binance Futuros
(sem conta, sem API key, sem ordens), avalia a regra do cliente a cada fechamento de
vela de 5 minutos e mostra um pop-up por 10 s quando há cruzamento verdadeiro.

## Regra implementada

| Etapa | Regra |
|---|---|
| Condição 1 | RSI(2) de Wilder no fechamento da vela 5m: `≥ 90` → **Acima** · `≤ 5` → **Abaixo** |
| Condição 2 | Vela 15m em andamento: tamanho = Máx − Mín, válida se `(Máx − Mín) / Mín > 0,020%`. Setor **A** = 30% superior, **C** = 30% inferior, **B** = meio |
| Cruzamento | **X** = Acima + A · **Y** = Abaixo + C |
| Preço-alvo | **W** = fechamento × 1,005 (verde) · **Z** = fechamento × 0,995 (vermelho) |

## Executar

Requer Python 3.10+.

```bash
pip install -r requirements.txt
python alerta_futuros.py               # monitora os 8 pares com pop-ups
python alerta_futuros.py --sem-popup   # só console + CSV
python alerta_futuros.py --demo        # pop-ups de exemplo, sem internet
python alerta_futuros.py --minutos 30  # encerra sozinho após 30 min
python janela.py                       # janela de configuração (Opção B) + quadro de situação
python -m unittest -v                  # testes da lógica
```

Cada fechamento avaliado é gravado em `logs/fechamentos_*.csv` (RSI, setor, sinal, alvo,
latência) para conferência com o gráfico da Binance.

## Visual (janela e pop-ups)

Cores, fontes e escala de DPI ficam em `tema.py`; as partes desenhadas (eixo de RSI por par,
diagrama da vela de 15m, indicador de estado) em `componentes.py`. Paleta: azul-marinho e
dourado da Blumenau TI (mesmos do ícone e da proposta), com o verde/vermelho de vela da própria
Binance reservados aos sinais W/Z. Números em Bahnschrift e textos em Segoe UI — as duas só
existem no Windows, então capturas feitas no Linux (como as de `evidencias/visual/`) saem com a
fonte reserva e um pouco mais largas do que o cliente vai ver. Os cantos arredondados do pop-up
também só aparecem no Windows (`-transparentcolor`).

Capturas de antes/depois do redesenho de 22/09/2026: `evidencias/visual/`.

## Endpoints

- REST: `https://fapi.binance.com/fapi/v1/klines` (histórico 5m para aquecer o RSI)
- WebSocket: `wss://fstream.binance.com/market/stream?streams=<par>@kline_5m/<par>@kline_15m`

Desde 23/04/2026 a Binance só entrega streams de kline na rota `/market`; as URLs antigas
(`/ws`, `/stream`) conectam mas não enviam velas.

## Empacotar o .exe (PyInstaller)

Só precisa disso quem vai **gerar** o executável pra entregar ao cliente — quem só roda o
app a partir do código-fonte (`python janela.py`) não precisa. Tem que rodar **no Windows**
(um `.exe` gerado no Linux não roda lá — o sandbox de nuvem só faz um build de sanidade em
Linux, pra pegar bug de empacotamento cedo, mas o `.exe` de verdade sai só daqui).

```powershell
pip install -r requirements-dev.txt
pyinstaller --onefile --windowed --name AlertaFuturos --icon assets\icone_bandeja.ico --add-data "assets;assets" janela.py
```

O `.exe` final fica em `dist\AlertaFuturos.exe`. Notas:

- `--windowed` evita que um console preto abra atrás da janela.
- `--icon` usa `assets/icone_bandeja.ico` (a logo da Blumenau TI) como ícone do `.exe` e da
  barra de tarefas — sem isso o Windows mostra o ícone genérico do Python.
- `--add-data "assets;assets"` (no Windows o separador é `;`, não `:`) embute a pasta
  `assets/` dentro do `.exe`, senão `bandeja.carregar_icone()` não encontra a logo em tempo
  de execução e cai no ícone de reserva (círculo escuro + linha verde).
- Depois de gerado, teste o `.exe` (não só o script) pelo menos uma vez antes de entregar —
  foi um build de teste como esse que pegou o bug do rodapé em 19/09/2026 (ver `CLAUDE.md`).
- Ver `GUIA-INSTALACAO-CLIENTE.md` pro texto simples que acompanha o `.exe` na entrega.
