# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este repositório

Projeto de cliente da **Blumenau TI** para **Roberto Urbano** (uso hobby, sem experiência técnica — textos voltados ao cliente em linguagem simples): app de alertas de trading para Windows que lê **somente dados públicos** da Binance Futuros USDⓈ-M (sem conta, API key ou ordens) e mostra um pop-up quando a regra do cliente é verdadeira. A especificação original do cliente está em `APP-Futuros.docx` — é a fonte de verdade da regra de negócio.

- `poc/` — Prova de Conceito em Python (motor + pop-up), base da futura Versão 1.
- `poc/evidencias/` — log e CSV de uma execução ao vivo; os números citados na proposta saem daqui.
- `proposta/` — proposta técnico-comercial em LaTeX (padrão das propostas Blumenau TI) + PDF compilado.

## Comandos

```bash
cd poc
pip install -r requirements.txt                 # única dependência: websockets
python -m unittest -v                           # todos os testes
python -m unittest test_alerta_futuros.TestRSI.test_periodo_2_calculado_a_mao   # um teste
python alerta_futuros.py --sem-popup --minutos 15   # execução ao vivo só console + CSV (logs/)
python alerta_futuros.py --demo                 # pop-ups de exemplo, sem rede (útil p/ screenshots)
python queda_simulada_ao_vivo.py                # E2E: derruba a conexão na virada da vela e confere a recuperação (2–7 min)

cd proposta
pdflatex -interaction=nonstopmode proposta-alerta-futuros.tex   # rodar 2x (LastPage/refs)
```

## Arquitetura da PoC (`poc/alerta_futuros.py`)

Fluxo: REST aquece o estado → WebSocket entrega velas → avaliação a cada vela 5m fechada → pop-up + CSV.

- **Lógica pura** (testada em `test_alerta_futuros.py`): `RSIWilder` (RSI incremental com suavização de Wilder/RMA, igual ao TradingView), `faixa_rsi` (Condição 1), `setor_vela15` (Condição 2), `cruzamento` (X/Y → alvo W/Z), `formatar_preco` (padrão BR, casas decimais por par em `PARES`).
- **`Ativo`**: estado por par. A vela de 15m **não** vem do stream de 15m: é reconstruída agregando as velas 5m fechadas da mesma janela (`abertura // MS_15M`). Isso é idêntico à vela da Binance e evita corrida entre mensagens 5m/15m. `classificar()` detecta duplicatas e lacunas.
- **`Monitor`** (thread própria com `asyncio`): conecta o WebSocket **antes** de baixar o histórico REST (mensagens ficam na fila, nenhuma vela se perde); reconexão com backoff exponencial até 30 s; watchdog derruba a conexão após 30 s sem mensagens; lacuna → recarrega histórico via REST com `endTime`. Só processa klines `5m` com `x: true`.
- **`Monitor._recuperar`** é o ponto único de carga REST (conexão inicial, reconexão e lacuna): se o par já tinha estado, as velas que fecharam durante a queda são **avaliadas** (`recuperada=True`), não só absorvidas no histórico — bug achado na execução ao vivo de 16/09/2026. Sinais recuperados com mais de 5 min de atraso (`ATRASO_MAX_POPUP_MS`) vão só para o CSV, sem pop-up.
- **UI**: Tkinter na thread principal; o motor publica sinais numa `queue.Queue` consumida por `root.after`. `Popups` é uma janela própria (não toast nativo) porque o toast do Windows não permite cor do texto nem duração exata de 10 s.

## Regra de negócio e decisões já tomadas

- Condição 1: RSI(2) ≥ 90 → ACIMA; ≤ 5 → ABAIXO (limites inclusivos).
- Condição 2: vela 15m válida se `(máx − mín) / mín > 0,020%`; setor A = 30% superior, C = 30% inferior, B = meio.
- X = ACIMA + A → W = fechamento × 1,005 (verde); Y = ABAIXO + C → Z = fechamento × 0,995 (vermelho).
- Nos fechamentos de :00/:15/:30/:45 usa-se a vela 15m que termina junto com a 5m.
- Aquecimento de 300 velas 5m (o documento do cliente pede só 2, mas o RSI divergiria do gráfico).
- Itens pendentes de confirmação com o cliente estão na seção 4.5 da proposta.

## Pegadinhas da Binance

- **Streams de kline de Futuros só funcionam na rota `/market`**: `wss://fstream.binance.com/market/stream?streams=...`. Desde 23/04/2026 as URLs antigas (`/ws`, `/stream`) conectam, mas **não entregam velas** e não dão erro.
- REST: `https://fapi.binance.com/fapi/v1/klines` (descartar a última vela se `closeTime` ainda estiver no futuro) e `/fapi/v1/time` para o offset de relógio.
- Latência do fechamento ao alerta (execução de 60 min, 88 fechamentos): mediana 637 ms, p95 3,2 s — os lentos quase sempre no LTCUSDT (menos negociado). A maior parte é a Binance publicando a vela fechada (campo `E` − fechamento, gravado no CSV como `publicacao_binance_ms`) + ~250 ms de rede até o Japão; o cálculo é < 1 ms.

## Proposta (`proposta/`)

- Valores comerciais e os resultados da PoC ficam em macros no topo do `.tex` (`\cliente`, `\autor`, `\valPoc`, `\valA`, `\valB`, `\pocAval`, `\pocLatMed`…) — altere ali, não no corpo.
- `popups-poc.png` é captura real dos pop-ups (`--demo`), obtida com `xwd -id <wm_frame>` porque a sessão é Wayland.
- Depois de editar, renderizar (`pdftoppm -r 70 -png`) e conferir visualmente: a proposta deve caber em 8 páginas (capa + 7).
