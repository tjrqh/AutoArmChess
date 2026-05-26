"""시뮬레이터 실행 진입점."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import load_settings
from sim.simulator import ChessRobotSimulator


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""

    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="렌더링 없이 실행")
    mode.add_argument("--gui", action="store_true", help="MuJoCo viewer로 실행")
    parser.add_argument("--steps", type=int, default=2000, help="실행할 시뮬레이션 step 수")
    return parser.parse_args()


def ensure_macos_mjpython_for_gui(args: argparse.Namespace) -> None:
    """macOS GUI 실행 시 MuJoCo 전용 `mjpython`으로 재실행한다.

    MuJoCo viewer는 macOS Cocoa GUI 제약 때문에 일반 `python` 프로세스의
    메인 스레드에서 바로 열 수 없다. `mjpython`은 이 문제를 우회하기 위한
    MuJoCo 제공 런처다. 사용자가 실수로 `python scripts/run_sim.py --gui`를
    입력해도 같은 인자로 `mjpython`을 다시 실행해 GUI가 정상 동작하게 한다.
    """

    if not args.gui or args.headless:
        return
    if platform.system() != "Darwin":
        return
    if os.environ.get("MJPYTHON_BIN"):
        return

    mjpython = Path(sys.executable).with_name("mjpython")
    if not mjpython.exists():
        raise RuntimeError(
            "macOS에서 MuJoCo GUI는 mjpython으로 실행해야 합니다. "
            "`pip install mujoco` 후 `.venv/bin/mjpython scripts/run_sim.py --gui`를 실행하세요."
        )

    os.execv(str(mjpython), [str(mjpython), *sys.argv])


def main() -> None:
    """설정을 로드하고 시뮬레이터를 실행한다."""

    args = parse_args()
    ensure_macos_mjpython_for_gui(args)

    settings = load_settings()
    headless = True
    if args.gui:
        headless = False
    if args.headless:
        headless = True

    simulator = ChessRobotSimulator(settings=settings, headless=headless)
    try:
        simulator.run(max_steps=args.steps)
    finally:
        simulator.close()


if __name__ == "__main__":
    main()
