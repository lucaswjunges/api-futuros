"""Prepara arquivos locais; nunca publica nem modifica paginas do site."""
from pathlib import Path
import argparse, hashlib, json, shutil, sys, zipfile
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'poc'))
from publicar_versao import gerar

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=ROOT/'poc/dist/AlertaFuturos.exe')
    args = parser.parse_args()
    base = ROOT/'entrega-v1.2'; private = base/'privado'; stage = base/'publicar-apos-aceite'
    private.mkdir(exist_ok=True); (stage/'assets').mkdir(parents=True, exist_ok=True)
    info = gerar(args.exe, 'Avaliação em 5 minutos e aviso na tela desligado por padrão', planos=['completa'])
    for target in [private/'AlertaFuturos.exe', stage/'assets/AlertaFuturos.exe']:
        if args.exe.resolve() != target.resolve(): shutil.copy2(args.exe, target)
    for folder in [private, stage]:
        (folder/'versao.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ['GUIA-INSTALACAO-CLIENTE.md', 'GUIA-INSTALACAO-CLIENTE.html']:
        shutil.copy2(ROOT/'poc'/name, private/name)
    research = ROOT/'pesquisa-historica/outputs/entrega-roberto'
    names = ['AlertaFuturos.exe','versao.json','GUIA-INSTALACAO-CLIENTE.md','GUIA-INSTALACAO-CLIENTE.html']
    files = {f'App-1.2/{name}':private/name for name in names}
    files.update({f'Pesquisa-Historica/{name}':research/name for name in ['Pesquisa-Historica-Roberto-Urbano.xlsx','INSTRUCAO-DE-USO.html']})
    inventory = {name:{'tamanho':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for name,p in files.items()}
    (base/'manifesto-entrega.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(base/'Entrega-Alerta-Futuros-Roberto-apos-aceite.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name,p in files.items(): z.write(p,name)
    with zipfile.ZipFile(base/'AlertaFuturos-1.2-entrega.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(private/name,name)
    print('Pacotes locais preparados. Publicação exige confirmação do aceite e do Pix.')
if __name__ == '__main__': main()
