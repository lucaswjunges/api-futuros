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
python -m unittest -v                  # testes da lógica
```

Cada fechamento avaliado é gravado em `logs/fechamentos_*.csv` (RSI, setor, sinal, alvo,
latência) para conferência com o gráfico da Binance.

## Endpoints

- REST: `https://fapi.binance.com/fapi/v1/klines` (histórico 5m para aquecer o RSI)
- WebSocket: `wss://fstream.binance.com/market/stream?streams=<par>@kline_5m/<par>@kline_15m`

Desde 23/04/2026 a Binance só entrega streams de kline na rota `/market`; as URLs antigas
(`/ws`, `/stream`) conectam mas não enviam velas.
