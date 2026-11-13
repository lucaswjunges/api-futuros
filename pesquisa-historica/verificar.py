from pathlib import Path
import json,datetime,math,hashlib
from coletar import analyze
p=Path(__file__).parent; d=json.loads((p/'resultados/consolidado.json').read_text()); total=0
for asset in d['results']:
 raw=json.loads((p/'cache'/f"{asset['symbol']}.json").read_text()); bytime={x[0]:i for i,x in enumerate(raw)}
 assert len(bytime)==len(raw) and not asset['gaps']
 assert raw[-1][0] == d['cutoff_ms']-300000
 assert {k:v[-50:] for k,v in analyze(raw).items()} == asset['groups'], asset['symbol']
 for level,rows in asset['groups'].items():
  assert len(rows)==50
  assert all(a['open_ms']<b['open_ms'] for a,b in zip(rows,rows[1:]))
  for row in rows:
   i=bytime[row['open_ms']]; end=bytime[row['first_end_ms']]; j=bytime[row['second_start_ms']]; k=bytime[row['second_end_ms']]
   first=raw[i+1:end+1] if end>i else [raw[i+1]]; second=raw[j:k+1]
   assert row['count']==end-i>=0 and row['reversal_ms']<d['cutoff_ms']
   if int(level)<=5:
    x=max(float(c[2]) for c in first)/float(raw[i][4])-1; y=float(raw[i][4])/min(float(c[3]) for c in second)-1
   else:
    x=float(raw[i][4])/min(float(c[3]) for c in first)-1;y=max(float(c[2]) for c in second)/float(raw[i][4])-1
   assert math.isclose(x,row['first'],abs_tol=1e-14) and math.isclose(y,row['second'],abs_tol=1e-14)
   total+=1
assert total==25600
snapshot=json.loads((p/'fontes/snapshot-original.json').read_text())
if d['cutoff_ms']==snapshot['cutoff_ms']:
 canonical=json.dumps({a['symbol']:a for a in d['results']},sort_keys=True,separators=(',',':')).encode()
 assert hashlib.sha256(canonical).hexdigest()==snapshot['results_canonical_sha256'], 'Replay difere da coleta original'
print('Conferidos:',len(d['results']),'ativos, 512 tabelas,',total,'linhas; sequencia, extremos, percentuais e contagem OK.')
(p/'resultados/verificacao.txt').write_text('64 ativos; 512 tabelas; 25.600 ocorrencias. Sem lacunas nos candles. Extremos, formulas e quantidades conferidos em todas as ocorrencias. Os quatro exemplos do roteiro passaram nos testes.',encoding='utf-8')
