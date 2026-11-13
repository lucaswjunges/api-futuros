# Relatório de preparação da entrega a Roberto Urbano

Verificação em 13/11/2026, horário de Brasília. **Entrega comercial ainda pendente;
1.2 não publicada, main não alterada e nenhuma mensagem enviada ao cliente.**

## Código e integração

Base conferida: `fa95442`, branch `feature/v1.2`. Commits desta preparação:
`ddbc914` (fontes, pesquisa, snapshot, exportação e spec) e `8dd739e` (ambiente
fixado, CI e manifesto dos artefatos) e `43a3a4b` (replay por hash canônico).
PR de rascunho:
https://github.com/lucaswjunges/api-futuros/pull/4

Simulação local `git merge-tree --write-tree HEAD origin/main` sem conflitos;
GitHub também informou `MERGEABLE`. O PR permanece rascunho e não foi integrado.
O CI Windows usa Python 3.14.7, dependências fixadas em `poc/requirements-build.txt`
e o `poc/AlertaFuturos.spec` agora versionado, como o procedimento do README.

CI do commit `43a3a4b` **aprovado**: testes do app, empacotamento Windows, testes
da pesquisa, replay offline com conferência e upload do executável como artefato.
Execução: https://github.com/lucaswjunges/api-futuros/actions/runs/43453604434
O CI emitiu aviso de depreciação do runtime Node 20 das actions usadas; o runner
executou-as com Node 24 e todos os passos passaram. Atualizar essas actions pode
ser tratado em manutenção posterior.

## Escopo conferido

App: testes confirmam avaliação em todos os fechamentos de 5 minutos, sem a espera
de 15 minutos, e aviso desligado por padrão. Configuração da 1.1 recebe esses padrões
ao migrar, preservando os demais valores. As opções antigas continuam selecionáveis.
Não houve alteração de regra nesta preparação.

Após a preparação, o usuário forneceu a transcrição do WhatsApp de Roberto ao
Business de sexta-feira, 06/11/2026, 06:53: “orçar uma Versão 1.2 do App,
bloqueando a 'Vela de 15 Minutos' (deixando tudo só 5M) e bloqueando o 'Alerta de
10 Segundos', deixando o restante da mesma forma em que está”. A fonte original
foi identificada por essa transcrição; o WhatsApp não foi consultado diretamente.

Decisão posterior do responsável pela entrega, em 13/11/2026: manter as opções
selecionáveis, com os padrões de 5 minutos e aviso desligado. A orientação foi
“as opções selecionáveis parece a melhor opção” e dar a Roberto essa possibilidade,
condicionada à avaliação técnica. A recomendação técnica é manter a implementação:
o funcionamento inicial atende a 5M sem espera de 15M e sem aviso automático, e
o retorno ao comportamento anterior exige escolha explícita. Essa decisão resolve
a pendência interna de escopo e preserva a implementação e os pacotes existentes.

O WhatsApp original, literalmente, pedia bloqueio; a decisão posterior de manter
as opções é do responsável pela entrega. Não é confirmação de que Roberto já
aceitou essa alternativa. Não houve alteração de código nem novo build nesta
etapa documental. Os testes já aprovados cobrem padrões, migração e persistência
das opções selecionadas; não foram repetidos por não haver alteração executável.

Pesquisa: documento DOCX lido integralmente e e-mail encaminhado de 05/11 conferido:
somente tabelas para leitura, sem app adicional. A planilha tem 66 abas (índice,
instruções e 64 ativos), 512 tabelas e 25.600 registros. O roteiro permite janela
histórica a qualquer tempo. No exemplo ETH, o RSI 95,3 corresponde ao nível 5;
o rótulo nível 1 do exemplo é inconsistente com a tabela de faixas e foi documentado.

## Validações realizadas

- 210 testes do app aprovados nesta máquina e novamente em clone limpo com venv
  separado: incluem padrões 1.2, opções 15m, migração/configuração, fatores por par,
  download validado, substituição, falha de troca e conservação da versão anterior.
- 11 testes da pesquisa aprovados nos dois ambientes: seis do roteiro e cinco
  de cache (atualização, falta de cobertura, replay offline, corte e lacunas).
- Snapshot original restaurado com conferência de SHA-256 e replay offline dos
  64 ativos: corte `1794580800000`, 13/11/2026 11:40 Brasília, última vela 11:35.
  Nenhuma lacuna. Resultado integral por ativo igual ao original, inclusive seleção
  das últimas 50 ocorrências completas de cada nível. Hash canônico registrado.
- Recalculados RSI, seleção, extremos, fórmulas e contagens de todas as 25.600
  ocorrências a partir das velas brutas.
