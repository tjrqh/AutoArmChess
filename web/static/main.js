import * as THREE from "https://unpkg.com/three@0.160.0/build/three.module.js";

const PIECES = {
  P: "♙", N: "♘", B: "♗", R: "♖", Q: "♕", K: "♔",
  p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
};

const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#status");
const selectedLabel = document.querySelector("#selectedLabel");
const lastMoveLabel = document.querySelector("#lastMoveLabel");
const resetBtn = document.querySelector("#resetBtn");

let state = null;
let selected = null;
let legalTargets = new Set();
let busy = false;
let boardPieces = {};
let ws = null;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1f26);

const topCanvas = document.querySelector("#sceneTop");
const armCanvas = document.querySelector("#sceneArm");
const topRenderer = new THREE.WebGLRenderer({ canvas: topCanvas, antialias: true });
const armRenderer = new THREE.WebGLRenderer({ canvas: armCanvas, antialias: true });
topRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
armRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

// 같은 3D 씬을 두 카메라로 렌더링한다.
// 위쪽 뷰는 보드/말 위치 확인용, 아래쪽 뷰는 관절 움직임 관찰용이다.
const topCamera = new THREE.PerspectiveCamera(54, 1, 0.01, 20);
topCamera.position.set(0.0, 0.0, 0.78);
topCamera.lookAt(0.0, 0.0, 0.02);

const armCamera = new THREE.PerspectiveCamera(42, 1, 0.01, 20);
armCamera.position.set(-0.72, 0.04, 0.52);
armCamera.lookAt(0.02, 0.04, 0.06);

// 조명
const ambient = new THREE.AmbientLight(0xffffff, 0.7);
scene.add(ambient);

const topLight = new THREE.DirectionalLight(0xffffff, 1.0);
topLight.position.set(0.2, 0.3, 1.0);
scene.add(topLight);

const sideLight = new THREE.DirectionalLight(0xbfd9ff, 0.75);
sideLight.position.set(-0.7, -0.6, 0.6);
scene.add(sideLight);

const boardGroup = new THREE.Group();
const pieceGroup = new THREE.Group();
const robotGroup = new THREE.Group();
scene.add(boardGroup, pieceGroup, robotGroup);

const squareSize = 0.06;
const boardOrigin = { x: -0.24, y: -0.24, z: 0.02 };
const hoverZ = 0.15;
const pickZ = 0.055;
const robotBase = new THREE.Vector3(0.0, 0.36, 0.04);
const robotRestGripper = new THREE.Vector3(0.0, 0.22, 0.22);
const pieceMeshes = new Map();
const animationQueue = [];
let activeAnimation = null;
let filteredGripper = robotRestGripper.clone();

const robot = createRobot();
robotGroup.add(robot.base, robot.arm);

buildBoard3d();
buildRobotInspectionGuides();
initWebSocket();
loadState();
animate();

resetBtn.addEventListener("click", async () => {
  animationQueue.length = 0;
  activeAnimation = null;
  const response = await fetch("/api/reset", { method: "POST" });
  applyState(await response.json());
});

window.addEventListener("resize", resizeRenderers);
window.addEventListener("resize", resizeBoard2d);

function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  ws.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "state") {
      applyState(payload);
    }
    if (payload.type === "move") {
      enqueueMove(payload.move);
    }
  });

  ws.addEventListener("close", () => {
    statusEl.textContent = "연결 끊김. 새로고침하세요.";
  });
}

async function loadState() {
  const response = await fetch("/api/state");
  applyState(await response.json());
}

function resizeBoard2d() {
  const panelRect = boardEl.parentElement.getBoundingClientRect();
  const reservedHeight = 132;
  const availableWidth = Math.max(280, panelRect.width - 24);
  const availableHeight = Math.max(280, panelRect.height - reservedHeight);
  const rawSize = Math.min(availableWidth, availableHeight, 656);
  const boardSize = Math.max(280, Math.floor(rawSize / 8) * 8);
  boardEl.style.setProperty("--board-size", `${boardSize}px`);
}

function applyState(nextState) {
  state = nextState;
  busy = state.status !== "white_turn";
  boardPieces = parseFenPieces(state.fen);
  resizeBoard2d();
  renderBoard2d();
  if (!activeAnimation && animationQueue.length === 0) {
    syncPieces3d(boardPieces);
  }
  statusEl.textContent = statusText(state);
}

