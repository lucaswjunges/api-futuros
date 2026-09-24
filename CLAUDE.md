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
pip install -r requirements.txt                 # websockets (motor) + pystray/Pillow (ícone de bandeja da janela)
python -m unittest -v                           # todos os testes
python -m unittest test_alerta_futuros.TestRSI.test_periodo_2_calculado_a_mao   # um teste
python alerta_futuros.py --sem-popup --minutos 15   # execução ao vivo só console + CSV (logs/)
python alerta_futuros.py --demo                 # pop-ups de exemplo, sem rede (útil p/ screenshots)
python janela.py                                # janela de configuração (Opção B) — CSV em logs/, ícone na bandeja
python janela.py --minimizado                   # mesma janela, já minimizada na bandeja (usado pelo início automático)
python queda_simulada_ao_vivo.py                # E2E: derruba a conexão na virada da vela e confere a recuperação (2–7 min)
xvfb-run -s "-screen 0 1366x768x24" python smoke_janela.py --pares 16   # smoke visual: layout/rolagem numa tela dada

# Empacotamento (.exe) — só no Windows, ver "Empacotar o .exe" no poc/README.md
pip install -r requirements-dev.txt
pyinstaller --onefile --windowed --name AlertaFuturos --icon assets\icone_bandeja.ico --add-data "assets;assets" janela.py

