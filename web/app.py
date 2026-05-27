"""2D 체스 입력과 3D 로봇 애니메이션을 연결하는 FastAPI 웹 서버.

브라우저는 좌측 2D 체스판에서 사용자의 수를 입력하고, 서버는
`python-chess`로 합법수를 검증한다. 검증된 수와 AI 응수는 WebSocket으로
프론트엔드에 전달되며, Three.js 3D 장면은 이 메시지를 큐에 넣고 순차적으로
로봇팔 Pick-and-Place 애니메이션을 재생한다.

Flow:
    1. 사용자가 2D 보드에서 수를 선택 (HTTP POST)
    2. 백엔드가 합법수 검증 및 로봇 애니메이션 정보 생성
    3. WebSocket으로 모든 클라이언트에 이동 및 상태 브로드캐스트
    4. AI 계산 (비동기)
    5. AI 수 반영 및 로봇팔 재생 애니메이션 전송
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai.minimax import MinimaxEngine
from config.config import load_settings
from core.models import BoardSquare
from core.transforms import board_square_to_board_pose


settings = load_settings()
app = FastAPI(title="AI Chess Robot Arm Web")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web" / "static"), name="static")


class MoveRequest(BaseModel):
    """브라우저에서 보내는 사용자 이동 요청."""

    uci: str


@dataclass(frozen=True, slots=True)
class MoveAnimation:
    """웹 3D 로봇 애니메이션에 필요한 이동 데이터."""

    uci: str
    source: str
    target: str
    piece: str
    captured: str | None
    actor: str
    fen_after: str


class ConnectionManager:
    """WebSocket 클라이언트 목록을 관리하고 JSON 메시지를 브로드캐스트한다."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """클라이언트 연결을 등록한다."""

        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """끊어진 클라이언트를 제거한다."""

        self._clients.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """모든 클라이언트에 JSON 메시지를 전송한다."""

        stale_clients: list[WebSocket] = []
        for websocket in self._clients:
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_clients.append(websocket)

        for websocket in stale_clients:
            self.disconnect(websocket)


class WebChessGame:
    """웹 플레이용 체스 게임 상태와 AI 작업을 관리한다.

    사용자 입력은 HTTP POST로 들어오고, 시각 업데이트는 WebSocket으로 나간다.
    AI 계산과 로봇 애니메이션 대기 시간은 백그라운드 태스크에서 처리하므로
    HTTP 요청 처리 경로를 오래 붙잡지 않는다.
    """

    def __init__(self) -> None:
        self.board = chess.Board()
        self.engine = MinimaxEngine(depth=settings.ai.depth)
        self.manager = ConnectionManager()
        self.lock = asyncio.Lock()
        self.busy = False
        self.status = "white_turn"
        self.animation_seconds = 4.2
        self.generation = 0

    def snapshot(self) -> dict[str, Any]:
        """프론트엔드가 보드를 그리는 데 필요한 현재 상태를 만든다."""

        game_result = self._game_result_payload()
        return {
            "type": "state",
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "status": self.status,
            "legal_moves": [move.uci() for move in self.board.legal_moves],
            "game_over": self.board.is_game_over(),
            "result": self.board.result() if self.board.is_game_over() else None,
            "game_result": game_result,
        }

    def _game_result_payload(self) -> dict[str, str | None] | None:
        """초보자도 이해할 수 있는 게임 종료 메시지를 만든다."""

        outcome = self.board.outcome(claim_draw=True)
        if outcome is None:
            return None

        if outcome.winner == chess.WHITE:
            winner = "white"
            winner_label = "White"
        elif outcome.winner == chess.BLACK:
            winner = "black"
            winner_label = "Black"
        else:
            winner = "draw"
            winner_label = "Draw"

        reason_map = {
            chess.Termination.CHECKMATE: "체크메이트",
            chess.Termination.STALEMATE: "스테일메이트",
            chess.Termination.INSUFFICIENT_MATERIAL: "기물 부족 무승부",
            chess.Termination.SEVENTYFIVE_MOVES: "75수 규칙 무승부",
            chess.Termination.FIVEFOLD_REPETITION: "5회 반복 무승부",
            chess.Termination.FIFTY_MOVES: "50수 규칙 무승부",
            chess.Termination.THREEFOLD_REPETITION: "3회 반복 무승부",
            chess.Termination.VARIANT_WIN: "특수 승리",
            chess.Termination.VARIANT_LOSS: "특수 패배",
            chess.Termination.VARIANT_DRAW: "특수 무승부",
        }
        reason = reason_map.get(outcome.termination, "게임 종료")

        if outcome.termination == chess.Termination.CHECKMATE and outcome.winner is not None:
            message = f"{winner_label}가 체크메이트로 승리했습니다."
        elif outcome.winner is None:
            message = f"무승부입니다. 사유: {reason}"
        else:
            message = f"{winner_label}가 승리했습니다. 사유: {reason}"

        return {
            "winner": winner,
            "winner_label": winner_label,
            "reason": reason,
            "message": message,
        }

    async def reset(self) -> dict[str, Any]:
        """게임을 초기 상태로 되돌린다."""

        async with self.lock:
            self.generation += 1
            self.board.reset()
            self.busy = False
            self.status = "white_turn"
            payload = self.snapshot()
        await self.manager.broadcast(payload)
        return payload

    async def submit_user_move(self, uci: str) -> dict[str, Any]:
        """사용자 수를 검증하고 로봇/AI 턴 진행 백그라운드 작업을 시작한다."""

        async with self.lock:
            if self.busy:
                return {"ok": False, "error": "로봇 또는 AI가 동작 중입니다."}
            if self.board.turn != chess.WHITE:
                return {"ok": False, "error": "현재 사용자 차례가 아닙니다."}

            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                return {"ok": False, "error": "UCI 형식이 잘못되었습니다. 예: e2e4"}

            if move not in self.board.legal_moves:
                return {"ok": False, "error": "불법수입니다."}

            animation = self._apply_move(move, actor="white")
            self.busy = True
            self.status = "user_robot_moving"
            generation = self.generation
            state = self.snapshot()

        await self.manager.broadcast({"type": "move", "move": self._animation_payload(animation)})
        await self.manager.broadcast(state)
        asyncio.create_task(self._continue_black_turn(generation))
        return {"ok": True, "state": state}

    async def _continue_black_turn(self, generation: int) -> None:
        """사용자 이동 애니메이션 이후 AI 수를 계산하고 로봇 애니메이션을 보낸다."""

        await asyncio.sleep(self.animation_seconds)

        async with self.lock:
            if generation != self.generation:
                return
            if self.board.is_game_over():
                self.busy = False
                self.status = "game_over"
                state = self.snapshot()
                await self.manager.broadcast(state)
                return
            self.status = "ai_thinking"
            fen = self.board.fen()

        await self.manager.broadcast(self.snapshot())
        ai_move = await asyncio.to_thread(self.engine.best_move, fen)

        async with self.lock:
            if generation != self.generation:
                return
            if ai_move is None or self.board.is_game_over():
                self.busy = False
                self.status = "game_over"
                state = self.snapshot()
                await self.manager.broadcast(state)
                return

            animation = self._apply_move(ai_move, actor="black")
            self.status = "ai_robot_moving"
            state = self.snapshot()

        await self.manager.broadcast({"type": "move", "move": self._animation_payload(animation)})
        await self.manager.broadcast(state)
        await asyncio.sleep(self.animation_seconds)

        async with self.lock:
            if generation != self.generation:
                return
            self.busy = False
            self.status = "game_over" if self.board.is_game_over() else "white_turn"
            state = self.snapshot()
        await self.manager.broadcast(state)

    def _apply_move(self, move: chess.Move, actor: str) -> MoveAnimation:
        """현재 보드에 수를 적용하고 3D 애니메이션 데이터를 만든다."""

        piece = self.board.piece_at(move.from_square)
        captured_piece = self.board.piece_at(move.to_square)
        if piece is None:
            raise ValueError(f"출발 칸에 기물이 없습니다: {move.uci()}")

        source = chess.square_name(move.from_square)
        target = chess.square_name(move.to_square)
        self.board.push(move)

        return MoveAnimation(
            uci=move.uci(),
            source=source,
            target=target,
            piece=piece.symbol(),
            captured=captured_piece.symbol() if captured_piece else None,
            actor=actor,
            fen_after=self.board.fen(),
        )

    def _animation_payload(self, animation: MoveAnimation) -> dict[str, Any]:
        """MoveAnimation을 JSON으로 직렬화 가능한 데이터로 변환한다."""

        return {
            "uci": animation.uci,
            "source": animation.source,
            "target": animation.target,
            "piece": animation.piece,
            "captured": animation.captured,
            "actor": animation.actor,
            "fen_after": animation.fen_after,
            "source_xyz": self._square_xyz(animation.source),
            "target_xyz": self._square_xyz(animation.target),
            "duration": self.animation_seconds,
        }

    def _square_xyz(self, square_name: str) -> dict[str, float]:
        """체스 칸 이름을 Board Frame의 3D 중심 좌표로 변환한다."""

        pose = board_square_to_board_pose(
            BoardSquare.from_uci(square_name),
            settings.board,
            z=settings.board.piece_pick_height,
        )
        return {"x": pose.x, "y": pose.y, "z": pose.z}


game = WebChessGame()


@app.get("/")
async def index() -> FileResponse:
    """웹 체스 UI를 반환한다."""

    return FileResponse(PROJECT_ROOT / "web" / "static" / "index.html")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    """현재 체스 게임 상태를 반환한다."""

    return game.snapshot()


@app.post("/api/move")
async def post_move(request: MoveRequest) -> dict[str, Any]:
    """사용자 이동 요청을 처리한다."""

    return await game.submit_user_move(request.uci.lower().strip())


@app.post("/api/reset")
async def reset_game() -> dict[str, Any]:
    """새 게임을 시작한다."""

    return await game.reset()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """보드 상태와 로봇 애니메이션 이벤트를 실시간으로 전송한다."""

    await game.manager.connect(websocket)
    await websocket.send_json(game.snapshot())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        game.manager.disconnect(websocket)
