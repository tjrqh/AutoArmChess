"""MuJoCo 시뮬레이션 메인 루프."""

from __future__ import annotations

import time
from concurrent.futures import Future

import chess
import mujoco

try:
    import mujoco.viewer
except Exception:  # pragma: no cover - headless 서버에서 viewer import가 실패할 수 있다.
    mujoco_viewer = None
else:
    mujoco_viewer = mujoco.viewer

from ai.minimax import MinimaxEngine
from config.config import Settings
from core.models import ChessMoveCommand, RobotTaskState
from sim.robot_controller import RobotController


class ChessRobotSimulator:
    """체스 게임, AI, 로봇 제어, MuJoCo step을 통합하는 오케스트레이터.

    통합 Loop:
        1. AI 백그라운드 작업 확인 및 시작 (필요시)
        2. 로봇 컨트롤러 step (FSM 진행)
        3. MuJoCo 물리 step
    
    Headless 모드에서는 viewer를 만들지 않고 `mj_step`만 호출한다. 이 모드는
    대량 학습과 수만 회 시뮬레이션에 적합하다. GUI 모드는 같은 로직을 사용하되
    `mujoco.viewer`를 붙여 디버깅과 시각 검증에 사용한다.
    """

    def __init__(self, settings: Settings, headless: bool | None = None) -> None:
        self.settings = settings
        self.headless = settings.simulation.headless if headless is None else headless
        self.model = mujoco.MjModel.from_xml_path(str(settings.simulation.model_path))
        self.model.opt.timestep = settings.simulation.timestep
        self.data = mujoco.MjData(self.model)
        self.board = chess.Board()
        self.robot = RobotController(self.model, self.data, settings)
        self.ai = MinimaxEngine(depth=settings.ai.depth)
        self._pending_ai_future: Future[chess.Move | None] | None = None

    def run(self, max_steps: int | None = None) -> None:
        """시뮬레이션을 실행한다."""

        if self.headless:
            self._run_headless(max_steps=max_steps)
        else:
            self._run_gui(max_steps=max_steps)

    def _run_headless(self, max_steps: int | None) -> None:
        """렌더링 없이 물리/AI/제어 루프만 실행한다."""

        step = 0
        while max_steps is None or step < max_steps:
            self.step()
            step += 1

    def _run_gui(self, max_steps: int | None) -> None:
        """MuJoCo viewer를 붙여 GUI 모드로 실행한다."""

        if mujoco_viewer is None:
            raise RuntimeError("MuJoCo viewer를 사용할 수 없습니다. headless 모드로 실행하세요.")

        step = 0
        with mujoco_viewer.launch_passive(self.model, self.data) as viewer:
            while viewer.is_running() and (max_steps is None or step < max_steps):
                frame_start = time.perf_counter()
                self.step()
                viewer.sync()
                step += 1

                elapsed = time.perf_counter() - frame_start
                target_dt = 1.0 / self.settings.simulation.control_hz
                if elapsed < target_dt:
                    time.sleep(target_dt - elapsed)

    def step(self) -> None:
        """AI 상태, 로봇 FSM, MuJoCo 물리 step을 한 번 진행한다."""

        self._maybe_start_ai_job()
        self._maybe_consume_ai_job()

        robot_state = self.robot.step()
        if robot_state == RobotTaskState.COMPLETE:
            self.robot.state = RobotTaskState.IDLE

        mujoco.mj_step(self.model, self.data)

    def is_robot_busy(self) -> bool:
        """로봇이 현재 이동 궤적을 수행 중인지 반환한다."""

        return self.robot.state not in (RobotTaskState.IDLE, RobotTaskState.COMPLETE)

    def has_pending_ai(self) -> bool:
        """AI 백그라운드 계산이 진행 중인지 반환한다."""

        return self._pending_ai_future is not None

    def apply_user_move(self, uci: str) -> bool:
        """사용자 수를 검증하고 보드에 적용한다.

        Returns:
            합법수이면 True, 불법수이면 False.
        """

        move = chess.Move.from_uci(uci)
        if move not in self.board.legal_moves:
            return False
        self.board.push(move)
        return True

    def _maybe_start_ai_job(self) -> None:
        """AI 차례가 되었고 로봇이 쉬고 있으면 백그라운드 탐색을 시작한다."""

        if self.board.is_game_over():
            return
        if self.board.turn != chess.BLACK:
            return
        if self.robot.state != RobotTaskState.IDLE:
            return
        if self._pending_ai_future is not None:
            return

        self._pending_ai_future = self.ai.best_move_async(self.board.fen())

    def _maybe_consume_ai_job(self) -> None:
        """완료된 AI 결과를 로봇 이동 명령으로 변환한다."""

        if self._pending_ai_future is None or not self._pending_ai_future.done():
            return

        move = self._pending_ai_future.result()
        self._pending_ai_future = None
        if move is None:
            return

        self.robot.plan_move(ChessMoveCommand.from_uci(move.uci()))
        self.board.push(move)

    def close(self) -> None:
        """백그라운드 리소스를 정리한다.
        
        AI 스레드풀을 정상 종료하고 모든 pending 작업이 완료되기를 기다린다.
        """

        self.ai.shutdown()
