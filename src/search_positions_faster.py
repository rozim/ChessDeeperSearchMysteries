import atexit
import functools
import json
import requests
import signal
import sys
import time

from absl import app
from absl import flags
import sqlitedict

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor


FLAGS = flags.FLAGS
flags.DEFINE_string('positions', '../data/sinqcup23-positions.txt', 'Input')
flags.DEFINE_integer('depth', 1, '')
flags.DEFINE_integer('workers', 4, '')

flags.DEFINE_string('analysis_server_url', 'http://127.0.0.1:5000/analyze', '') # depth=DDD&fen=FFF
flags.DEFINE_string('cache', '../data/cache.db', '')


def fetch_url(url, key):
  response = requests.get(url)
  assert(response.status_code == 200), (response, url, key)
  return response, url, key


def read_data(fn, cache):
  cache_win, cache_lose = 0, 0
  with open(fn, 'r') as f:
    urls = []
    for row, fen in enumerate(f.readlines()):
      fen = fen.strip()
      key = f'{fen}|{FLAGS.depth}'
      if key in cache:
        cache_win += 1
        continue
      cache_lose += 1
      url = f'{FLAGS.analysis_server_url}?depth={FLAGS.depth}&fen={fen}'
      urls.append((url, key))
    return urls, cache_win, cache_lose


def handle_sigterm(cache, sig, frame):
  print("Received SIGTERM signal, shutting down...")
  sys.stdout.flush()
  cache.commit()
  sys.exit(0)

def handle_atexit(cache):
  print('At exit...')
  cache.commit()
  print('At exit...done')

def main(argv):
  cache = sqlitedict.open(filename=FLAGS.cache,
                          flag='c',
                          encode=json.dumps,
                          decode=json.loads)

  atexit.register(functools.partial(handle_atexit, cache))
  signal.signal(signal.SIGTERM, functools.partial(handle_sigterm, cache))
  flush_freq = 10

  cache_commit, cache_add = 0, 0

  urls, cache_win, cache_lose = read_data(FLAGS.positions, cache)
  print("#URLs: ", len(urls))

  t1 = time.time()
  last_tick = t1
  with ThreadPoolExecutor(max_workers=FLAGS.workers) as executor:
    # futures = [executor.submit(fetch_url, url, key) for url, key in urls]
    print('Submitting')
    futures = set([executor.submit(fetch_url, url, key) for url, key in urls])
    print('Submitted: ', len(futures))
    for row, future in enumerate(concurrent.futures.as_completed(futures)):
      print('.', end='')
      sys.stdout.flush()
      now = time.time()
      dt = now - last_tick
      if row % 10 == 0 or (now - last_tick) >= 60.0:
        print(f'{row} {(now - t1):.1f} | add={cache_add} win={cache_win} lose={cache_lose} commit={cache_commit} len={len(cache)}')
        last_tick = time.time()
        cache.commit()
        sys.stdout.flush()
      http_resp, _, key = future.result()
      cache[key] = http_resp.json()
      cache_add += 1
      if cache_add % flush_freq == 0:
        cache.commit()
        cache_commit += 1

  print(f'Final commit {len(cache)}')
  cache.commit()

if __name__ == "__main__":
  app.run(main)
