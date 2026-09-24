# Alerta Futuros — Guia de instalação

Este guia é para quem só vai **usar** o app (não precisa saber programar).

## 1. Baixar o programa

Você vai receber um único arquivo: **`AlertaFuturos.exe`**.

Salve-o em qualquer pasta do seu computador (por exemplo, na Área de Trabalho ou em
"Documentos"). Não precisa instalar nada além disso — é um programa único, pronto pra usar.

## 2. Abrir pela primeira vez

Dê dois cliques em `AlertaFuturos.exe`.

O Windows pode mostrar um aviso do tipo **"O Windows protegeu o computador"** (SmartScreen).
Isso acontece porque o programa não tem um certificado de assinatura digital paga — não é
sinal de vírus. Para continuar:

1. Clique em **"Mais informações"**
2. Clique em **"Executar assim mesmo"**

Isso só aparece na primeira vez que você abre o programa nesse computador.

## 3. A janela de configuração

Ao abrir, aparece a janela com os campos de configuração (RSI, tamanho dos setores etc.) já
preenchidos com os valores combinados. Normalmente você só precisa:

1. Marcar a caixa **"Iniciar com o Windows"**, se quiser que o programa já suba sozinho
   quando você ligar o computador (ele sobe minimizado, sem abrir a janela sozinho)
2. Clicar em **"Iniciar"**

A partir daí o programa fica rodando e mostra um pop-up no canto da tela sempre que a regra
combinada acontecer.

## 3.1. Trocar os pares acompanhados (até 16)

No campo **"Pares acompanhados"** você escolhe quais moedas o programa vigia — **até 16**.
Escreva o símbolo do jeito que ele aparece na Binance (quase sempre termina em `USDT`, por
exemplo `BTCUSDT`), separando por espaço ou vírgula. Pode colar a lista inteira de uma vez.

Depois de mexer nessa lista, clique em **"Iniciar"**: é nesse momento que a mudança passa a
valer e o quadro de baixo se refaz com as moedas novas. A lista fica salva, então da próxima
vez que você abrir o programa ela já vem do jeito que você deixou — **não é preciso pedir um
programa novo pra trocar de moeda**.

Se você digitar um símbolo que a Binance não tem (um erro de digitação, ou uma moeda que saiu
de linha), o programa avisa na hora, com o nome do símbolo, em vez de ficar com uma linha
parada no quadro sem explicação.

## 4. Ícone perto do relógio (bandeja)

Ao fechar a janela (o X), o programa **não** encerra — ele continua rodando escondido, com um
ícone perto do relógio do Windows (canto inferior direito da tela).

Esse ícone às vezes fica escondido na "área de ícones ocultos": clique na setinha **"^"** ao
lado do relógio pra ver os ícones que não aparecem direto na barra. Procure a logo da
Blumenau TI (fundo azul-escuro com um "B" branco).

Clicando com o botão direito nesse ícone você tem as opções **Abrir**, **Iniciar
Monitoramento**, **Parar Monitoramento** e **Sair** (só "Sair" encerra o programa de vez).

## 5. Registro de sinais (CSV)

Toda vez que o programa avalia um fechamento, ele grava uma linha num arquivo de planilha
(CSV) numa pasta `logs`, ao lado do programa — pra você conferir depois no Excel, se quiser.

## 6. Conhecer outras versões

Dentro da janela de configuração, no rodapé, tem um link **"Conhecer outras versões"**.
Clicando nele, abre no seu navegador a página com as outras opções disponíveis (Opção A, Opção
B completa, e a versão com análise por IA) — é a mesma página que a Blumenau TI vai te enviar
separadamente com todos os detalhes.

## Dúvidas

Qualquer dúvida na instalação, fale com a Blumenau TI pelo mesmo canal do orçamento.
