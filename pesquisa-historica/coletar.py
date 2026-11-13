from pathlib import Path
import sys,json,urllib.request,urllib.parse,time,threading,concurrent.futures,datetime,math,zipfile,xml.etree.ElementTree as ET,re,argparse,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'poc'))
from alerta_futuros import RSIWilder
MS=300000
lock=threading.Lock(); next_request=0

def request(path,params=None):
 global next_request
 url='https://fapi.binance.com'+path+('?' + urllib.parse.urlencode(params) if params else '')
 for attempt in range(5):
  with lock:
   delay=max(0,next_request-time.monotonic()); next_request=max(next_request,time.monotonic())+0.32
  if delay: time.sleep(delay)
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BlumenauTI-PesquisaHistorica/1.0'}),timeout=30) as r:
    return json.load(r)
  except Exception:
   if attempt==4: raise
   time.sleep(2**attempt)

def level(x):
 if x is None:return None
 if 99<=x<=100:return 1
 if 98<=x<99:return 2
 if 97<=x<98:return 3
 if 96<=x<97:return 4
 if 95<=x<96:return 5
 if 2<=x<=3:return 6
 if 1<=x<2:return 7
 if 0<=x<1:return 8
 return None

def event(candles,rsi,i,upper):
 direction=1 if upper else -1
 j=i+1
 while j<len(rsi) and direction*(rsi[j]-rsi[j-1])>=0:j+=1
 if j>=len(rsi):return None
 first_end=j-1
 k=j+1
 while k<len(rsi) and direction*(rsi[k]-rsi[k-1])<=0:k+=1
 if k>=len(rsi):return None
 first=candles[i+1:first_end+1] if first_end>i else [candles[i+1]]
 second=candles[j:k]
 base=float(candles[i][4])
 if upper:
  a=max(float(c[2]) for c in first); b=min(float(c[3]) for c in second)
  one=a/base-1; two=base/b-1
 else:
  a=min(float(c[3]) for c in first); b=max(float(c[2]) for c in second)
  one=base/a-1; two=b/base-1
 return {'open_ms':candles[i][0],'rsi':rsi[i],'first':one,'count':first_end-i,'second':two,'base':base,'extreme1':a,'extreme2':b,'first_end_ms':candles[first_end][0],'second_start_ms':candles[j][0],'second_end_ms':candles[k-1][0],'reversal_ms':candles[k][0]}

def analyze(candles):
 calc=RSIWilder(2); r=[calc.atualizar(float(c[4])) for c in candles]
 groups={str(k):[] for k in range(1,9)}
 # 300 velas de aquecimento, conforme a implementacao ja validada do app.
 for i in range(300,len(candles)-2):
  l=level(r[i])
  if l:
   e=event(candles,r,i,l<=5)
   if e is not None: groups[str(l)].append(e)
 return groups

def load_candles(symbol,cutoff,replay=False):
 path=ROOT/'cache'/f'{symbol}.json'
 candles=json.loads(path.read_text()) if path.exists() else []
 candles=[c for c in candles if c[6]<cutoff]
 if replay:
  if not candles or candles[-1][0]!=cutoff-MS:
   raise ValueError('Replay exige cache com cobertura ate a ultima vela anterior ao corte')
 else:
  # Atualizar a cauda ANTES de decidir se os oito niveis ja possuem 50 linhas.
  while candles and candles[-1][0]<cutoff-MS:
   start=candles[-1][0]+MS
   data=request('/fapi/v1/klines',{'symbol':symbol,'interval':'5m','limit':1500,'startTime':start,'endTime':cutoff-1})
   data=[c for c in data if start<=c[0]<cutoff and c[6]<cutoff]
   if not data:raise ValueError('Nao foi possivel atualizar o cache ate a data de corte')
   candles.extend(data)
 for a,b in zip(candles,candles[1:]):
  if b[0]-a[0]!=MS:raise ValueError('Cache com lacunas ou duplicatas')
 return candles

