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

FLAGS = flags.FLAGS
flags.DEFINE_string('pgn', '../data/sinqcup23.pgn', 'Input')
flags.DEFINE_string('engine', './stockfish', '')
flags.DEFINE_string('cache', 'cache.db', '')
flags.DEFINE_integer('hash_size', 1024, '')
flags.DEFINE_integer('threads', 1, '')
flags.DEFINE_integer('depth', 1, '')
flags.DEFINE_integer('flush_freq', 10, '')
flags.DEFINE_integer('np', 1, 'num processes')

def simplify_pv(pv):
  return [move.uci() for move in pv]


def simplify_score(score, board):
  return score.pov(WHITE).score()


def pv_to_san(board, pv):
  board = board.copy()
  res = []
  for move in pv:
    res.append(board.san(move))
    board.push(move)
  return res


def gen_games(fn):
  f = open(fn, 'r', encoding='utf-8', errors='replace')
  while True:
    g = chess.pgn.read_game(f)
    if g is None:
      return
    yield g # Game


def simplify_fen(board):
  #rn2kbnr/ppq2pp1/4p3/2pp2Bp/2P4P/1Q6/P2NNPP1/3RK2R w Kkq - 2 13
  return ' '.join(board.fen().split(' ')[0:4])


def gen_simplified_fens(game):
  board = game.board()
  for ply, move in enumerate(game.mainline_moves()):
    board.push(move)
    yield simplify_fen(board) # FEN after move


def search_at_depth(engine, board: chess.Board, depth: int):
  multi = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=1)
  m = multi[0]
  pv = m.get('pv', [])
  return {
    'depth': depth,
    'ev': simplify_score(m['score'], board),
    'wdl': m['wdl'].pov(WHITE).expectation(),
    'best': board.san(pv[0]),
    'pv': pv_to_san(board, pv),
    'time': m['time'],
    'nodes': m['nodes'],
  }

# Search with iterative deepening.
def search_deeply(engine, fen: str, max_depth: int) -> list:
  engine.configure({"Clear Hash": None})
  board = chess.Board(fen)
  return [search_at_depth(engine, board, depth) for depth in range(max_depth + 1)]


def analysis_worker(request_queue, response_queue, engine, hash_size, max_depth) -> None:

  engine = chess.engine.SimpleEngine.popen_uci(engine)

  engine.configure({'Hash': hash_size})
  engine.configure({'Threads': 1})
  engine.configure({'UCI_ShowWDL': 'true'})

  while True:
    task = request_queue.get()

    #fen, max_depth, engine, hash_size = task
    if task is None:  # Exit signal
      engine.quit()
      break
    fen = task
    response_queue.put(search_deeply(engine, fen, max_depth))



def main(argv):
  request_queue = multiprocessing.Queue()
  response_queue = multiprocessing.Queue()

  processes = []
  for _ in range(FLAGS.np):
    process = multiprocessing.Process(target=analysis_worker, args=(request_queue, response_queue, FLAGS.engine, FLAGS.hash_size, FLAGS.depth))
    process.start()
    processes.append(process)

  cache = sqlitedict.open(filename=FLAGS.cache,
                          flag='c',
                          encode=json.dumps,
                          decode=json.loads)

  # engine = chess.engine.SimpleEngine.popen_uci(FLAGS.engine)
  # engine.configure({'Hash': FLAGS.hash_size})
  # engine.configure({'Threads': FLAGS.threads})
  # engine.configure({'UCI_ShowWDL': 'true'})

  fens = set() # Unique across all games.
  for g in gen_games(FLAGS.pgn):
    fens.update(gen_simplified_fens(g))
  print('FENS: ', len(fens))

  foo = list(fens)
  random.shuffle(foo)

  wins = 0
  queued = 0
  print('Queueing')
  for fen in foo:
    multi = cache.get(fen, None)
    if multi and multi[-1]['depth'] >= FLAGS.depth:
      wins += 1
      continue
    queued += 1
    request_queue.put(fen)

  print(f'Queued, wins={wins}, queued={queued}')

  longest = 0.0
  last = time.time()
  flushes = 0
  for writes in (pbar := tqdm.tqdm(range(queued))):
    pbar.set_postfix({'longest': longest, 'flushes': flushes})
    res = response_queue.get()
    cache[fen] = res

    if res[-1]['time'] > longest:
      longest = res[-1]['time']
    if writes > 0 and (writes % FLAGS.flush_freq == 0 or time.time() > (last + 60.0)):
      last = time.time()
      cache.commit()
      flushes += 1
  cache.commit()

  print('Writing Nones')
  for p in range(FLAGS.np):
    request_queue.put(None)
  print('Joining')
  for p in processes:
    p.join()
  print('Joined')


  #pbar = tqdm.tqdm(foo)
  # for fen in pbar:
  #   pbar.set_postfix({'wins': wins, 'writes': writes, 'longest': longest})
  #   multi = cache.get(fen, None)
  #   if multi and multi[-1]['depth'] >= FLAGS.depth:
  #     wins += 1
  #     continue
  #   res = search_deeply(engine, fen, FLAGS.depth)
  #   cache[fen] = res
  #   if res[-1]['time'] > longest:
  #     longest = res[-1]['time']
  #   writes += 1
  #   if writes % FLAGS.flush_freq == 0:
  #     cache.commit()
  # cache.commit()
  # engine.quit()
  # print()
  # print('Wins: ', wins)
  # print('Writes: ', writes)
  #print(f'{depth:2d}. {res["ev"]:8d} {res["wdl"]:5.3f} {res["best"]:10s} {res["time"]:4.1f}s {res["nodes"]:8d} {" ".join(res["pv"])}')


if __name__ == "__main__":
  app.run(main)
