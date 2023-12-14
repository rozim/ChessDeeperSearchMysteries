from absl import app
from absl import flags

import chess
import chess.pgn

FLAGS = flags.FLAGS
flags.DEFINE_string('pgn', '../data/sinqcup23.pgn', 'Input')


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


def main(argv):
  fens = set() # Unique across all games.
  for g in gen_games(FLAGS.pgn):
    fens.update(gen_simplified_fens(g))
  print('\n'.join(fens))


if __name__ == "__main__":
  app.run(main)