cd proposta
pdflatex -interaction=nonstopmode proposta-alerta-futuros.tex   # rodar 2x (LastPage/refs)
```

## Arquitetura da PoC (`poc/alerta_futuros.py`)

Fluxo: REST aquece o estado → WebSocket entrega velas → RSI(2) atualiza a **cada** vela 5m fechada → captação (avaliação completa + pop-up + CSV) só nos fechamentos que também fecham uma vela de 15m (:00/:15/:30/:45).

- **Lógica pura** (testada em `test_alerta_futuros.py`): `RSIWilder` (RSI incremental com suavização de Wilder/RMA, igual ao TradingView), `faixa_rsi` (Condição 1), `setor_vela15` (Condição 2), `cruzamento` (X/Y → alvo W/Z), `formatar_preco` (padrão BR, casas decimais por par em `PARES`), `fecha_vela_15m(abertura_ms)` (item 4.5-b).
- **`Ativo`**: estado por par. A vela de 15m **não** vem do stream de 15m: é reconstruída agregando as velas 5m fechadas da mesma janela (`abertura // MS_15M`). Isso é idêntico à vela da Binance e evita corrida entre mensagens 5m/15m. `classificar()` detecta duplicatas e lacunas. `Ativo.fechar_vela()` sempre atualiza o RSI(2) e a agregação da vela 15m, independentemente de captarmos aquele fechamento ou não.
- **`Monitor`** (thread própria com `asyncio`): conecta o WebSocket **antes** de baixar o histórico REST (mensagens ficam na fila, nenhuma vela se perde); reconexão com backoff exponencial até 30 s; watchdog derruba a conexão após 30 s sem mensagens; lacuna → recarrega histórico via REST com `endTime`. Só processa klines `5m` com `x: true`.
- **Captação a cada 15m (item 4.5-b, confirmado com o cliente em 19/09/2026)**: em `Monitor._recuperar` e `Monitor._vela_fechada`, todo fechamento de vela 5m chama `ativo.fechar_vela()` (RSI sempre atualizado), mas só chama `self.ao_avaliar(av)` (o que dispara CSV/pop-up/painel de status) quando `fecha_vela_15m(abertura_ms)` é verdadeiro. Antes disso, a captação era a cada 5m; o cliente pediu 15m porque uma vela de 15m "em formação" (ainda não fechada) dá resultado móvel/instável. `queda_simulada_ao_vivo.py` avança o alvo (`virada`) até um fechamento que também feche uma vela de 15m, senão o teste reportaria FALHOU mesmo com a recuperação certa.
- **`Monitor._recuperar`** é o ponto único de carga REST (conexão inicial, reconexão e lacuna): se o par já tinha estado, as velas que fecharam durante a queda são **avaliadas** (`recuperada=True`, sujeitas à mesma regra dos 15m acima), não só absorvidas no histórico — bug achado na execução ao vivo de 16/09/2026. Sinais recuperados com mais de 5 min de atraso (`ATRASO_MAX_POPUP_MS`) vão só para o CSV, sem pop-up.
- **UI**: Tkinter na thread principal; o motor publica sinais numa `queue.Queue` consumida por `root.after`. `Popups` é uma janela própria (não toast nativo) porque o toast do Windows não permite cor do texto nem duração exata de 10 s. Com a captação a cada 15m, o painel de status da janela agora atualiza cada linha a cada 15 min (não mais a cada 5).
- **`poc/janela.py`**: CSV (`Registro`) é gravado igual ao CLI — cada "Iniciar" abre um arquivo novo em `poc/logs/`, "Parar"/fechar de vez fecha o arquivo (ver `construir_ao_avaliar()`, testado em `test_janela.py` sem precisar de `tk.Tk()` real). **Bug corrigido em 19/09/2026**: antes disso, `Monitor` recebia `self.fila.put` direto como `ao_avaliar`, sem nunca passar por um `Registro` — quem rodasse pela janela (o fluxo principal da Opção B) não gerava CSV nenhum, apesar da proposta prometer "Registro CSV de fechamentos e sinais". Achado numa auditoria de escopo, não por teste automático (é exatamente por isso que agora tem teste).
- **`poc/bandeja.py`**: ícone de bandeja (`pystray` + `Pillow`), item da proposta "Roda em segundo plano, com ícone perto do relógio: Iniciar, Parar e Sair". Fechar a janela (X) minimiza pra bandeja em vez de encerrar; "Sair" só pelo menu da bandeja (ou Ctrl+C no console). Callbacks do menu rodam na thread do pystray — nunca tocam widget direto, só agendam via `root.after(0, ...)`, mesma regra do `Monitor`. Se a criação do `pystray.Icon` falhar (ex.: Linux sem GTK/appindicator/xorg, como este sandbox de nuvem), `Aplicativo._configurar_bandeja` cai no comportamento antigo (fechar = encerrar de vez) e loga um aviso — nunca finge que a bandeja está funcionando.
  - **Achado em 19/09/2026 (teste ao vivo do Hugo no Windows)**: a criação do ícone pode dar certo (sem nenhum aviso no log) e mesmo assim nenhum ícone aparecer de verdade na bandeja — porque o `.run()` que efetivamente desenha o ícone roda numa thread separada e pode falhar *depois*, sem levantar nada no código que criou a bandeja. `bandeja._executar()` agora embrulha o `.run()` num try/except que avisa `janela.Aplicativo` de volta se a thread morrer, e `janela._verificar_bandeja_subiu()` confere 300ms depois de iniciar se ela já não nasceu morta — os dois casos caem em `Aplicativo._bandeja_falhou_em_tempo_de_execucao()`, que desfaz o "fechar minimiza" e volta pro "fechar encerra". Testado em `test_bandeja.py` (pulado neste sandbox porque `import pystray` já falha aqui sem GTK/xorg configurado — no Windows real, que é a plataforma de destino, isso não acontece, pystray escolhe o backend win32 direto).
  - **Resolvido em 19/09/2026 (mesmo dia, análise de vídeo do Hugo)**: a bandeja sempre esteve funcionando — o ícone fica na área de ícones ocultos do Windows (o "^" ao lado do relógio), e o placeholder genérico (círculo escuro + linha verde) era pequeno e sem cara de "Alerta Futuros" o bastante pra ser notado no meio de Bluetooth/Teams/OneDrive. Não era bug, só um ícone fácil de não perceber.
  - **Ícone (19/09/2026)**: trocado o placeholder pela logo oficial da Blumenau TI — `poc/assets/icone_bandeja.png`, baixada de `blumenauti.com.br/favico2.png` (fundo azul-marinho `#1a1a2e`, "B" branco e barra de gráfico ascendente, a mesma paleta do site). `bandeja.carregar_icone()` carrega esse arquivo por padrão e só cai em `icone_padrao()` (o círculo verde antigo) se o arquivo não existir por algum motivo — nunca quebra o app por causa de um ícone faltando. `poc/assets/icone_bandeja.ico` (multi-resolução, mesma logo) existe só pra ser o ícone do `.exe`/da barra de tarefas — quem lê o ícone da bandeja em tempo de execução continua sendo o `.png`.
