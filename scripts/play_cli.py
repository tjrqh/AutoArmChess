"""터미널 기반 체스 게임 검증 스크립트.

이 스크립트는 아직 웹/마우스 UI가 없는 단계에서 게임 루프가 실제로
작동하는지 확인하기 위한 최소 플레이어 인터페이스다.

흐름:
    1. 사용자가 백(White)으로 UCI 수를 입력한다. 예: e2e4
    2. python-chess가 합법수인지 검증한다.
    3. AI가 별도 스레드에서 흑(Black)의 응수를 계산한다.
    4. 로봇 컨트롤러가 해당 흑 수에 대한 Pick-and-Place 궤적을 수행한다.
    5. 다시 사용자 차례로 돌아온다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import load_settings
from sim.simulator import ChessRobotSimulator


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-wait-steps",
        type=int,
        default=6000,
        help="AI와 로봇 이동 완료를 기다릴 최대 시뮬레이션 step 수",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="각 시뮬레이션 step 사이에 쉴 시간. GUI가 아닌 CLI에서는 보통 0이면 충분하다.",
    )
    return parser.parse_args()


def print_board(board: chess.Board) -> None:
    """현재 보드 상태를 터미널에 출력한다.
    
    보드 상태, FEN 문자열, 그리고 게임 상태를 시각적으로 표시한다.
    """

    print()
    print(board)
    print()
    print(f"FEN: {board.fen()}")
    print()


def wait_for_ai_and_robot(simulator: ChessRobotSimulator, max_steps: int, sleep: float) -> str | None:
    """AI 응수와 로봇 이동이 끝날 때까지 시뮬레이션을 진행한다.

    Returns:
        AI가 둔 UCI 수. 시간 초과 또는 게임 종료면 None.
    """

    before_ply = simulator.board.ply()
    ai_move_uci: str | None = None

    for _ in range(max_steps):
        simulator.step()

        if simulator.board.ply() > before_ply and ai_move_uci is None:
            ai_move_uci = simulator.board.peek().uci()
            print(f"AI(Black): {ai_move_uci}")

        if simulator.board.turn == chess.WHITE and not simulator.has_pending_ai() and not simulator.is_robot_busy():
            return ai_move_uci

        if simulator.board.is_game_over():
            return ai_move_uci

        if sleep > 0:
            time.sleep(sleep)

    print("AI/로봇 이동 대기 시간이 초과되었습니다.")
    return ai_move_uci


def main() -> None:
    """터미널에서 백으로 체스를 두며 AI/로봇 루프를 확인한다."""

    args = parse_args()
    settings = load_settings()
    simulator = ChessRobotSimulator(settings=settings, headless=True)

    print("AI 체스 로봇팔 CLI 검증 모드")
    print("사용자는 White입니다. UCI 형식으로 입력하세요. 예: e2e4, g1f3")
    print("종료하려면 quit 또는 exit 입력")

    try:
        while not simulator.board.is_game_over():
            print_board(simulator.board)
            user_input = input("White move> ").strip().lower()

            if user_input in {"quit", "exit"}:
                break

            try:
                accepted = simulator.apply_user_move(user_input)
            except ValueError:
                accepted = False

            if not accepted:
                print(f"불법수입니다: {user_input}")
                continue

            print(f"You(White): {user_input}")
            if simulator.board.is_game_over():
                break

            wait_for_ai_and_robot(
                simulator=simulator,
                max_steps=args.max_wait_steps,
                sleep=args.sleep,
            )

        print_board(simulator.board)
        if simulator.board.is_game_over():
            print(f"게임 종료: {simulator.board.result()} ({simulator.board.outcome()})")
    finally:
        simulator.close()


if __name__ == "__main__":
    main()