function statusText(current) {
  if (current.game_over) {
    return `게임 종료: ${current.result}`;
  }
  const labels = {
    white_turn: "White 차례입니다. 2D 보드에서 말을 선택하세요.",
    user_robot_moving: "사용자 수를 3D 로봇팔이 재생 중입니다.",
    ai_thinking: "AI가 다음 수를 계산 중입니다.",
    ai_robot_moving: "AI 수를 3D 로봇팔이 재생 중입니다.",
  };
  return labels[current.status] ?? current.status;
}

function renderBoard2d() {
  boardEl.innerHTML = "";
  legalTargets = new Set();
  if (selected && state) {
    for (const move of state.legal_moves) {
      if (move.slice(0, 2) === selected) {
        legalTargets.add(move.slice(2, 4));
      }
    }
  }

  for (let rank = 7; rank >= 0; rank -= 1) {
    for (let file = 0; file < 8; file += 1) {
      const square = `${String.fromCharCode(97 + file)}${rank + 1}`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `square ${(file + rank) % 2 === 0 ? "dark" : "light"}`;
      if (selected === square) button.classList.add("selected");
      if (legalTargets.has(square)) button.classList.add("legal");
      if (busy) button.classList.add("busy");
      button.dataset.square = square;
      const piece = boardPieces[square];
      const pieceSpan = document.createElement("span");
      pieceSpan.className = `piece ${piece && piece === piece.toUpperCase() ? "white-piece" : "black-piece"}`;
      pieceSpan.textContent = PIECES[piece] ?? "";
      button.appendChild(pieceSpan);

      if (file === 0) {
        const rankLabel = document.createElement("span");
        rankLabel.className = "coord rank-label";
        rankLabel.textContent = String(rank + 1);
        button.appendChild(rankLabel);
      }
      if (rank === 0) {
        const fileLabel = document.createElement("span");
        fileLabel.className = "coord file-label";
        fileLabel.textContent = String.fromCharCode(97 + file);
        button.appendChild(fileLabel);
      }
      button.addEventListener("click", () => onSquareClick(square));
      boardEl.appendChild(button);
    }
  }
}

async function onSquareClick(square) {
  if (!state || busy || state.game_over) return;

  if (!selected) {
    const piece = boardPieces[square];
    if (!piece || piece !== piece.toUpperCase()) return;
    selected = square;
    selectedLabel.textContent = `선택: ${square}`;
    renderBoard2d();
    return;
  }

  if (selected === square) {
    selected = null;
    selectedLabel.textContent = "선택 없음";
    renderBoard2d();
    return;
  }

  const move = `${selected}${square}`;
  const promotionMove = `${move}q`;
  const legalMove = state.legal_moves.includes(move)
    ? move
    : state.legal_moves.includes(promotionMove)
      ? promotionMove
      : null;

  if (!legalMove) {
    const piece = boardPieces[square];
    selected = piece && piece === piece.toUpperCase() ? square : null;
    selectedLabel.textContent = selected ? `선택: ${selected}` : "선택 없음";
    renderBoard2d();
    return;
  }

  selected = null;
  selectedLabel.textContent = "선택 없음";
  const response = await fetch("/api/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uci: legalMove }),
  });
  const result = await response.json();
  if (!result.ok) {
    statusEl.textContent = result.error;
  }
}

function parseFenPieces(fen) {
  const placement = fen.split(" ")[0];
  const result = {};
  const ranks = placement.split("/");
  for (let rankIndex = 0; rankIndex < ranks.length; rankIndex += 1) {
    let file = 0;
    const rank = 8 - rankIndex;
    for (const char of ranks[rankIndex]) {
      if (/\d/.test(char)) {
        file += Number(char);
      } else {
        result[`${String.fromCharCode(97 + file)}${rank}`] = char;
        file += 1;
      }
    }
  }
  return result;
}

