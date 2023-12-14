import atexit
import json
import requests
import sys

from absl import app
from absl import flags
import sqlitedict


FLAGS = flags.FLAGS
flags.DEFINE_string('positions', '../data/sinqcup23-positions.txt', 'Input')
flags.DEFINE_integer('depth', 1, '')

flags.DEFINE_string('analysis_server_url', 'http://127.0.0.1:5000/analyze', '') # depth=DDD&fen=FFF
flags.DEFINE_string('cache', '../data/cache.db', '')


def main(argv):
  cache = sqlitedict.open(filename=FLAGS.cache,
                          flag='c',
                          encode=json.dumps,
                          decode=json.loads)

  atexit.register(lambda: cache.commit())
  adds = 0
  flush_freq = 100

  with open(FLAGS.positions, 'r') as f:
    for row, fen in enumerate(f.readlines()):
      if row % 100 == 0:
        print(row)
        sys.stdout.flush()
      fen = fen.strip()
      key = f'{fen}|{FLAGS.depth}'
      if key in cache:
        continue
      url = f'{FLAGS.analysis_server_url}?depth={FLAGS.depth}&fen={fen}'
      response = requests.get(url)

      assert(response.status_code == 200), response
      cache[key] = response.json()
      adds += 1
      if adds % flush_freq == 0:
        cache.commit()

  cache.commit()

if __name__ == "__main__":
  app.run(main)
