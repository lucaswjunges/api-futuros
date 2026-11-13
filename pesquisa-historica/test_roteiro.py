import unittest
from coletar import event,level

def candles(high,low,close): return [[i*300000,0,h,l,c] for i,(h,l,c) in enumerate(zip(high,low,close))]
class Roteiro(unittest.TestCase):
 def test_btc_superior(self):
  e=event(candles([82931,82946,82957,82958,82985,82985,83016],[82863,82923,82931,82953,82958,82981,82981],[82923,82940,82955,82958,82985,82981,83016]),[97.8,98.8,99.1,99.1,99.7,78.6,98.8],0,True)
  self.assertEqual(e['count'],4);self.assertAlmostEqual(e['first'],82985/82923-1);self.assertAlmostEqual(e['second'],82923/82981-1)
 def test_eth_superior_sem_elevacao(self):
  e=event(candles([2266,2266,2260,2257,2255,2253],[2262,2259,2255,2254,2250,2249],[2266,2259,2255,2255,2250,2250]),[95.3,34.7,18.3,18.3,5.5,11.1],0,True)
  self.assertEqual(e['count'],0);self.assertEqual(e['first'],0);self.assertAlmostEqual(e['second'],2266/2250-1)
 def test_near_inferior(self):
  e=event(candles([3.997,3.987,3.999,4.006,4.002],[3.975,3.966,3.978,3.992,3.974],[3.983,3.982,3.994,3.996,3.983]),[2.78,1.98,70.38,77.33,23.89],0,False)
  self.assertEqual(e['count'],1);self.assertAlmostEqual(e['first'],3.983/3.966-1);self.assertAlmostEqual(e['second'],4.006/3.983-1)
 def test_pepe_inferior_sem_queda(self):
  e=event(candles([.0050967,.0050978,.0051156],[.0050664,.0050640,.0050829],[.0050687,.0050972,.0050861]),[.82,63.52,37.22],0,False)
  self.assertEqual(e['count'],0);self.assertAlmostEqual(e['first'],.0050687/.0050640-1);self.assertAlmostEqual(e['second'],.0050978/.0050687-1)
 def test_limites(self):
  for v,l in [(100,1),(99,1),(98.999,2),(98,2),(97,3),(96,4),(95.3,5),(95,5),(94.99,None),(3,6),(2,6),(1.999,7),(1,7),(.999,8),(0,8)]:self.assertEqual(level(v),l)
 def test_sem_segunda_reversao(self):self.assertIsNone(event(candles([2]*4,[1]*4,[1.5]*4),[96,97,90,85],0,True))
if __name__=='__main__': unittest.main()