function buildBoard3d() {
  // 보드 베이스
  const baseGeometry = new THREE.BoxGeometry(0.5, 0.5, 0.025);
  const baseMaterial = new THREE.MeshStandardMaterial({ 
    color: 0x2a3035, 
    roughness: 0.85,
    metalness: 0.1
  });
  const base = new THREE.Mesh(baseGeometry, baseMaterial);
  base.position.set(0, 0, 0.005);
  boardGroup.add(base);

  // 체스판 칸
  for (let rank = 0; rank < 8; rank += 1) {
    for (let file = 0; file < 8; file += 1) {
      const geometry = new THREE.BoxGeometry(squareSize, squareSize, 0.008);
      const isDark = (file + rank) % 2 === 0;
      const material = new THREE.MeshStandardMaterial({
        color: isDark ? 0x3d5233 : 0xe8dcc8,
        roughness: isDark ? 0.75 : 0.65,
        metalness: isDark ? 0.05 : 0.02
      });
      const square = new THREE.Mesh(geometry, material);
      const pos = squareToPosition(`${String.fromCharCode(97 + file)}${rank + 1}`, 0.025);
      square.position.copy(pos);
      boardGroup.add(square);
    }
  }

  const blackSideMarker = createBoardLabel("Black side / Robot base", "#dfe7ef");
  blackSideMarker.position.set(0, boardOrigin.y + squareSize * 8 + 0.045, 0.036);
  boardGroup.add(blackSideMarker);
}

function buildRobotInspectionGuides() {
  const workspaceMaterial = new THREE.LineBasicMaterial({ color: 0x4f8cc9, transparent: true, opacity: 0.55 });
  const workspacePoints = [];
  const radius = 0.46;
  for (let index = 0; index <= 96; index += 1) {
    const angle = (Math.PI * 2 * index) / 96;
    workspacePoints.push(new THREE.Vector3(
      robotBase.x + Math.cos(angle) * radius,
      robotBase.y + Math.sin(angle) * radius,
      0.031,
    ));
  }
  const workspace = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(workspacePoints),
    workspaceMaterial,
  );
  scene.add(workspace);

  const axisMaterialX = new THREE.LineBasicMaterial({ color: 0xc95f4f });
  const axisMaterialY = new THREE.LineBasicMaterial({ color: 0x67a76a });
  scene.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(boardOrigin.x, boardOrigin.y, 0.04),
      new THREE.Vector3(boardOrigin.x + squareSize * 8, boardOrigin.y, 0.04),
    ]),
    axisMaterialX,
  ));
  scene.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(boardOrigin.x, boardOrigin.y, 0.04),
      new THREE.Vector3(boardOrigin.x, boardOrigin.y + squareSize * 8, 0.04),
    ]),
    axisMaterialY,
  ));
}

function createBoardLabel(text, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 96;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = color;
  context.font = "700 42px Inter, system-ui, sans-serif";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.24, 0.045), material);
  return mesh;
}

function syncPieces3d(pieces) {
  for (const [square, piece] of Object.entries(pieces)) {
    if (!pieceMeshes.has(square)) {
      const mesh = createPieceMesh(piece);
      mesh.position.copy(squareToPosition(square, pickZ));
      pieceMeshes.set(square, mesh);
      pieceGroup.add(mesh);
    } else {
      const mesh = pieceMeshes.get(square);
      mesh.userData.piece = piece;
      if (!activeAnimation || activeAnimation.mesh !== mesh) {
        mesh.position.copy(squareToPosition(square, pickZ));
      }
    }
  }

  for (const [square, mesh] of [...pieceMeshes.entries()]) {
    if (!pieces[square] && (!activeAnimation || activeAnimation.mesh !== mesh)) {
      pieceGroup.remove(mesh);
      pieceMeshes.delete(square);
    }
  }
}

function createPieceMesh(piece) {
  const group = new THREE.Group();
  group.userData.piece = piece;

  const isWhite = piece === piece.toUpperCase();
  const material = new THREE.MeshStandardMaterial({
    color: isWhite ? 0xf1ead8 : 0x1d2024,
    roughness: 0.6,
    metalness: 0.05,
  });
  const accent = new THREE.MeshStandardMaterial({
    color: isWhite ? 0xc9b878 : 0x5e6875,
    roughness: 0.5,
  });

  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.022, 0.014, 32), material);
  base.position.z = 0.007;
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.016, 0.034, 32), material);
  body.position.z = 0.031;
  const head = new THREE.Mesh(new THREE.SphereGeometry(piece.toLowerCase() === "p" ? 0.011 : 0.014, 24, 16), accent);
  head.position.z = 0.055;
  group.add(base, body, head);

  return group;
}

