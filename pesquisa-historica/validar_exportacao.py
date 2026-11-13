from pathlib import Path
import json,zipfile,xml.etree.ElementTree as E,datetime,math,shutil
root=Path(__file__).resolve().parent;out=root/'outputs/entrega-roberto';d=json.loads((root/'resultados/consolidado.json').read_text());by={a['symbol']:a for a in d['results']};n={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(out/'Pesquisa-Historica-Roberto-Urbano.xlsx') as z:
 w=E.fromstring(z.read('xl/workbook.xml'));sheets=w.findall('m:sheets/m:sheet',n);assert [s.get('name') for s in sheets]==['Índice','Como ler',*d['symbols']]
 count=0
 for idx,sym in enumerate(d['symbols'],3):
  r=E.fromstring(z.read(f'xl/worksheets/sheet{idx}.xml'));cells={c.attrib['r']:c for c in r.findall('.//m:c',n)}
  assert not any(c.get('t')=='e' for c in cells.values())
  for l in range(1,9):
   for offset,row in enumerate(by[sym]['groups'][str(l)]):
    number=8+(l-1)*57+offset
    for col,key in [('C','first'),('D','count'),('E','second')]:
     c=cells[f'{col}{number}'];assert c.get('t')=='n';v=float(c.find('m:v',n).text);assert math.isclose(v,row[key],abs_tol=1e-12)
    for col in ['A','B']:
     c=cells[f'{col}{number}'];assert c.get('t')=='n'
     actual=(float(c.find('m:v',n).text)-25569)*86400000
     assert abs(actual-(row['open_ms']-10800000))<=2, (sym,number,col,actual,row['open_ms']-10800000)
    count+=1
assert count==25600
extra=out/'Pesquisa-Historica-Roberto-Urbano.xlsx.inspect.ndjson'
if extra.exists():shutil.move(str(extra),str(root/'authoring/export-inspect.ndjson'))
with zipfile.ZipFile(out/'Pesquisa-Historica-Roberto-Urbano.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in ['Pesquisa-Historica-Roberto-Urbano.xlsx','INSTRUCAO-DE-USO.html']:z.write(out/name,name)
print('XLSX salvo conferido: 66 abas, 512 tabelas e 25.600 linhas. Numeros e datas tipados. Pacotes prontos.')



