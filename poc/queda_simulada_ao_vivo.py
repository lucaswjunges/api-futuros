"""Teste ao vivo (E2E): derruba a conexão cobrindo a virada de uma vela 5m e verifica que,
ao reconectar, a vela é avaliada (captada) para os 8 pares (recuperada=True). Leva ~2 a 10 min.

A vela testada precisa ser uma que também fecha uma vela de 15m (item 4.5-b, confirmado com o
cliente em 19/09/2026: só nesses fechamentos há captação/CSV/pop-up) — senão o teste reportaria
FALHOU mesmo com a recuperação funcionando certinho, só porque aquela vela nunca seria captada.

Uso: python queda_simulada_ao_vivo.py   (grava log/CSV em evidencias/)
"""
import asyncio, logging, threading, time
from pathlib import Path

import alerta_futuros as af


def main() -> None:
    agora = time.time() * 1000
    virada = (int(agora) // af.MS_5M + 1) * af.MS_5M
    if virada - agora < 60_000:
        virada += af.MS_5M
    while not af.fecha_vela_15m(virada - af.MS_5M):
        virada += af.MS_5M  # avança até uma virada que também fecha a vela de 15m
    inicio_queda = virada - 15_000
    fim_queda = virada + 20_000

    class MonitorComQueda(af.Monitor):
        derrubou = False
        async def _ler(self, ws):
            if not self.derrubou:
                espera = (inicio_queda - time.time() * 1000) / 1000
                leitura = asyncio.create_task(super()._ler(ws))
                await asyncio.sleep(espera)
                leitura.cancel()
                self.derrubou = True
                af.log.warning("QUEDA SIMULADA: leitura parada; conexão será derrubada às %s",
                               time.strftime("%H:%M:%S", time.localtime(fim_queda / 1000)))
                await asyncio.sleep((fim_queda - time.time() * 1000) / 1000)
                raise ConnectionError("queda simulada")
            await super()._ler(ws)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    pasta = Path(__file__).with_name("evidencias")
    reg = af.Registro(pasta)
    reg.caminho.rename(pasta / f"teste_queda_{reg.caminho.name}")
    avaliadas = []
    def ao_avaliar(av):
        reg.gravar(av); avaliadas.append(av)
    m = MonitorComQueda(af.Parametros(), ao_avaliar)
    af.log.info("Virada testada: %s · queda de %s a %s", *(time.strftime("%H:%M:%S", time.localtime(x / 1000)) for x in (virada, inicio_queda, fim_queda)))
    t = threading.Thread(target=lambda: asyncio.run(m.executar()), daemon=True); t.start()
    while time.time() * 1000 < fim_queda + 15_000:
        time.sleep(0.5)
    m.parar.set(); t.join(timeout=3)
    alvo = virada - af.MS_5M
    rec = [a for a in avaliadas if a.abertura_ms == alvo]
    ok = len(rec) == 8 and all(a.recuperada for a in rec)
    af.log.info("RESULTADO: %d/8 pares avaliados para a vela %s, recuperada=%s, reconexões=%d -> %s",
                len(rec), time.strftime("%H:%M", time.localtime(virada / 1000)), all(a.recuperada for a in rec) if rec else None,
                m.reconexoes, "PASSOU" if ok else "FALHOU")
    reg.fechar()


if __name__ == "__main__":
    main()
