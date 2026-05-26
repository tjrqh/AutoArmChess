"""비동기 실행에 적합한 Minimax + Alpha-Beta 체스 AI."""

from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor

import chess

from core.pieces import PIECE_VALUES


class MinimaxEngine:
    """python-chess 기반 Minimax 의사결정 엔진.

    `best_move_async`는 별도 스레드에서 탐색을 수행한다. 따라서 MuJoCo
    시뮬레이션 루프는 AI 계산 완료를 기다리며 멈추지 않고 FPS를 유지할 수 있다.
    """

    def __init__(self, depth: int, max_workers: int = 1) -> None:
        self.depth = depth
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def best_move_async(self, fen: str) -> Future[chess.Move | None]:
        """현재 FEN을 기준으로 최선 수 계산을 백그라운드에 제출한다."""

        return self._executor.submit(self.best_move, fen)

    def best_move(self, fen: str) -> chess.Move | None:
        """현재 FEN에서 최선 수를 동기적으로 계산한다."""

        board = chess.Board(fen)
        if board.is_game_over():
            return None

        maximizing = board.turn == chess.WHITE
        best_score = -math.inf if maximizing else math.inf
        best_move: chess.Move | None = None

        for move in self._ordered_moves(board):
            board.push(move)
            score = self._minimax(
                board=board,
                depth=self.depth - 1,
                alpha=-math.inf,
                beta=math.inf,
                maximizing=not maximizing,
            )
            board.pop()

            if maximizing and score > best_score:
                best_score = score
                best_move = move
            elif not maximizing and score < best_score:
                best_score = score
                best_move = move

        return best_move

    def _minimax(
        self,
        board: chess.Board,
        depth: int,
        alpha: float,
        beta: float,
        maximizing: bool,
    ) -> float:
        """Alpha-Beta Pruning이 적용된 Minimax 재귀 탐색."""

        if depth == 0 or board.is_game_over():
            return self._evaluate(board)

        if maximizing:
            value = -math.inf
            for move in self._ordered_moves(board):
                board.push(move)
                value = max(
                    value,
                    self._minimax(board, depth - 1, alpha, beta, False),
                )
                board.pop()
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value

        value = math.inf
        for move in self._ordered_moves(board):
            board.push(move)
            value = min(
                value,
                self._minimax(board, depth - 1, alpha, beta, True),
            )
            board.pop()
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    def _evaluate(self, board: chess.Board) -> float:
        """간단한 물질 가치 기반 평가 함수.

        양수는 백에게 유리, 음수는 흑에게 유리함을 의미한다. 실제 제품에서는
        위치 테이블, 킹 안전성, 폰 구조 평가를 추가하거나 Stockfish 연동으로
        교체할 수 있다.
        """

        if board.is_checkmate():
            return -math.inf if board.turn == chess.WHITE else math.inf
        if board.is_stalemate() or board.is_insufficient_material():
            return 0.0

        score = 0
        for piece_type, value in PIECE_VALUES.items():
            score += len(board.pieces(piece_type, chess.WHITE)) * value
            score -= len(board.pieces(piece_type, chess.BLACK)) * value
        return float(score)

    def _ordered_moves(self, board: chess.Board) -> list[chess.Move]:
        """가지치기 효율을 높이기 위해 잡는 수와 체크 수를 우선 탐색한다."""

        def move_priority(move: chess.Move) -> int:
            return int(board.is_capture(move)) * 2 + int(board.gives_check(move))

        return sorted(board.legal_moves, key=move_priority, reverse=True)

    def shutdown(self) -> None:
        """백그라운드 스레드풀을 정리한다."""

        self._executor.shutdown(wait=True)

