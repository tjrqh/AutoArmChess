"""Quintic Polynomial 기반 궤적 생성기."""

from __future__ import annotations

import numpy as np

from core.models import JointTrajectoryPoint


class QuinticTrajectory:
    """정지-출발/정지-도착 조건을 만족하는 부드러운 관절 궤적 생성기.

    s(t) = 10t^3 - 15t^4 + 6t^5 형태의 quintic time-scaling을 사용한다.
    시작과 끝에서 속도/가속도가 0이므로 모터 급발진과 급정지를 줄일 수 있다.
    """

    def __init__(self, duration: float, sample_hz: int) -> None:
        self.duration = duration
        self.sample_hz = sample_hz

    def generate(
        self,
        start: tuple[float, ...],
        goal: tuple[float, ...],
    ) -> list[JointTrajectoryPoint]:
        """시작 관절각에서 목표 관절각까지의 샘플 궤적을 생성한다."""

        start_array = np.array(start, dtype=float)
        goal_array = np.array(goal, dtype=float)
        delta = goal_array - start_array
        steps = max(2, int(self.duration * self.sample_hz))

        points: list[JointTrajectoryPoint] = []
        for index in range(steps + 1):
            time_from_start = self.duration * index / steps
            tau = time_from_start / self.duration
            scale = 10 * tau**3 - 15 * tau**4 + 6 * tau**5
            scale_dot = (30 * tau**2 - 60 * tau**3 + 30 * tau**4) / self.duration

            positions = start_array + scale * delta
            velocities = scale_dot * delta
            points.append(
                JointTrajectoryPoint(
                    time_from_start=time_from_start,
                    positions=tuple(float(v) for v in positions),
                    velocities=tuple(float(v) for v in velocities),
                )
            )

        return points