function enqueueMove(move) {
  animationQueue.push(move);
  lastMoveLabel.textContent = `${move.actor}: ${move.uci}`;
}

function startMoveAnimation(move) {
  const mesh = pieceMeshes.get(move.source);
  const capturedMesh = pieceMeshes.get(move.target);
  if (capturedMesh) {
    pieceGroup.remove(capturedMesh);
    pieceMeshes.delete(move.target);
  }

  if (!mesh) return null;

  pieceMeshes.delete(move.source);
  pieceMeshes.set(move.target, mesh);

  const source = squareToPosition(move.source, pickZ);
  const target = squareToPosition(move.target, pickZ);
  return {
    move,
    mesh,
    source,
    target,
    startTime: performance.now(),
    duration: move.duration * 1000,
  };
}

function updateMoveAnimation(now) {
  if (!activeAnimation && animationQueue.length > 0) {
    activeAnimation = startMoveAnimation(animationQueue.shift());
  }
  if (!activeAnimation) {
    updateRobotPose(null);
    return;
  }

  const t = Math.min(1, (now - activeAnimation.startTime) / activeAnimation.duration);
  const pose = pickPlacePose(activeAnimation.source, activeAnimation.target, t);
  activeAnimation.mesh.position.copy(pose.piece);
  updateRobotPose(pose.gripper);

  if (t >= 1) {
    activeAnimation.mesh.position.copy(activeAnimation.target);
    activeAnimation = null;
  }
}

function pickPlacePose(source, target, t) {
  const gripper = new THREE.Vector3();
  const piece = new THREE.Vector3();
  const sourceHover = withZ(source, hoverZ);
  const targetHover = withZ(target, hoverZ);
  const sourcePick = withZ(source, pickZ);
  const targetPick = withZ(target, pickZ);

  if (t < 0.16) {
    const u = smooth(t / 0.16);
    gripper.lerpVectors(robotRestGripper, sourceHover, u);
    piece.copy(source);
  } else if (t < 0.28) {
    const u = smooth((t - 0.16) / 0.12);
    gripper.lerpVectors(sourceHover, sourcePick, u);
    piece.copy(source);
  } else if (t < 0.34) {
    gripper.copy(sourcePick);
    piece.copy(source);
  } else if (t < 0.46) {
    const u = smooth((t - 0.34) / 0.12);
    gripper.lerpVectors(sourcePick, sourceHover, u);
    piece.copy(gripper);
  } else if (t < 0.66) {
    const u = smooth((t - 0.46) / 0.20);
    gripper.lerpVectors(sourceHover, targetHover, u);
    piece.copy(gripper);
  } else if (t < 0.78) {
    const u = smooth((t - 0.66) / 0.12);
    gripper.lerpVectors(targetHover, targetPick, u);
    piece.copy(gripper);
  } else if (t < 0.84) {
    gripper.copy(targetPick);
    piece.copy(target);
  } else if (t < 0.92) {
    const u = smooth((t - 0.84) / 0.08);
    gripper.lerpVectors(targetPick, targetHover, u);
    piece.copy(target);
  } else {
    const u = smooth((t - 0.92) / 0.08);
    gripper.lerpVectors(targetHover, robotRestGripper, u);
    piece.copy(target);
  }

  return { gripper, piece };
}

function squareToPosition(square, z) {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  return new THREE.Vector3(
    boardOrigin.x + file * squareSize + squareSize / 2,
    boardOrigin.y + rank * squareSize + squareSize / 2,
    z,
  );
}

function withZ(vector, z) {
  return new THREE.Vector3(vector.x, vector.y, z);
}

function smooth(t) {
  return 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5;
}

