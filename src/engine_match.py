from atexit import register
from collections import Counter
import datetime
import functools
import os
import random
import sys
import time

import chess
from chess import WHITE, BLACK
import chess.engine
import chess.pgn

from absl import app
from absl import flags

FLAGS = flags.FLAGS

flags.DEFINE_string('openings', '../data/openings.pgn', '')
flags.DEFINE_string('engine1', 'stockfish', '')
flags.DEFINE_string('engine2', 'lc0', '')

flags.DEFINE_integer('depth', 1, 'Fixed depth')
flags.DEFINE_integer('engine1_hash', 512, '')
flags.DEFINE_integer('engine2_hash', 0, '')

flags.DEFINE_integer('num_matches', 1, 'Number of two game matches to play')
flags.DEFINE_string('outd', '', 'Output directory/prefix')

THREADS = 1

def openw(fn):
  fn = os.path.join(FLAGS.outd, fn)
  print(f'Open {fn}')
  return open(fn, 'w')


def play_best1(engine, board):
  return engine.analyse(board, chess.engine.Limit(depth=FLAGS.depth))


def gen_games(fn):
  print(f'Open {fn}')
  with open(fn, 'r', encoding='utf-8', errors='replace') as f:
    while True:
      game = chess.pgn.read_game(f)
      if game is None:
        return
      yield game


def create_game(opening_board, moves, bot1, bot2, xround, result, elapsed1, elapsed2):
  game = chess.pgn.Game()
  game.headers['Event'] = 'Depth match'
  game.headers['Site'] = 'CasaDava'
  game.headers['Date'] = datetime.date.today().strftime('%Y.%m.%d')
  game.headers['X-Time'] = datetime.datetime.now().strftime('%H:%M:%S')
  game.headers['White'] = bot1['name']
  game.headers['Black'] = bot2['name']
  game.headers['Round'] = str(xround)
  game.headers['Result'] = result
  game.headers['Ply'] = str(len(opening_board.move_stack) + len(moves))
  game.headers['X-Depth'] = str(FLAGS.depth)
  game.headers['X-White-Time-Used'] = f'{elapsed1:.1f}s'
  game.headers['X-Black-Time-Used'] = f'{elapsed2:.1f}s'
  game.headers['X-FEN'] = opening_board.fen()

  node = game # duck typing
  for move in opening_board.move_stack:
    node = node.add_main_variation(move)
  node.comment = 'End of opening'

  for move in moves:
    node = node.add_main_variation(move)

  return game


def play_2_games(board, bot1, bot2):
  oboard = board.copy()
  (moves1, outcome1, board1, dt1a, dt1b) = play_1_game(board,  bot1, bot2)
  (moves2, outcome2, board2, dt2a, dt2b) = play_1_game(oboard, bot2, bot1)

  return [(moves1, outcome1.result(), board1, dt1a, dt1b),
          (moves2, outcome2.result(), board2, dt2a, dt2b)]

def play_1_game(board, bot1, bot2):
  moves = []
  ply = -1

  bots = [bot1, bot2]
  dts = [0.0, 0.0]

  while True:
    ply += 1
    outcome = board.outcome()
    if outcome is not None:
      break

    if board.turn == WHITE:
      which = 0
    else:
      which = 1
    bot = bots[which]

    t1 = time.time()
    if bot['hash']:
      bot['engine'].configure({"Clear Hash": None})
    res = play_best1(bot['engine'], board)
    dts[which] += time.time() - t1

    move = res['pv'][0]
    moves.append(move)

    board.push(move)

  return moves, outcome, board, dts[0], dts[1]


def playthrough(game):
  board = chess.Board()
  for move in game.mainline_moves():
    board.push(move)
  return board


def read_opening(fn: str):
  print(f'Read {fn}')
  return [playthrough(game) for game in gen_games(fn)]


def create_engine(binary, hash_size):
  engine = chess.engine.SimpleEngine.popen_uci(binary)
  if hash_size:
    engine.configure({'hash': hash_size})
    engine.configure({'Threads': THREADS})
  return engine

def create_bot(engine, hash_size, depth):
  return {
    'name': f'{engine}(d={depth})',
    'hash': hash_size,
    'engine': create_engine(engine, hash_size)
  }

def create_bots():
  return [create_bot(FLAGS.engine1, FLAGS.engine1_hash, FLAGS.depth),
          create_bot(FLAGS.engine2, FLAGS.engine2_hash, FLAGS.depth)]


