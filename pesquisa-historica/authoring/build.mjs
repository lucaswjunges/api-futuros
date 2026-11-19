import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const data=JSON.parse(await fs.readFile(path.join(root,'resultados/consolidado.json'),'utf8'));
if(data.results.length!==64 || Object.keys(data.errors).length || data.missing_symbols.length) throw Error('Coleta incompleta');
const bySymbol=new Map(data.results.map(x=>[x.symbol,x]));
const wb=Workbook.create();
const summary=wb.worksheets.add('Índice');
const methodology=wb.worksheets.add('Como ler');
const output=path.join(root,'outputs/entrega-roberto');await fs.mkdir(output,{recursive:true});
const previews=path.join(root,'previews'); await fs.mkdir(previews,{recursive:true});
function style(sh,lastRow,lastCol=5){
 sh.showGridLines=false; const r=sh.getRangeByIndexes(0,0,lastRow,lastCol);
 r.format.font={name:'Arial',size:10,color:'#172338'};r.format.rowHeight=18;r.format.verticalAlignment='center';
 sh.getRange('A1:A'+lastRow).format.columnWidth=15;
 sh.getRange('B1:B'+lastRow).format.columnWidth=12;
 sh.getRange('C1:E'+lastRow).format.columnWidth=21;
}
function header(sh,r,values){let a=sh.getRangeByIndexes(r-1,0,1,values.length);a.values=[values];a.format={fill:'#172338',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:25,horizontalAlignment:'center',verticalAlignment:'center'};}
const timestamp=ms=>25569+(ms-10800000)/86400000;
const cutoffLabel=new Date(data.cutoff_ms-10800000).toISOString().slice(0,16).replace('T',' ');
const title=(sh,t)=>{sh.getRange('A2').values=[[t]];sh.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:'#172338'};};
style(summary,72,6);title(summary,'Pesquisa Histórica — Alerta Futuros');
summary.getRange('A3').values=[['64 ativos · 8 níveis · 50 ocorrências por tabela']];
summary.getRange('A4').values=[['Horários de abertura das velas, em Brasília (UTC-3).']];
header(summary,6,['Ativo','Tabelas','Ocorrências','Primeiro registro','Último registro','Situação']);
const summaryRows=[];
for(const sym of data.symbols){
 const d=bySymbol.get(sym);if(d.gaps.length)throw Error('Lacunas '+sym);
 const sh=wb.worksheets.add(sym);style(sh,463);title(sh,sym+' — RSI-2 em 5 minutos');
 sh.getRange('A3').values=[['50 fechamentos por nível, em sequência temporal. Horários UTC-3.']];
 const all=[];
 for(let l=1;l<=8;l++){
  const rows=d.groups[String(l)];if(rows.length!==50)throw Error('Faltam linhas '+sym+' '+l);
  const start=6+(l-1)*57;const up=l<=5;
  sh.getRange('A'+start).values=[['Nível '+l+' — '+({1:'99 a 100',2:'98 a <99',3:'97 a <98',4:'96 a <97',5:'95 a <96',6:'2 a 3',7:'1 a <2',8:'0 a <1'}[l])+' de RSI']];
  sh.getRange('A'+start+':E'+start).format.fill='#FFF3D0';sh.getRange('A'+start).format.font={name:'Arial',size:10,bold:true};
  header(sh,start+1,['Data','Hora',up?'% Elevação':'% Queda','Quant. velas',up?'% Queda':'% Elevação']);
  const matrix=rows.map(x=>[timestamp(x.open_ms),timestamp(x.open_ms),x.first,x.count,x.second]);
  sh.getRangeByIndexes(start+1,0,50,5).values=matrix;
  sh.getRange('A'+(start+2)+':A'+(start+51)).setNumberFormat('dd/mm/yyyy');
  sh.getRange('B'+(start+2)+':B'+(start+51)).setNumberFormat('hh:mm');
  sh.getRange('C'+(start+2)+':C'+(start+51)).setNumberFormat('0.0000%');
  sh.getRange('D'+(start+2)+':D'+(start+51)).setNumberFormat('0');
  sh.getRange('E'+(start+2)+':E'+(start+51)).setNumberFormat('0.0000%');
  sh.getRangeByIndexes(start+1,0,50,5).format.horizontalAlignment='right';
  for(let k=0;k<50;k+=2)sh.getRangeByIndexes(start+1+k,0,1,5).format.fill='#F3F5F8';
  all.push(...rows.map(x=>x.open_ms));
 }
 sh.freezePanes.freezeRows(3);
 summaryRows.push([sym,8,400,timestamp(Math.min(...all)),timestamp(Math.max(...all)),'Completo']);
}
summary.getRange('A7:F70').values=summaryRows;summary.getRange('D7:E70').setNumberFormat('dd/mm/yyyy hh:mm');
summary.getRange('A7:A70').format.columnWidth=22;summary.getRange('B7:C70').format.columnWidth=15;summary.getRange('D7:E70').format.columnWidth=25;summary.getRange('F7:F70').format.columnWidth=15;
summary.freezePanes.freezeRows(6);
style(methodology,35,2);methodology.getRange('A1:A35').format.columnWidth=30;methodology.getRange('B1:B35').format.columnWidth=110;title(methodology,'Como ler as tabelas');
const notes=[
 ['Fonte','Candles de 5 minutos da Binance Futuros USDⓈ-M: https://fapi.binance.com/fapi/v1/klines'],
 ['Roteiro','Futuros - Pesquisa Histórica.docx, encaminhado em 05/11/2026.'],
 ['Coleta','Somente velas fechadas antes de '+cutoffLabel+' (UTC-3).'],
 ['Organização','Uma aba por ativo, com oito tabelas de 50 ocorrências. Total: 512 tabelas e 25.600 registros.'],
 ['Data e hora','Abertura da vela de origem da ocorrência, no horário de Brasília (UTC-3).'],
 ['Seleção','As últimas 50 ocorrências completas de cada nível, em ordem crescente, sem pular fechamentos elegíveis.'],
 ['Ocorrência','Cada fechamento de 5 minutos cujo RSI-2 pertence à faixa gera uma ocorrência, inclusive fechamentos consecutivos na mesma faixa.'],
 ['RSI-2','Método de Wilder sobre os fechamentos. São reservadas 300 velas anteriores para aquecimento do cálculo.'],
 ['Faixas','Classificação com precisão completa: 98 a 98,99 é interpretado como 98 ≤ RSI < 99, e assim para faixas vizinhas.'],
 ['Nível 6','RSI de 2 até 3, inclusive. Valores acima de 3 e abaixo de 95 não geram ocorrência.'],
 ['Primeiro trecho','Começa na vela de origem e segue a direção inicial: elevação nos níveis 1–5 e queda nos níveis 6–8.'],
 ['Empates','RSI igual ao anterior não muda a direção.'],
 ['Primeiro extremo','Desconsidera a vela de origem. Sem continuação do primeiro trecho, usa o extremo da segunda vela e quantidade zero.'],
 ['Segundo trecho','Começa na primeira reversão e termina antes da reversão seguinte. Só entram ocorrências com os dois trechos completos.'],
 ['Quantidade de velas','Conta as velas do primeiro trecho, sem a vela de origem.'],
 ['Elevação','Máxima do trecho / fechamento da vela de origem − 1.'],
 ['Queda','Fechamento da vela de origem / mínima do trecho − 1.'],
 ['Percentuais','Valores calculados sem arredondamento intermediário, exibidos com quatro casas decimais. Valores negativos são preservados.'],
 ['Exemplo ETH do roteiro','O exemplo com RSI 95,3 está escrito como Nível 1; foi usada a tabela de faixas, que o classifica no Nível 5.'],
 ['Janelas','O período necessário varia entre ativos e níveis; o roteiro permite janelas a qualquer tempo.'],
 ['Uso','Selecione a aba do ativo e role até o nível desejado. As tabelas são estáticas e não atualizam automaticamente.']
];
methodology.getRangeByIndexes(4,0,notes.length,2).values=notes;methodology.getRange('A5:A25').format.font={name:'Arial',size:10,bold:true};
methodology.getRange('B5:B25').format.wrapText=true;methodology.getRange('A5:B25').format.rowHeight=35;
wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:'BTCUSDT',range:'A6:E11',maxChars:1800,tableMaxRows:6,tableMaxCols:5})).ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(output,'Pesquisa-Historica-Roberto-Urbano.xlsx'));
if (process.argv.includes('--previews')) {
for(const sym of ['Índice','Como ler','BTCUSDT','ETHUSDT','1000PEPEUSDT']) {
 const range=sym==='Como ler'?'A2:B25':sym==='Índice'?'A2:F16':'A2:E13';
 const b=await wb.render({sheetName:sym,range,scale:1,format:'png'});
 await fs.writeFile(path.join(previews,sym+'.png'),new Uint8Array(await b.arrayBuffer()));
}
}
console.log('EXPORTADO',output);
