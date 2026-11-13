# Pesquisa Histórica

Entrega: apenas XLSX e instrução HTML, sem aplicativo adicional. Fonte de escopo:
`fontes/Futuros - Pesquisa Histórica.docx`: 64 ativos, 8 níveis, 50 ocorrências,
512 tabelas e 25.600 registros.

## Reprodução original sem rede

Na raiz de um clone limpo, com Python e dependências do app instaladas:

```powershell
python pesquisa-historica/reproduzir.py
python pesquisa-historica/coletar.py --replay-cutoff 1794580800000
python pesquisa-historica/verificar.py
python -m unittest discover -s pesquisa-historica -v
```

Corte original: 13/11/2026 11:40 Brasília (14:40 UTC). O snapshot deliberadamente
versionado `fontes/candles-original.zip` contém os 64 históricos necessários,
com SHA-256 do arquivo e de cada histórico em `snapshot-original.json`.
Permite auditar e reproduzir mesmo se a API mudar. O restaurador recusa substituir
cache divergente; use outro clone para preservá-lo. O replay filtra velas posteriores,
exige cobertura até a última vela fechada, recalcula RSI e seleção e falha se faltar
qualquer nível. Não acessa a rede.

Para nova coleta: `python pesquisa-historica/coletar.py`. Atualiza a cauda do cache
até o corte da Binance antes de analisar se há 50 ocorrências. Falta de cobertura,
lacunas, duplicatas ou níveis incompletos causam erro. Preserve resultados anteriores
em outra pasta antes de nova coleta.

## Exportação do zero

Um único gerador (`authoring/build.mjs`) lê `resultados/consolidado.json`.
Não importa XLSX. Datas e horas entram como seriais numéricos do Excel em UTC-3,
formatados como `dd/mm/yyyy` e `hh:mm`. O alias `build-original.mjs` usa esse gerador.

Requer Node e `@oai/artifact-tool` do runtime de artefatos do Codex
(bundle validado: 26.1105.12137). Localize com `load_workspace_dependencies`.
Ligue `authoring/node_modules` ao diretório de pacotes retornado e defina
`ARTIFACT_NODE` com o executável Node retornado. Não versione a ligação.

```powershell
python pesquisa-historica/exportar.py --previews
```

Gera planilha, instrução e ZIP em `outputs/entrega-roberto/` e reabre o OOXML
exportado para conferir datas/horas, números e ausência de erros em todas as
25.600 linhas. `verificar.py` confere extremos, contagens e fórmulas contra as
velas brutas. Seis testes do roteiro cobrem quatro exemplos, limites e ocorrência
incompleta; cinco testes adicionais cobrem cache.

Arquivos por ativo em `resultados/` são intermediários locais. Só o consolidado e
relatório de verificação são versionados. Caches, previews, XLSX e ZIP de entrega
ficam locais; fontes e snapshot de auditoria ficam no Git.