def at_shutdown(engine1, engine2):
  print('Shutdown')
  engine1.quit()
  engine2.quit()

def main(_argv):
  t0 = time.time()

  e1_win, e1_lose, e1_draw = 0, 0, 0

  opening_boards = read_opening(FLAGS.openings)
  random.shuffle(opening_boards)

  print('Openings: ', len(opening_boards))

  bot1, bot2 = create_bots() # 'name', 'engine'

  f_summary = openw('summary.csv')

  # So outcomes are from bot1's POV.
  FLIP = {
    "1-0": "0-1",
    "1/2-1/2": "1/2-1/2",
    "0-1": "1-0"
    }

  f_pgn = openw('match.pgn')

  bot1_results = Counter({'1-0': 0,
                          '0-1': 0,
                          '1/2-1/2': 0})

  engine_time = [0.0, 0.0]

  for xround, opening_board in enumerate(opening_boards):
    if FLAGS.num_matches and xround >= FLAGS.num_matches:
      break
    print(f'Game {xround:4d} {opening_board.fen()}')

    ((m1, r1, b1, dt1a, dt1b), (m2, r2, b2, dt2a, dt2b)) = play_2_games(opening_board.copy(), bot1, bot2)

    engine_time[0] += dt1a + dt2b
    engine_time[1] += dt1b + dt2a

    bot1_results[r1] += 1
    bot1_results[FLIP[r2]] += 1

    print(f'{2 * xround + 1} {r1:8s} {dt1a:4.1f}s {dt1b:4.1f}s')
    print(f'{2 * xround + 2} {r2:8s} {dt2a:4.1f}s {dt2b:4.1f}s')
    win = bot1_results['1-0']
    lose = bot1_results['0-1']
    draw = bot1_results['1/2-1/2']
    print(f'\tengine1: win={win} lose={lose} draw={draw}')

    game1 = create_game(opening_board.copy(), m1, bot1, bot2, 2 * xround + 1, r1, dt1a, dt1b)
    game2 = create_game(opening_board.copy(), m2, bot2, bot1, 2 * xround + 2, r2, dt2a, dt2b)

    f_pgn.write(str(game1) + '\n\n')
    f_pgn.write(str(game2) + '\n\n')
    f_pgn.flush()

  bot1['engine'].quit()
  bot2['engine'].quit()

  assert len(bot1_results) == 3, bot1_results

  win = bot1_results['1-0']
  lose = bot1_results['0-1']
  draw = bot1_results['1/2-1/2']

  print(f'Win:  {win}')
  print(f'Lose: {lose}')
  print(f'Draw: {draw}')
  print()
  print('Engine1 time: {engine_time[0]:.1f}s')
  print('Engine2 time: {engine_time[1]:.2f}s')

  print('Exiting...')
  sys.exit(0)


  def _pc(a, b):
    if b == 0:
      return 0
    assert b > 0, (a, b)
    return 100.0 * ((a + 0.0) / (b + 0.0))

  ng = e1_win + e1_lose + e1_draw
  e1_points = e1_win + (e1_draw / 2.0)

  f = openw('final.txt')
  f.write(f'Depth: {FLAGS.depth}\n')
  f.write(f'NumMatches: {FLAGS.num_matches}\n')
  f.write(f'NumOpenings: {len(opening_boards)}\n')
  f.write('\n')
  f.write(f'Elapsed: {time.time() - t0:.1f}s\n')
  f.write(f'Games: {ng}\n')
  f.write('\n')
  f.write(f'Win: {e1_win}\n')
  f.write(f'Lose: {e1_lose}\n')
  f.write(f'Draw: {e1_draw}\n')
  f.write(f'Points: {e1_points}\n')
  f.write('\n')
  f.write(f'Win%: {_pc(e1_win, ng):.0f}\n')
  f.write(f'Lose%: {_pc(e1_lose, ng):.0f}\n')
  f.write(f'Draw%: {_pc(e1_draw, ng):.0f}\n')
  f.write(f'Points%: {_pc(e1_points, ng):.0f}\n')
  f.write('\n')
  f.write(f'Special: {tot_special}\n')
  f.write(f'Possible: {tot_special_possible}\n')
  f.close()

  f_pgn.write('\n\n')
  f_pgn.close()
  f_summary.close()
  print('finis')



if __name__ == "__main__":
  app.run(main)
