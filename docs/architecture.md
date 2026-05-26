# 아키텍처 설계 요약

## 1. 디렉토리 구조

```text
config/
  config.py        중앙 설정 로더. YAML과 환경 변수를 Settings 객체로 변환한다.
  settings.yaml    보드 크기, 좌표 오프셋, 제어 주기, AI 깊이 등 실행 파라미터.

core/
  models.py        dataclass(frozen=True) 기반 불변 도메인 모델.
  pieces.py        체스 기물 정의 및 메타데이터 (가치, 한글명 등).
  transforms.py    Board Frame과 Robot Base Frame 사이의 좌표 변환.

ai/
  minimax.py       python-chess 기반 Minimax + Alpha-Beta AI. 별도 스레드에서 실행 가능.

sim/
  trajectory.py        Quintic Polynomial 궤적 생성.
  robot_controller.py  전자석 Pick-and-Place FSM, IK, 특이점 검사.
  simulator.py         Headless/GUI MuJoCo 루프, AI 작업 소비, 로봇 제어 통합.

assets/mujoco/
  chess_robot.xml  8x8 체스판, 단순 충돌 원기둥 기물, 6축 로봇팔 예시 MJCF.

scripts/
  run_sim.py       CLI 실행 진입점.
  play_cli.py      터미널 기반 게임 루프 검증.

web/
  app.py           FastAPI + WebSocket 웹 서버.
  static/          2D 보드 + Three.js 3D 애니메이션 프론트엔드.
```

## 2. 핵심 데이터 흐름

```
체스 이동 (사용자 또는 AI)
  ↓
ChessMoveCommand 불변 객체 생성
  ↓
RobotController.plan_move()
  → 출발/도착 칸 → Board Frame 포즈
  → Board Frame → Robot Base Frame 포즈
  → IK 계산 (각 waypoint마다)
  → Quintic 궤적 생성
  → FSM 상태 프레임 큐 생성
  ↓
매 시뮬레이션 step마다 RobotController.step()
  → FSM 상태 진행
  → 관절 목표값 MuJoCo에 전달
  ↓
MuJoCo 물리 시뮬레이션 (mj_step)
  → 충돌, 동역학 계산
  → 엔드 이펙터 위치 업데이트
```

AI 흐름 (비동기):

```
RobotController가 IDLE 상태
  ↓
SimulatorChessRobotSimulator._maybe_start_ai_job()
  → MinimaxEngine.best_move_async(fen)
  → 별도 스레드에서 최선 수 계산
  ↓
메인 루프는 계속 mj_step() 실행 (AI 계산과 병렬)
  ↓
AI Future done 확인 (동기화)
  → best_move() 결과 추출
  → 로봇 이동 명령 생성
```

## 3. Headless와 GUI 분리

`simulator.py`는 동일한 물리/AI/제어 로직을 사용하지만 실행 루프만 분리한다.

### Headless 모드
- viewer 생성 없이 `mj_step()`만 수행
- 최대한 빠름 (렌더링 오버헤드 없음)
- 대량 학습, 시뮬레이션 통계 수집에 적합
- 서버 환경에서 사용

### GUI 모드
- `mujoco.viewer.launch_passive()`로 렌더링 붙임
- 로봇 자세, 충돌, 궤적을 시각적으로 디버깅
- 데모 및 검증에 적합
- macOS에서는 자동으로 `mjpython` 재실행

## 4. 좌표계 변환

### Board Frame
- 체스판 원점 기준
- 설정: `board.origin_in_board_frame` (보통 [-0.24, -0.24, 0.02])
- 칸 중심 좌표: `x = x0 + file * L + L/2`, `y = y0 + rank * L + L/2`

### Robot Base Frame
- 로봇 베이스 중심 기준
- 설정: `robot.base_to_board_translation`, `robot.base_to_board_rpy`
- 변환 행렬: `T_base_board = [R | t; 0 0 0 1]`
- 변환 공식: `p_base = T_base_board @ p_board`

## 5. 로봇 제어 FSM

Pick-and-Place 이동의 8단계:

