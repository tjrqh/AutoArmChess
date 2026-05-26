"""전자석 Pick-and-Place 로봇 컨트롤러."""

from __future__ import annotations

from collections.abc import Iterable

import mujoco
import numpy as np

from config.config import Settings
from core.models import ChessMoveCommand, Pose3D, RobotCommandFrame, RobotTaskState
from core.transforms import board_pose_to_base_pose, board_square_to_board_pose
from sim.trajectory import QuinticTrajectory


class RobotController:
    """체스 말을 옮기는 로봇 제어 FSM.

    데이터 흐름:
        1. ChessMoveCommand가 들어온다.
        2. source/target 체스 칸을 Board Frame 중심 좌표로 변환한다.
        3. Board Frame 좌표를 Robot Base Frame 좌표로 변환한다.
        4. 각 waypoint마다 MuJoCo IK를 계산한다.
        5. Quintic 궤적으로 부드러운 관절 목표 프레임을 생성한다.

    전자석은 실제 접촉 물리를 복잡하게 계산하지 않고, 자석 ON 시점부터
    대상 body의 mocap/pose를 엔드 이펙터에 종속시키는 방식으로 확장할 수 있다.
    """

    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData, settings: Settings) -> None:
        self.model = model
        self.data = data
        self.settings = settings
        self.state = RobotTaskState.IDLE
        self.magnet_enabled = False
        self._trajectory = QuinticTrajectory(
            duration=settings.trajectory.duration,
            sample_hz=settings.trajectory.sample_hz,
        )
        self._joint_ids = self._resolve_joint_ids(settings.robot.joint_names)
        self._actuator_ids = self._resolve_actuator_ids(settings.robot.joint_names)
        self._frame_queue: list[RobotCommandFrame] = []

    def plan_move(self, command: ChessMoveCommand) -> None:
        """체스 이동 명령을 FSM waypoint와 관절 궤적으로 변환한다."""

        pick_pose = self._square_pose(command.source, self.settings.board.piece_pick_height)
        place_pose = self._square_pose(command.target, self.settings.board.piece_pick_height)
        hover_pick = pick_pose.with_z(self.settings.board.piece_hover_height)
        hover_place = place_pose.with_z(self.settings.board.piece_hover_height)

        waypoints = [
            (RobotTaskState.MOVE_ABOVE_SOURCE, hover_pick, False),
            (RobotTaskState.DESCEND_TO_PICK, pick_pose, False),
            (RobotTaskState.MAGNET_ON, pick_pose, True),
            (RobotTaskState.LIFT_SOURCE, hover_pick, True),
            (RobotTaskState.MOVE_ABOVE_TARGET, hover_place, True),
            (RobotTaskState.DESCEND_TO_PLACE, place_pose, True),
            (RobotTaskState.MAGNET_OFF, place_pose, False),
            (RobotTaskState.RETREAT, hover_place, False),
        ]

        current_joints = self.current_joint_positions()
        frames: list[RobotCommandFrame] = []
        for state, pose, magnet in waypoints:
            goal_joints = self.solve_ik(pose, current_joints)
            self._raise_if_singular()
            trajectory = self._trajectory.generate(current_joints, goal_joints)

            for point in trajectory:
                frames.append(
                    RobotCommandFrame(
                        state=state,
                        target_pose=pose,
                        joint_targets=point.positions,
                        magnet_enabled=magnet,
                    )
                )
            current_joints = goal_joints

        self._frame_queue = frames
        self.state = RobotTaskState.MOVE_ABOVE_SOURCE

    def step(self) -> RobotTaskState:
        """시뮬레이션 한 프레임에 해당하는 로봇 명령을 적용한다."""

        if not self._frame_queue:
            if self.state not in (RobotTaskState.IDLE, RobotTaskState.ERROR):
                self.state = RobotTaskState.COMPLETE
            return self.state

        frame = self._frame_queue.pop(0)
        self.state = frame.state
        self.magnet_enabled = frame.magnet_enabled
        self._apply_joint_targets(frame.joint_targets)
        return self.state

    def current_joint_positions(self) -> tuple[float, ...]:
        """현재 MuJoCo qpos에서 제어 대상 관절 위치를 읽는다."""

        positions = []
        for joint_id in self._joint_ids:
            qpos_index = self.model.jnt_qposadr[joint_id]
            positions.append(float(self.data.qpos[qpos_index]))
        return tuple(positions)

    def solve_ik(
        self,
        target: Pose3D,
        seed: tuple[float, ...],
        max_iters: int = 80,
        tolerance: float = 1e-4,
    ) -> tuple[float, ...]:
        """MuJoCo Jacobian 기반 Damped Least Squares IK를 계산한다.

        특이점 근처에서는 Jacobian의 조건이 나빠져 관절 속도가 폭주할 수 있다.
        여기서는 damping 항을 넣어 역행렬을 안정화하고, 별도 특이점 검사를 통해
        너무 위험한 자세는 상위 FSM에서 에러 처리할 수 있게 한다.
        """

        q = np.array(seed, dtype=float)
        site_id = mujoco.mj_name2id(
            self.model,
            mujoco.mjtObj.mjOBJ_SITE,
            self.settings.robot.end_effector_site,
        )
        if site_id < 0:
            raise ValueError(f"엔드 이펙터 site를 찾을 수 없습니다: {self.settings.robot.end_effector_site}")

        target_pos = np.array([target.x, target.y, target.z], dtype=float)
        damping = 1e-3

        for _ in range(max_iters):
            self._set_joint_positions(q)
            mujoco.mj_forward(self.model, self.data)

            current_pos = self.data.site_xpos[site_id].copy()
            error = target_pos - current_pos
            if np.linalg.norm(error) < tolerance:
                return tuple(float(v) for v in q)

            jac_pos = np.zeros((3, self.model.nv))
            jac_rot = np.zeros((3, self.model.nv))
            mujoco.mj_jacSite(self.model, self.data, jac_pos, jac_rot, site_id)
            controlled_jac = jac_pos[:, [self.model.jnt_dofadr[j] for j in self._joint_ids]]

            lhs = controlled_jac @ controlled_jac.T + damping * np.eye(3)
            delta_q = controlled_jac.T @ np.linalg.solve(lhs, error)
            delta_q = np.clip(
                delta_q,
                -self.settings.robot.joint_velocity_limit * self.model.opt.timestep,
                self.settings.robot.joint_velocity_limit * self.model.opt.timestep,
            )
            q = q + delta_q

        return tuple(float(v) for v in q)

    def _square_pose(self, square, z: float) -> Pose3D:
        """체스 칸을 로봇 베이스 좌표계 포즈로 변환한다."""

        board_pose = board_square_to_board_pose(square, self.settings.board, z)
        return board_pose_to_base_pose(board_pose, self.settings.robot)

    def _raise_if_singular(self) -> None:
        """Jacobian determinant 기반의 간단한 특이점 회피 검사.
        
        Manipulability가 설정된 임계값 이하면 특이점에 가까운 자세로 판정하고
        로봇 상태를 ERROR로 변경한다.
        """

        site_id = mujoco.mj_name2id(
            self.model,
            mujoco.mjtObj.mjOBJ_SITE,
            self.settings.robot.end_effector_site,
        )
        jac_pos = np.zeros((3, self.model.nv))
        jac_rot = np.zeros((3, self.model.nv))
        mujoco.mj_jacSite(self.model, self.data, jac_pos, jac_rot, site_id)
        controlled_jac = jac_pos[:, [self.model.jnt_dofadr[j] for j in self._joint_ids]]
        manipulability = np.linalg.det(controlled_jac @ controlled_jac.T)

        if (
            self.settings.robot.singularity_min_det > 0.0
            and manipulability < self.settings.robot.singularity_min_det
        ):
            self.state = RobotTaskState.ERROR
            raise RuntimeError("특이점에 가까운 자세가 감지되었습니다.")

    def _resolve_joint_ids(self, joint_names: Iterable[str]) -> tuple[int, ...]:
        """설정에 적힌 관절 이름을 MuJoCo joint id로 해석한다."""

        ids = []
        for name in joint_names:
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint_id < 0:
                raise ValueError(f"joint를 찾을 수 없습니다: {name}")
            ids.append(joint_id)
        return tuple(ids)

    def _resolve_actuator_ids(self, joint_names: Iterable[str]) -> tuple[int, ...]:
        """관절 이름과 같은 이름의 actuator id를 해석한다."""

        ids = []
        for name in joint_names:
            actuator_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            if actuator_id < 0:
                raise ValueError(f"actuator를 찾을 수 없습니다: {name}")
            ids.append(actuator_id)
        return tuple(ids)

    def _set_joint_positions(self, positions: np.ndarray) -> None:
        """IK 반복 중 임시 qpos를 설정한다."""

        for joint_id, value in zip(self._joint_ids, positions, strict=True):
            qpos_index = self.model.jnt_qposadr[joint_id]
            self.data.qpos[qpos_index] = value

    def _apply_joint_targets(self, positions: tuple[float, ...]) -> None:
        """actuator control 입력으로 목표 관절 위치를 전달한다."""

        for actuator_id, value in zip(self._actuator_ids, positions, strict=True):
            self.data.ctrl[actuator_id] = value