- XLSX gerado diretamente do JSON sem importação de planilha preexistente.
  Datas e horas são seriais numéricos UTC-3 desde a primeira escrita.
  OOXML salvo reaberto e todas as 25.600 linhas conferidas, incluindo tipos,
  percentuais, contagens e horários (tolerância de 2 ms na conversão Excel).
  O comando único `exportar.py` também passou em clone limpo, sem XLSX inicial.
- Prévia visual examinada: índice, instruções e BTC; geradas também ETH e PEPE.
- Três ZIPs reabertos sem falha de CRC; todos os componentes do pacote completo
  conferidos por tamanho e SHA-256 contra `manifesto-entrega.json`.
- Build PyInstaller concluído em clone limpo e venv separado, Windows/Python 3.14.7.
  EXE de prova: `build-entrega-v1.2/clone-validacao/poc/dist/AlertaFuturos.exe`,
  22.711.988 bytes, SHA-256 `cf0cfa4f1cb560c135f3c657f2e852b123830af743dc5d459b715018e1cb0334`.
  É prova do procedimento; não substitui automaticamente o EXE de entrega já preparado.
  A nova cópia não foi inspecionada visualmente nesta sessão.

## Arquivos locais de entrega

- `entrega-v1.2/Entrega-Alerta-Futuros-Roberto-apos-aceite.zip`: pacote completo.
- `entrega-v1.2/AlertaFuturos-1.2-entrega.zip`: app, guia e manifesto.
- `pesquisa-historica/outputs/entrega-roberto/Pesquisa-Historica-Roberto-Urbano.zip`:
  planilha e instrução; nenhum aplicativo de pesquisa.
- `entrega-v1.2/manifesto-entrega.json`: tamanhos e SHA-256 de cada componente.
- EXE de entrega: 22.712.089 bytes, SHA-256
  `79b6ba46c670bbabc2bff2767ae587fc974a6e6d411a194db0ae32741b751149`.
  Manifesto: versão 1.2, build 2026.11.10.1, plano completa.

Binários e pacotes continuam locais, ignorados pelo Git. Fontes, testes, documentação,
consolidado e snapshot deliberado de auditoria estão versionados. Nenhum cache de
trabalho, node_modules, build, preview ou arquivo temporário foi adicionado.
O snapshot comprimido tem 16.509.065 bytes; não é o diretório de cache mutável.
Os arquivos existentes foram preservados. `authoring/build-original.mjs` é um alias
para o único gerador. Scripts não publicam nem sobrescrevem páginas do site.

## Produção e pendências de publicação

Consultados `/versao.json`, `/assets/AlertaFuturos.exe` e página inicial, com HTTP 200.
Produção permanece na **1.1, build 2026.10.07.3**. EXE baixado e validado contra o
manifesto: 21.647.990 bytes, SHA-256
`ccbffab4c5d5c3e52d909e92121ad9a3336ab604e141bcf020d1be0c28cb8be2`.
Cópias locais em `entrega-v1.2/evidencias-locais/`. Acesso urllib recebeu 403;
curl com User-Agent de navegador conseguiu baixar e a integridade foi conferida.

O usuário informou o projeto Cloudflare Pages **`alerta-futuros-versoes`**, na conta
do **Lucas**, a mesma de `blumenauti.com.br`. Essa identificação foi recebida, mas
a associação ao domínio ainda não foi verificada diretamente no painel/API.
Não há token Cloudflare disponível no ambiente consultado. A ferramenta de interface
interrompeu o acesso por não conseguir determinar a URL do navegador com segurança.
O DNS consultado não expôs CNAME que permita identificar o projeto. Antes de qualquer
deploy, conferir o domínio personalizado no projeto informado e guardar deployment
e site completo anteriores; a página inicial baixada não substitui backup completo.

Faltam confirmação do aceite e do Pix, verificação do projeto Pages informado
e backup integral. O comportamento das opções foi definido pelo responsável pela
entrega. Após a liberação comercial e a revisão: integrar o PR,
incorporar EXE e JSON ao site completo, baixar de produção e validar hashes/tamanhos,
testar atualização **real** 1.1 → 1.2, configurações e recuperação da versão anterior.
Os testes automatizados não comprovam esse percurso em produção. O roteiro operacional
está em `LEIA-ANTES-DE-PUBLICAR.md`.

Condição comercial preservada: **R$ 720,00 no aceite**, Pix no CNPJ
**53.700.754/0001-10**, entrega em até **dois dias úteis após o Pix**.
Nenhuma confirmação comercial foi presumida e nenhuma publicação foi executada.

O retorno encaminhado informa que o aditivo e a planilha foram recebidos e que a
conferência de conteúdo contra o DOCX será feita. Isso não comprova o aceite final
nem o recebimento do Pix. A frase “a publicação ... eu faço quando você liberar”
também não constitui liberação para publicar; permanece a condição comercial.