function createRobot() {
  const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x414953, roughness: 0.55 });
  const linkMaterial = new THREE.MeshStandardMaterial({ color: 0x7b858f, roughness: 0.45 });
  const magnetMaterial = new THREE.MeshStandardMaterial({ color: 0xd3422f, roughness: 0.35 });
  const shoulderMaterial = new THREE.MeshStandardMaterial({ color: 0x4f8cc9, roughness: 0.35 });
  const elbowMaterial = new THREE.MeshStandardMaterial({ color: 0xf2c14e, roughness: 0.35 });
  const wristMaterial = new THREE.MeshStandardMaterial({ color: 0xe76f51, roughness: 0.35 });

  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.04, 36), baseMaterial);
  base.position.copy(robotBase);

  const arm = new THREE.Group();
  const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.026, 0.085, 28), baseMaterial);
  pedestal.position.copy(robotBase.clone().add(new THREE.Vector3(0, 0, 0.06)));

  const shoulder = new THREE.Mesh(new THREE.SphereGeometry(0.028, 28, 18), shoulderMaterial);
  const elbow = new THREE.Mesh(new THREE.SphereGeometry(0.024, 28, 18), elbowMaterial);
  const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 1, 20), linkMaterial);
  const forearm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1, 20), linkMaterial);
  const wrist = new THREE.Mesh(new THREE.SphereGeometry(0.021, 22, 16), wristMaterial);
  const magnet = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.016, 0.018, 18), magnetMaterial);
  const targetLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(),
      new THREE.Vector3(),
      new THREE.Vector3(),
    ]),
    new THREE.LineBasicMaterial({ color: 0xf2c14e, transparent: true, opacity: 0.88 }),
  );

  arm.add(pedestal, shoulder, elbow, upper, forearm, wrist, magnet, targetLine);
  arm.userData = { pedestal, shoulder, elbow, upper, forearm, wrist, magnet, targetLine };
  return { base, arm };
}

function updateRobotPose(gripperTarget) {
  const rawGripper = gripperTarget
    ? gripperTarget.clone().add(new THREE.Vector3(0, 0, 0.035))
    : robotRestGripper;
  filteredGripper.lerp(rawGripper, gripperTarget ? 0.34 : 0.18);
  const gripper = filteredGripper;
  const shoulder = robotBase.clone().add(new THREE.Vector3(0, 0, 0.06));
  const reach = shoulder.distanceTo(gripper);
  const elbowLift = THREE.MathUtils.clamp(0.16 - reach * 0.12, 0.075, 0.145);
  const elbow = shoulder.clone().lerp(gripper, 0.48).add(new THREE.Vector3(0, 0, elbowLift));
  const {
    upper,
    forearm,
    wrist,
    magnet,
    targetLine,
    shoulder: shoulderMesh,
    elbow: elbowMesh,
  } = robot.arm.userData;

  shoulderMesh.position.copy(shoulder);
  elbowMesh.position.copy(elbow);
  placeCylinderBetween(upper, shoulder, elbow);
  placeCylinderBetween(forearm, elbow, gripper);
  wrist.position.copy(gripper);
  magnet.position.copy(gripper.clone().add(new THREE.Vector3(0, 0, -0.022)));

  const points = [shoulder, elbow, gripper];
  targetLine.geometry.setFromPoints(points);
  targetLine.visible = Boolean(gripperTarget);

  const activeScale = gripperTarget ? 1.22 : 1.0;
  wrist.scale.setScalar(activeScale);
  magnet.scale.setScalar(gripperTarget ? 1.18 : 1.0);
}

function placeCylinderBetween(mesh, start, end) {
  const midpoint = start.clone().add(end).multiplyScalar(0.5);
  const direction = end.clone().sub(start);
  const length = direction.length();
  mesh.position.copy(midpoint);
  mesh.scale.set(1, length, 1);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
}

function resizeRenderer(renderer, targetCanvas, targetCamera) {
  const width = targetCanvas.clientWidth;
  const height = targetCanvas.clientHeight;
  if (targetCanvas.width !== width || targetCanvas.height !== height) {
    renderer.setSize(width, height, false);
    targetCamera.aspect = width / height;
    targetCamera.updateProjectionMatrix();
  }
}

function resizeRenderers() {
  resizeRenderer(topRenderer, topCanvas, topCamera);
  resizeRenderer(armRenderer, armCanvas, armCamera);
}

function renderViews() {
  topRenderer.render(scene, topCamera);
  armRenderer.render(scene, armCamera);
}

function animate(now = performance.now()) {
  resizeRenderers();
  updateMoveAnimation(now);
  renderViews();
  requestAnimationFrame(animate);
}
