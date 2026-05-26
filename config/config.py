"""중앙 설정 로더.

이 모듈은 YAML 설정 파일과 환경 변수를 합쳐 프로젝트 전체에서
동일한 설정 객체를 사용하도록 만든다. 시뮬레이터, AI, 로봇 제어기는
직접 하드코딩된 값을 갖지 않고 Settings 객체를 주입받는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SimulationSettings:
    """MuJoCo 실행 관련 설정."""

    model_path: Path
    timestep: float
    control_hz: int
    headless: bool


@dataclass(frozen=True)
class BoardSettings:
    """체스판 좌표계와 기물 접근 높이 설정."""

    square_size: float
    origin_in_board_frame: tuple[float, float, float]
    piece_hover_height: float
    piece_pick_height: float


@dataclass(frozen=True)
class RobotSettings:
    """로봇 좌표계, 관절, 특이점 회피 관련 설정."""

    base_to_board_translation: tuple[float, float, float]
    base_to_board_rpy: tuple[float, float, float]
    end_effector_site: str
    joint_names: tuple[str, ...]
    singularity_min_det: float
    joint_velocity_limit: float


@dataclass(frozen=True)
class TrajectorySettings:
    """S-Curve/Quintic 궤적 생성 설정."""

    duration: float
    sample_hz: int
    approach_duration: float
    lift_duration: float


@dataclass(frozen=True)
class AISettings:
    """체스 AI 탐색 깊이 설정."""

    depth: int


@dataclass(frozen=True)
class Settings:
    """시스템 전체 설정 루트 객체."""

    simulation: SimulationSettings
    board: BoardSettings
    robot: RobotSettings
    trajectory: TrajectorySettings
    ai: AISettings


def _tuple3(value: list[float]) -> tuple[float, float, float]:
    """YAML 배열을 3D 벡터 튜플로 변환한다."""

    if len(value) != 3:
        raise ValueError(f"3개 원소가 필요합니다: {value}")
    return (float(value[0]), float(value[1]), float(value[2]))


def load_settings(path: Path | None = None) -> Settings:
    """설정 파일을 읽고 환경 변수 오버라이드를 적용한다.

    환경 변수 `CHESS_AI_DEPTH`가 있으면 YAML의 AI 탐색 깊이보다
    우선 적용된다. 학습/실험 시 탐색 깊이를 코드 수정 없이 바꾸기 위함이다.
    """

    config_path = path or PROJECT_ROOT / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as file:
        raw: dict[str, Any] = yaml.safe_load(file)

    ai_depth = int(os.getenv("CHESS_AI_DEPTH", raw["ai"]["depth"]))
    model_path = PROJECT_ROOT / raw["simulation"]["model_path"]

    return Settings(
        simulation=SimulationSettings(
            model_path=model_path,
            timestep=float(raw["simulation"]["timestep"]),
            control_hz=int(raw["simulation"]["control_hz"]),
            headless=bool(raw["simulation"]["headless"]),
        ),
        board=BoardSettings(
            square_size=float(raw["board"]["square_size"]),
            origin_in_board_frame=_tuple3(raw["board"]["origin_in_board_frame"]),
            piece_hover_height=float(raw["board"]["piece_hover_height"]),
            piece_pick_height=float(raw["board"]["piece_pick_height"]),
        ),
        robot=RobotSettings(
            base_to_board_translation=_tuple3(raw["robot"]["base_to_board_translation"]),
            base_to_board_rpy=_tuple3(raw["robot"]["base_to_board_rpy"]),
            end_effector_site=str(raw["robot"]["end_effector_site"]),
            joint_names=tuple(raw["robot"]["joint_names"]),
            singularity_min_det=float(raw["robot"]["singularity_min_det"]),
            joint_velocity_limit=float(raw["robot"]["joint_velocity_limit"]),
        ),
        trajectory=TrajectorySettings(
            duration=float(raw["trajectory"]["duration"]),
            sample_hz=int(raw["trajectory"]["sample_hz"]),
            approach_duration=float(raw["trajectory"]["approach_duration"]),
            lift_duration=float(raw["trajectory"]["lift_duration"]),
        ),
        ai=AISettings(depth=ai_depth),
    )