```
MOVE_ABOVE_SOURCE    체스 수 높이보다 위에서 출발 칸 상공 이동
    ↓
DESCEND_TO_PICK      픽 가능 높이로 하강
    ↓
MAGNET_ON            전자석 활성화
    ↓
LIFT_SOURCE          기물을 들어올림 (상공 높이로 상승)
    ↓
MOVE_ABOVE_TARGET    목표 칸 상공으로 이동
    ↓
DESCEND_TO_PLACE     픽 가능 높이로 하강
    ↓
MAGNET_OFF           전자석 비활성화
    ↓
RETREAT              최종 위치로 복귀
    ↓
COMPLETE             작업 완료
```

## 6. 특이점 회피

현재 보일러플레이트는 Jacobian의 `det(JJ^T)`가 설정값보다 낮으면 특이점 근처로 판단한다.

```python
manipulability = det(J @ J^T)
if manipulability < singularity_min_det:
    raise RuntimeError("특이점 근처")
```

**데모 MJCF**: 단순 기구 구조이므로 기본값을 `0.0`으로 두어 fatal stop 비활성화

**실제 로봇 모델 적용 시**:
- `settings.yaml`의 `singularity_min_det`를 양수로 설정
- 여러 elbow-up/elbow-down seed 후보 테스트
- joint limit margin cost 추가
- manipulability maximization
- 충돌 거리 기반 waypoint 재계획

## 7. AI 알고리즘

### Minimax 기본
```
minimax(depth, maximizing):
    if depth == 0 or game_over:
        return evaluate(board)
    
    if maximizing:
        value = -∞
        for each move:
            value = max(value, minimax(depth-1, false))
    else:
        value = +∞
        for each move:
            value = min(value, minimax(depth-1, true))
    return value
```

### Alpha-Beta Pruning
```
minimax(depth, alpha, beta, maximizing):
    if depth == 0 or game_over:
        return evaluate(board)
    
    if maximizing:
        value = -∞
        for each move:
            value = max(value, minimax(..., alpha, beta, false))
            alpha = max(alpha, value)
            if alpha >= beta: break  # β-cutoff
    else:
        value = +∞
        for each move:
            value = min(value, minimax(..., alpha, beta, true))
            beta = min(beta, value)
            if alpha >= beta: break  # α-cutoff
    return value
```

### 이동 정렬 (Move Ordering)
효율적인 가지치기를 위해 이동을 우선 순위 순으로 정렬:
1. 캡처 수 (상대 기물 잡기)
2. 체크 수
3. 일반 수

이를 통해 가장 중요한 변동성이 높은 수부터 탐색하여 가지치기 기회 증가.

## 8. 기물 가치 (Material Values)

단위: centipawn (cp) = 1/100 pawn

```
Pawn   = 100 cp
Knight = 320 cp
Bishop = 330 cp
Rook   = 500 cp
Queen  = 900 cp
King   = 0 cp (특수)
```

평가 함수: `score = Σ(white_pieces * value) - Σ(black_pieces * value)`

긍정값 = 백 유리, 부정값 = 흑 유리, 0 = 동등

## 9. 웹 인터페이스 아키텍처

```
Client (Browser)
  ├─ 2D Chess Board UI (HTML canvas 또는 SVG)
  ├─ Three.js 3D Robot Visualization
  └─ WebSocket 통신

Server (FastAPI)
  ├─ HTTP GET /          → index.html
  ├─ HTTP GET /api/state → 현재 게임 상태 (JSON)
  ├─ HTTP POST /api/move → 사용자 이동 처리
  ├─ HTTP POST /api/reset → 게임 초기화
  └─ WebSocket /ws       → 실시간 이동 및 애니메이션 이벤트 스트림
```

WebSocket 메시지 형식:
```json
{
  "type": "move",
  "move": {
    "uci": "e2e4",
    "source": "e2",
    "target": "e4",
    "piece": "P",
    "captured": null,
    "actor": "white",
    "fen_after": "...",
    "source_xyz": {"x": ..., "y": ..., "z": ...},
    "target_xyz": {"x": ..., "y": ..., "z": ...},
    "duration": 2.8
  }
}
```

