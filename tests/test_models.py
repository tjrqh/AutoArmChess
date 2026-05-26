"""도메인 모델 단위 테스트."""

from core.models import BoardSquare, ChessMoveCommand, Pose3D
from core.pieces import PIECE_INFOS, get_piece_name, get_piece_value

import chess


def test_board_square_uci_roundtrip():
    """UCI 칸 표기법과 BoardSquare 간 변환 테스트."""
    square = BoardSquare.from_uci("e2")
    assert square.file == 4
    assert square.rank == 1
    assert square.to_uci() == "e2"


def test_board_square_boundaries():
    """체스판 경계 테스트."""
    # 최소값
    min_square = BoardSquare.from_uci("a1")
    assert min_square.file == 0
    assert min_square.rank == 0
    assert min_square.to_uci() == "a1"
    
    # 최대값
    max_square = BoardSquare.from_uci("h8")
    assert max_square.file == 7
    assert max_square.rank == 7
    assert max_square.to_uci() == "h8"


def test_board_square_invalid():
    """잘못된 칸 표기법 테스트."""
    try:
        BoardSquare.from_uci("i9")  # 범위 초과
        assert False, "Should raise ValueError"
    except ValueError:
        pass


def test_chess_move_command_from_uci():
    """체스 이동 명령 생성 테스트."""
    command = ChessMoveCommand.from_uci("e2e4")
    assert command.source.to_uci() == "e2"
    assert command.target.to_uci() == "e4"
    assert command.promotion is None


def test_chess_move_command_with_promotion():
    """프로모션이 포함된 체스 이동 명령 테스트."""
    command = ChessMoveCommand.from_uci("e7e8q")
    assert command.source.to_uci() == "e7"
    assert command.target.to_uci() == "e8"
    assert command.promotion == "q"


def test_pose3d_with_z():
    """포즈의 z 높이 변경 테스트."""
    pose1 = Pose3D(x=1.0, y=2.0, z=3.0)
    pose2 = pose1.with_z(5.0)
    
    assert pose2.x == 1.0
    assert pose2.y == 2.0
    assert pose2.z == 5.0


def test_piece_values():
    """기물 가치 테스트."""
    assert get_piece_value(chess.PAWN) == 100
    assert get_piece_value(chess.KNIGHT) == 320
    assert get_piece_value(chess.BISHOP) == 330
    assert get_piece_value(chess.ROOK) == 500
    assert get_piece_value(chess.QUEEN) == 900
    assert get_piece_value(chess.KING) == 0


def test_piece_names():
    """기물 이름 테스트."""
    assert get_piece_name(chess.PAWN, lang="en") == "Pawn"
    assert get_piece_name(chess.PAWN, lang="ko") == "폰"
    assert get_piece_name(chess.QUEEN, lang="en") == "Queen"
    assert get_piece_name(chess.QUEEN, lang="ko") == "퀸"


def test_piece_infos_frozen():
    """기물 정보가 불변인지 테스트."""
    pawn_info = PIECE_INFOS[chess.PAWN]
    try:
        pawn_info.value = 200  # 변경 시도
        assert False, "Should not be mutable"
    except AttributeError:
        pass  # 예상된 동작


