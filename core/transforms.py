"""좌표계 변환 유틸리티.

Board Frame은 체스판 원점 기준 좌표계이고, Base Frame은 로봇 베이스
중심 기준 좌표계다. 실제 로봇 제어에서는 모든 목표점을 Base Frame으로
변환한 뒤 IK 타겟으로 사용한다.

변환 흐름:
    체스 칸 인덱스 → Board Frame 포즈 → Robot Base Frame 포즈 → IK 계산
"""

from __future__ import annotations

import math

import numpy as np

from config.config import BoardSettings, RobotSettings
from core.models import BoardSquare, Pose3D


def rpy_to_rotation(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Roll/Pitch/Yaw 라디안 값을 3x3 회전 행렬로 변환한다."""

    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)

    rot_x = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    rot_y = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rot_z = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rot_z @ rot_y @ rot_x


def make_transform(translation: tuple[float, float, float], rpy: tuple[float, float, float]) -> np.ndarray:
    """이동 벡터와 RPY 자세로 4x4 동차 변환 행렬을 만든다."""

    transform = np.eye(4)
    transform[:3, :3] = rpy_to_rotation(*rpy)
    transform[:3, 3] = np.array(translation, dtype=float)
    return transform


def board_square_to_board_pose(square: BoardSquare, board: BoardSettings, z: float) -> Pose3D:
    """체스 칸 중심을 Board Frame의 3D 포즈로 변환한다.

    중심 좌표 공식:
        x = x0 + file * L + L / 2
        y = y0 + rank * L + L / 2

    여기서 L은 한 칸의 실제 길이이며, 원점은 설정 파일의
    `origin_in_board_frame`으로 중앙 통제된다.
    """

    x0, y0, _ = board.origin_in_board_frame
    square_size = board.square_size
    return Pose3D(
        x=x0 + square.file * square_size + square_size / 2.0,
        y=y0 + square.rank * square_size + square_size / 2.0,
        z=z,
        roll=math.pi,
        pitch=0.0,
        yaw=0.0,
    )


def board_pose_to_base_pose(pose: Pose3D, robot: RobotSettings) -> Pose3D:
    """Board Frame 포즈를 Robot Base Frame 포즈로 변환한다.

    설정의 `base_to_board_translation`은 Base Frame에서 본 Board Frame의
    위치다. 즉 `T_base_board` 행렬을 구성한 뒤 Board 좌표점을 곱해
    Base 좌표점으로 변환한다.
    """

    t_base_board = make_transform(
        robot.base_to_board_translation,
        robot.base_to_board_rpy,
    )
    point_board = np.array([pose.x, pose.y, pose.z, 1.0])
    point_base = t_base_board @ point_board

    return Pose3D(
        x=float(point_base[0]),
        y=float(point_base[1]),
        z=float(point_base[2]),
        roll=pose.roll,
        pitch=pose.pitch,
        yaw=pose.yaw,
    )