- **`--minimizado`**: flag de `janela.py` que já sobe minimizado na bandeja; `inicio_automatico.comando_de_inicializacao()` sempre inclui essa flag no valor gravado no Registro do Windows, pra quem ligou "iniciar com o Windows" não ver a janela de configuração aparecer sozinha no login.
- **Rodapé "Conhecer outras versões" (19/09/2026)**: pedido do Hugo/Lucas — link no rodapé da janela de configuração (`janela.py`, `_montar_rodape()`) apontando pra uma futura página de aquisição das Opções A/B e da versão com IA, pra já ir acessível a partir da versão que vai pro cliente agora como MVP mesmo a página em si ainda não existindo. A URL fica em `URL_OUTRAS_VERSOES` (marcada com `TODO`, hoje só um placeholder — `https://www.blumenauti.com.br/` — até o Hugo passar o link definitivo) e o clique é tratado por `abrir_outras_versoes()` (função separada do bind só pra dar pra testar sem `tk.Tk()`, ver `test_janela.py`). Também documentado no material do cliente (`poc/GUIA-INSTALACAO-CLIENTE.md`), por pedido explícito do Hugo de que o link apareça tanto no app quanto no material de instalação.
  - **Bug pego no build de teste do PyInstaller, corrigido no mesmo dia**: a primeira versão criava o `Frame` do rodapé com `pady=(0, 10)` — tupla assimétrica, que só é válida no gerenciador de geometria (`.pack`/`.grid`), não no construtor do widget. `tk.Frame(..., pady=(0, 10))` levanta `_tkinter.TclError: bad screen distance "0 10"` assim que a janela de verdade é montada. Escapou dos testes automatizados porque nenhum deles chega a montar um `tk.Tk()` real (só testam lógica pura, ver docstring de `test_janela.py`) — só apareceu rodando o `.exe`/script de verdade. Corrigido movendo o `pady=(0, 10)` do construtor do `Frame` pro `.pack()`.
- **Visual (redesenho de 22/09/2026, branch `feature/janela-configuracao`)**: `poc/tema.py` (paleta, fontes, DPI, `retangulo_arredondado`) e `poc/componentes.py` (`Indicador`, `DiagramaVela15`, `PainelPares` + funções puras testadas em `test_componentes.py`). Decisões: azul-marinho + dourado da marca (ícone da bandeja e capa da proposta) — dourado é o único destaque de interface (botão principal, foco); verde `#0ECB81`/vermelho `#F6465D` são as cores de vela da Binance e ficam **reservados aos sinais** (marcador do RSI na faixa, coluna Sinal, linha tingida, pop-up) — por isso os botões Iniciar/Parar deixaram de ser verde/vermelho. Números em **Bahnschrift** (DIN, vem no Windows 10/11) e texto em Segoe UI, com fallback em `Helvetica` fora do Windows (`Tema` resolve por `tkfont.families`). A regra aparece como frases com os números como lacunas; o diagrama da vela e a régua de RSI do quadro se redesenham a cada tecla (`_ao_editar`). Quadro de situação é um `Canvas` (não mais `ttk.Treeview`): eixo 0–100 por par, faixas Abaixo/Acima tingidas, marcador colorido só quando a faixa é verdadeira, coluna **Sinal** com o último W/Z. `CampoInvalido.campo` permite destacar o campo errado em vermelho. **DPI**: `tema.preparar_dpi()` (SetProcessDpiAwareness) roda antes do `tk.Tk()` em `janela.main()` e no `--demo`; toda medida em pixel passa por `Tema.px()` — **ainda não testado num Windows a 125%/150%** (o sandbox é Linux); se algo sair desproporcional, é a primeira coisa a desligar. Pop-up: cantos arredondados via `-transparentcolor` (só Windows; fora dele fica retângulo), barra que esvazia nos 10 s, sem eyebrow em caixa alta. Capturas antes/depois em `poc/evidencias/visual/` (feitas no Xvfb a 100 dpi com fonte reserva — no Windows fica um pouco mais compacto). `proposta/popups-poc.png` continua sendo a captura antiga: a proposta já foi enviada, não foi regenerada.

- **Pares acompanhados: até 16, escolhidos pelo cliente (23/09/2026)**. Antes eram 8 fixos em
  `PARES`. Agora `LIMITE_PARES = 16`, a lista mora em `Configuracao.pares` (salva no `config.json`,
  campo "Pares acompanhados" na janela) e `Monitor` recebe o dicionário já resolvido por
  `resolver_pares()`. **Casas decimais**: `PARES` continua mandando nos 8 originais (é a tabela que
  o cliente montou olhando o gráfico) e os pares novos saem do `tickSize` do `/fapi/v1/exchangeInfo`
  — **não** do `pricePrecision`, que daria 4 casas no SOLUSDT e 6 no DOGEUSDT. A consulta é aquecida
  numa thread ao abrir a janela (`_aquecer_casas_decimais`) e memorizada no processo, senão o clique
  em "Iniciar" esperaria alguns MB de download. `pares_desconhecidos()` recusa no "Iniciar" símbolo
  que a Binance não lista (erro de digitação, ou par que saiu de linha — o MATICUSDT, que aparecia
  nos exemplos, é exatamente esse caso: sem a checagem ele virava uma linha com RSI 100 fixo); sem
  internet a checagem é pulada em vez de travar o app.