def process(symbol,cutoff,replay=False):
 path=ROOT/'cache'/f'{symbol}.json'; candles=load_candles(symbol,cutoff,replay)
 for page in range(40):
  if len(candles)>=300:
   groups=analyze(candles)
   if all(len(v)>=50 for v in groups.values()):break
  if replay:raise ValueError('Replay sem 50 ocorrencias em cada nivel')
  end=candles[0][0]-1 if candles else cutoff-1
  data=request('/fapi/v1/klines',{'symbol':symbol,'interval':'5m','limit':1500,'endTime':end})
  if not data:break
  old_first=candles[0][0] if candles else cutoff
  data=[c for c in data if c[0]<old_first and c[6]<cutoff]
  if not data:break
  candles=data+candles;path.write_text(json.dumps(candles,separators=(',',':')))
 if not candles or candles[-1][0]!=cutoff-MS:raise ValueError('Cobertura nao alcanca a data de corte')
 path.write_text(json.dumps(candles,separators=(',',':')))
 groups=analyze(candles)
 # Detect gaps; do not silently compute RSI across missing candles.
 gaps=[(a[0],b[0]) for a,b in zip(candles,candles[1:]) if b[0]-a[0]!=MS]
 if gaps or not all(len(v)>=50 for v in groups.values()):raise ValueError('Historico incompleto')
 result={'symbol':symbol,'candles':len(candles),'coverage_start':candles[0][0] if candles else None,'coverage_end':candles[-1][0] if candles else None,'gaps':gaps,'groups':{k:v[-50:] for k,v in groups.items()},'available':{k:len(v) for k,v in groups.items()}}
 (ROOT/'resultados'/f'{symbol}.json').write_text(json.dumps(result,separators=(',',':')))
 print(symbol,len(candles),[len(v) for v in result['groups'].values()],'gaps',len(gaps),flush=True)
 return result

def symbols():
 with zipfile.ZipFile(ROOT/'fontes'/'Futuros - Pesquisa Histórica.docx') as z:r=ET.fromstring(z.read('word/document.xml'))
 text=''.join(r.itertext()).split('GRÁFICOS')[0]; names=list(dict.fromkeys(re.findall(r'\b[A-Z0-9]+USDT\b',text)))
 assert len(names)==64,len(names)
 return names

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--replay-cutoff',type=int,help='Reproduzir offline um corte explicito usando o snapshot do cache')
 args=parser.parse_args(); replay=args.replay_cutoff is not None
 for folder in ['cache','resultados']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
 names=symbols(); meta=json.loads((ROOT/'fontes'/'exchangeInfo.json').read_text()) if replay else request('/fapi/v1/exchangeInfo'); available={s['symbol'] for s in meta['symbols']}; missing=set(names)-available
 if not replay:(ROOT/'fontes'/'exchangeInfo.json').write_text(json.dumps(meta,separators=(',',':')))
 cutoff=args.replay_cutoff if replay else request('/fapi/v1/time')['serverTime']//MS*MS
 if cutoff%MS:raise ValueError('Corte precisa coincidir com fechamento de 5 minutos')
 summary={'cutoff_ms':cutoff,'symbols':names,'missing_symbols':sorted(missing),'results':[],'errors':{}}
 print('cutoff',datetime.datetime.fromtimestamp(cutoff/1000,datetime.timezone.utc),'missing',missing,flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  tasks={pool.submit(process,s,cutoff,replay):s for s in names if s in available}
  for f in concurrent.futures.as_completed(tasks):
   s=tasks[f]
   try:summary['results'].append(f.result())
   except Exception as e:summary['errors'][s]=str(e); print('ERROR',s,str(e),flush=True)
   (ROOT/'resultados'/'consolidado.json').write_text(json.dumps(summary,separators=(',',':')))
 print('DONE',len(summary['results']),'errors',summary['errors'],flush=True)
 if missing or summary['errors'] or len(summary['results'])!=64:raise SystemExit(1)

if __name__=='__main__':main()
