# AI Chess Robot Arm 3D Simulation

Python 기반 AI 체스 로봇팔 3D 시뮬레이션 프로젝트입니다.

## 개요

이 프로젝트는 다음을 통합합니다:

- **체스 AI**: Minimax + Alpha-Beta Pruning으로 최선 수 계산
- **로봇 제어**: IK(역운동학) 및 Quintic 궤적 계획  
- **물리 시뮬레이션**: MuJoCo 기반 체스판과 로봇팔 시뮬레이션
- **웹 인터페이스**: 2D 체스판 입력 + Three.js 3D 로봇팔 애니메이션

## 프로젝트 구조

```text
ai-chess-robot-sim/
├── ai/                     # 체스 AI 의사결정 엔진 (Minimax + Alpha-Beta)
├── assets/mujoco/          # MuJoCo XML 로봇팔 및 체스판 모델
├── config/                 # 중앙 설정 관리 (설정 파일 및 Settings 클래스)
├── core/                   # 불변 데이터 모델 및 변환 유틸리티
│   ├── models.py           # 불변 도메인 모델 (BoardSquare, Pose3D, ChessMoveCommand 등)
│   ├── pieces.py           # 체스 기물 정의 및 메타데이터
│   └── transforms.py       # 좌표계 변환 (Board Frame ↔ Base Frame)
├── scripts/                # 실행 진입점
│   ├── run_sim.py          # 시뮬레이터 메인 런처
│   └── play_cli.py         # 터미널 기반 게임 루프 검증
├── sim/                    # MuJoCo 시뮬레이터 및 로봇 제어기
│   ├── simulator.py        # 게임, AI, 로봇, 물리 통합 루프
│   ├── robot_controller.py # Pick-and-Place 로봇 FSM 제어
│   └── trajectory.py       # Quintic 궤적 생성기
├── web/                    # 웹 인터페이스 (FastAPI)
│   ├── app.py              # WebSocket 기반 실시간 게임 상태 전송
│   └── static/             # 2D 보드 + 3D 애니메이션 프론트엔드
├── tests/                  # 단위 테스트
├── config/settings.yaml    # 로봇팔, 체스판, AI 파라미터 설정
└── requirements.txt        # Python 의존성
```

## 실행

### 1단계: 환경 설정

의존성 설치:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2단계: 실행 모드 선택

#### Headless 모드 (렌더링 없음, 가장 빠름)

```bash
python scripts/run_sim.py --headless
```

#### GUI 모드 (MuJoCo viewer 포함)

```bash
python scripts/run_sim.py --gui
```

macOS에서는 MuJoCo GUI가 `mjpython`을 요구합니다. `run_sim.py`는 이를 자동으로 처리합니다.

#### CLI 게임 루프 검증

터미널에서 직접 체스를 두며 게임 로직을 빠르게 검증할 수 있습니다:

```bash
python scripts/play_cli.py
```

예시:
```text
White move> e2e4
AI(Black): e7e5
White move> g1f3
AI(Black): b8c6
White move> quit
```

#### 웹 인터페이스

브라우저에서 2D 입력 + 3D 로봇팔 애니메이션을 함께 확인:

```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
```

브라우저: http://127.0.0.1:8000

### AI 탐색 깊이 조절

AI의 탐색 깊이를 환경 변수로 조절할 수 있습니다:

```bash
CHESS_AI_DEPTH=3 python scripts/run_sim.py --headless
```

기본값은 `config/settings.yaml`의 `ai.depth`입니다.

## 기술 상세

### 좌표계 변환

- **Board Frame**: 체스판 원점 기준 좌표계
- **Base Frame**: 로봇 베이스 중심 좌표계
- 모든 목표점은 Board Frame에서 Base Frame으로 변환되어 IK 계산에 사용됩니다.

### 로봇 제어

1. **이동 계획**: 체스 수 → 4개 waypoint (위에서 픽, 픽 가능한 높이, 픽, 내려놓기)
2. **IK 계산**: MuJoCo Jacobian 기반 Damped Least Squares IK
3. **궤적 생성**: Quintic polynomial으로 부드러운 조인트 움직임
4. **전자석 제어**: 특정 상태에서 자석 ON/OFF

### AI 알고리즘

- **Minimax**: 재귀적 게임 트리 탐색
- **Alpha-Beta Pruning**: 비효율적인 가지 제거로 탐색 효율화
- **비동기 실행**: 별도 스레드에서 AI 계산하여 시뮬레이션 FPS 유지
- **이동 정렬**: 캡처 및 체크 수를 먼저 탐색하여 가지치기 효율 향상

## 주요 클래스

### `RobotController`
로봇의 Pick-and-Place 작업을 FSM으로 관리합니다.
```python
controller = RobotController(mujoco_model, mujoco_data, settings)
controller.plan_move(chess_move_command)  # 이동 계획
controller.step()  # 매 프레임 실행
```

### `MinimaxEngine`
비동기 AI 엔진입니다.
```python
ai = MinimaxEngine(depth=3)
future = ai.best_move_async(fen_string)  # 백그라운드 계산
best_move = future.result()  # 결과 대기
```

### `ChessRobotSimulator`
게임, AI, 로봇, 물리를 통합 관리합니다.
```python
sim = ChessRobotSimulator(settings)
sim.apply_user_move("e2e4")  # 사용자 이동
sim.step()  # 한 시뮬레이션 단계 실행
```

## 테스트

```bash
pytest tests/
```

## 라이선스

MIT License

## 참고 자료

- [MuJoCo 문서](https://mujoco.org/)
- [python-chess](https://python-chess.readthedocs.io/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Three.js](https://threejs.org/)

# AutoArmChess
# AutoArmChess