- **Layout da janela com 16 pares**: `LARGURA_MIN_LADO_A_LADO = 1280` — em tela larga a janela vira
  duas colunas (regra à esquerda, quadro à direita, ~1150×550 px, tudo à vista sem rolar); em tela
  estreita volta ao empilhado e o quadro ganha rolagem. `altura_maxima_do_quadro()` (janela.py) +
  `altura_visivel_das_linhas()` (componentes.py) garantem que a janela **nunca** passe da tela — o
  risco real era o quadro de 16 linhas empurrar os botões Iniciar/Parar para fora da borda de baixo.
  Por isso `PainelPares` virou um `tk.Frame` com **dois** Canvas (cabeçalho parado + corpo que rola):
  rolando um Canvas único, a régua do RSI subiria junto e o cliente perderia a legenda do eixo.
  Capturas: `poc/evidencias/visual/16-pares-lado-a-lado.png` e `16-pares-empilhado-rolagem.png`.

## Regra de negócio e decisões já tomadas

- Condição 1: RSI(2) ≥ 90 → ACIMA; ≤ 5 → ABAIXO (limites inclusivos).
- Condição 2: vela 15m válida se `(máx − mín) / mín > 0,020%`; setor A = 30% superior, C = 30% inferior, B = meio.
- X = ACIMA + A → W = fechamento × 1,005 (verde); Y = ABAIXO + C → Z = fechamento × 0,995 (vermelho).
- Nos fechamentos de :00/:15/:30/:45 usa-se a vela 15m que termina junto com a 5m.
- **Item 4.5-b (confirmado com o cliente em 19/09/2026)**: a captação (avaliação completa, CSV, pop-up) só acontece nos fechamentos de vela 5m que também fecham uma vela de 15m (:00/:15/:30/:45) — nas demais o RSI(2) é atualizado normalmente, mas não há avaliação/CSV/pop-up. Motivo dado pelo cliente: uma vela de 15m "em formação" (fechamento de 5m que não coincide com :00/:15/:30/:45) ainda não é definitiva, e usar esses fechamentos intermediários dava resultados mais instáveis. Implementado em `fecha_vela_15m()`.
- Aquecimento de 300 velas 5m (o documento do cliente pede só 2, mas o RSI divergiria do gráfico).
- Feature de IA/análise de notícias sugerida pelo cliente (grupo de 19/09/2026): tratada como fora do escopo da Opção B atual, para uma segunda entrega — não implementar aqui.
- Itens pendentes de confirmação com o cliente estão na seção 4.5 da proposta.

## Pegadinhas da Binance

- **Streams de kline de Futuros só funcionam na rota `/market`**: `wss://fstream.binance.com/market/stream?streams=...`. Desde 23/04/2026 as URLs antigas (`/ws`, `/stream`) conectam, mas **não entregam velas** e não dão erro.
- REST: `https://fapi.binance.com/fapi/v1/klines` (descartar a última vela se `closeTime` ainda estiver no futuro) e `/fapi/v1/time` para o offset de relógio.
- Latência do fechamento ao alerta (execução de 60 min, 88 fechamentos): mediana 637 ms, p95 3,2 s — os lentos quase sempre no LTCUSDT (menos negociado). A maior parte é a Binance publicando a vela fechada (campo `E` − fechamento, gravado no CSV como `publicacao_binance_ms`) + ~250 ms de rede até o Japão; o cálculo é < 1 ms.

## Proposta (`proposta/`)

- Valores comerciais e os resultados da PoC ficam em macros no topo do `.tex` (`\cliente`, `\autor`, `\valPoc`, `\valA`, `\valB`, `\pocAval`, `\pocLatMed`…) — altere ali, não no corpo.
- `popups-poc.png` é captura real dos pop-ups (`--demo`), obtida com `xwd -id <wm_frame>` porque a sessão é Wayland.
- Depois de editar, renderizar (`pdftoppm -r 70 -png`) e conferir visualmente: a proposta deve caber em 8 páginas (capa + 7).
