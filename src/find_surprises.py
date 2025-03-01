from absl import app
from absl import flags
from chess import WHITE, BLACK
import chess
import chess.engine
import chess.pgn
import json
import multiprocessing
import pprint
import random
import sqlitedict
import time
import tqdm
import collections

FLAGS = flags.FLAGS
flags.DEFINE_string('cache', 'cache.db', '')

def omain(argv):
  cache = sqlitedict.open(filename=FLAGS.cache,
                          flag='r',
                          encode=json.dumps,
                          decode=json.loads)
  n = 0
  d = collections.defaultdict(int)
  for k, v in cache.items():
    d[len(v)] += 1
  pprint.pprint(d, width=1)


def main(argv):
  cache = sqlitedict.open(filename=FLAGS.cache,
                          flag='r',
                          encode=json.dumps,
                          decode=json.loads)
  n = 0
  d = collections.defaultdict(int)
  mx = 0.0
  mx_fen = None
  for fen, v in cache.items():
    b1 = v[-1]['best']
    b2 = v[-2]['best']
    if b1 == b2:
      continue
    v1 = v[-1]['wdl']
    v2 = v[-2]['wdl']
    dv = v1 - v2
    if dv > mx:
      print(dv)
      mx = dv
      mx_fen = fen
  print()
  print(mx_fen, mx)
  for ent in cache[mx_fen]:
    print(ent['best'], ent['ev'], ent['wdl'])




if __name__ == "__main__":
  app.run(main)
