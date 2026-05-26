"""불변 도메인 모델.

체스 좌표, 3D 포즈, 이동 명령, 로봇 상태는 실행 중 여러 스레드와 
시뮬레이션 루프가 동시에 참조할 수 있다. 따라서 `dataclass(frozen=True)`로
정의해 한 번 생성된 값이 변경되지 않도록 보장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RobotTaskState(str, Enum):
    """전자석 기반 Pick-and-Place 로봇 작업 상태."""

    IDLE = "idle"
    MOVE_ABOVE_SOURCE = "move_above_source"
    DESCEND_TO_PICK = "descend_to_pick"
    MAGNET_ON = "magnet_on"
    LIFT_SOURCE = "lift_source"
    MOVE_ABOVE_TARGET = "move_above_target"
    DESCEND_TO_PLACE = "descend_to_place"
    MAGNET_OFF = "magnet_off"
    RETREAT = "retreat"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class BoardSquare:
    """체스판의 한 칸을 표현하는 불변 좌표.

    Attributes:
        file: 0부터 7까지의 열 인덱스. a 파일이 0, h 파일이 7이다.
        rank: 0부터 7까지의 행 인덱스. 1 랭크가 0, 8 랭크가 7이다.
    """

    file: int
    rank: int

    @classmethod
    def from_uci(cls, square: str) -> "BoardSquare":
        """`e2` 같은 UCI 칸 이름을 BoardSquare로 변환한다."""

        if len(square) != 2:
            raise ValueError(f"잘못된 체스 칸입니다: {square}")

        file_index = ord(square[0].lower()) - ord("a")
        rank_index = int(square[1]) - 1
        if not 0 <= file_index < 8 or not 0 <= rank_index < 8:
            raise ValueError(f"체스판 범위를 벗어났습니다: {square}")

        return cls(file=file_index, rank=rank_index)

    def to_uci(self) -> str:
        """BoardSquare를 `e2` 같은 UCI 칸 이름으로 변환한다."""

        return f"{chr(ord('a') + self.file)}{self.rank + 1}"


@dataclass(frozen=True, slots=True)
class Pose3D:
    """3D 위치와 자세를 담는 불변 포즈.

    roll/pitch/yaw는 라디안 단위이며, 단순 Pick-and-Place에서는 보통
    엔드 이펙터가 수직 아래를 향하도록 고정된 자세를 사용한다.
    """

    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def with_z(self, z: float) -> "Pose3D":
        """같은 x/y/자세를 유지하고 z 높이만 바꾼 새 포즈를 반환한다."""

        return Pose3D(
            x=self.x,
            y=self.y,
            z=z,
            roll=self.roll,
            pitch=self.pitch,
            yaw=self.yaw,
        )


@dataclass(frozen=True, slots=True)
class ChessMoveCommand:
    """체스 이동과 로봇 목표를 연결하는 불변 명령 객체."""

    uci: str
    source: BoardSquare
    target: BoardSquare
    promotion: str | None = None

    @classmethod
    def from_uci(cls, uci: str) -> "ChessMoveCommand":
        """UCI 이동 문자열을 로봇 명령으로 변환한다."""

        if len(uci) not in (4, 5):
            raise ValueError(f"잘못된 UCI 이동입니다: {uci}")

        return cls(
            uci=uci,
            source=BoardSquare.from_uci(uci[:2]),
            target=BoardSquare.from_uci(uci[2:4]),
            promotion=uci[4] if len(uci) == 5 else None,
        )


@dataclass(frozen=True, slots=True)
class JointTrajectoryPoint:
    """한 시점의 관절 목표값."""

    time_from_start: float
    positions: tuple[float, ...]
    velocities: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RobotCommandFrame:
    """시뮬레이터에 전달되는 한 프레임의 로봇 제어 명령."""

    state: RobotTaskState
    target_pose: Pose3D
    joint_targets: tuple[float, ...]
    magnet_enabled: bool

