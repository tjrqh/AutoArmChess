"""체스 기물 정의 및 표현.

기물의 기호, 한글명, 가치를 중앙에서 관리한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import chess


@dataclass(frozen=True)
class PieceInfo:
    """체스 기물의 상세 정보."""

    piece_type: int  # chess.PAWN, chess.KNIGHT, ...
    name_ko: str  # "폰", "나이트", ...
    name_en: str  # "Pawn", "Knight", ...
    symbol: str  # "p", "n", ... (소문자)
    value: int  # 물질가치 (센트)

    def display_name(self, color: str = "en") -> str:
        """기물의 표시 이름을 반환한다.
        
        Args:
            color: "ko" (한글) 또는 "en" (영문). 기본값은 영문.
        """
        return self.name_ko if color == "ko" else self.name_en


# 기물 정의 (가치는 centipawn 단위)
PIECE_INFOS = {
    chess.PAWN: PieceInfo(
        piece_type=chess.PAWN,
        name_ko="폰",
        name_en="Pawn",
        symbol="p",
        value=100,
    ),
    chess.KNIGHT: PieceInfo(
        piece_type=chess.KNIGHT,
        name_ko="나이트",
        name_en="Knight",
        symbol="n",
        value=320,
    ),
    chess.BISHOP: PieceInfo(
        piece_type=chess.BISHOP,
        name_ko="비숍",
        name_en="Bishop",
        symbol="b",
        value=330,
    ),
    chess.ROOK: PieceInfo(
        piece_type=chess.ROOK,
        name_ko="룩",
        name_en="Rook",
        symbol="r",
        value=500,
    ),
    chess.QUEEN: PieceInfo(
        piece_type=chess.QUEEN,
        name_ko="퀸",
        name_en="Queen",
        symbol="q",
        value=900,
    ),
    chess.KING: PieceInfo(
        piece_type=chess.KING,
        name_ko="킹",
        name_en="King",
        symbol="k",
        value=0,
    ),
}


def get_piece_value(piece_type: int) -> int:
    """기물 타입으로 물질가치를 조회한다."""
    return PIECE_INFOS.get(piece_type, PieceInfo(piece_type, "?", "?", "?", 0)).value


def get_piece_name(piece_type: int, lang: str = "en") -> str:
    """기물 타입으로 이름을 조회한다."""
    info = PIECE_INFOS.get(piece_type)
    if not info:
        return "?"
    return info.display_name(color=lang)


# AI 평가 함수용 가치 맵
PIECE_VALUES = {info.piece_type: info.value for info in PIECE_INFOS.values()}
