from __future__ import annotations

from collections import Counter
from typing import Any

import shogi

from .core import BaseGame


PIECE_LABELS = {
    "P": "歩",
    "L": "香",
    "N": "桂",
    "S": "銀",
    "G": "金",
    "B": "角",
    "R": "飛",
    "K": "玉",
    "+P": "と",
    "+L": "成香",
    "+N": "成桂",
    "+S": "成銀",
    "+B": "馬",
    "+R": "龍",
}

DROP_MAP = {
    shogi.PAWN: "P",
    shogi.LANCE: "L",
    shogi.KNIGHT: "N",
    shogi.SILVER: "S",
    shogi.GOLD: "G",
    shogi.BISHOP: "B",
    shogi.ROOK: "R",
}


class ShogiEngine(BaseGame):
    game_id = "shogi"
    title = "将棋"
    max_players = 2

    def __init__(self) -> None:
        super().__init__()
        self.board = shogi.Board()

    def _color_for(self, user_id: str) -> int:
        return shogi.BLACK if self.player_index(user_id) == 0 else shogi.WHITE

    def _board_grid(self) -> list[list[str]]:
        grid: list[list[str]] = []
        for row in range(9):
            line: list[str] = []
            for col in range(9):
                square = row * 9 + col
                piece = self.board.piece_at(square)
                line.append(piece.symbol() if piece else ".")
            grid.append(line)
        return grid

    def _hands(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for color_name, color in (("black", shogi.BLACK), ("white", shogi.WHITE)):
            pieces = self.board.pieces_in_hand[color]
            result[color_name] = [
                {"code": DROP_MAP[piece_type], "label": PIECE_LABELS[DROP_MAP[piece_type]], "count": count}
                for piece_type, count in pieces.items()
                if count > 0
            ]
        return result

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        your_color = self._color_for(user_id) if self.is_player(user_id) else None
        turn_user_id = None
        if self.started and len(self.players) >= 2:
            turn_user_id = self.players[0]["user_id"] if self.board.turn == shogi.BLACK else self.players[1]["user_id"]
        legal_moves = []
        if self.started and self.is_player(user_id) and your_color == self.board.turn and not self.winner:
            for move in self.board.legal_moves:
                legal_moves.append(
                    {
                        "usi": move.usi(),
                        "from": shogi.SQUARE_NAMES[move.from_square] if move.from_square is not None else None,
                        "to": shogi.SQUARE_NAMES[move.to_square],
                        "drop": DROP_MAP.get(move.drop_piece_type),
                        "promotion": move.promotion,
                    }
                )
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "shogi",
                "board": self._board_grid(),
                "turn_color": "black" if self.board.turn == shogi.BLACK else "white",
                "turn_user_id": turn_user_id,
                "your_color": "black" if your_color == shogi.BLACK else "white" if your_color == shogi.WHITE else None,
                "hands": self._hands(),
                "legal_moves": legal_moves,
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if not self.started or self.winner:
            return False, "まだ始まっていません。"
        if action.get("type") == "resign":
            self.winner = f"{self.players[1 - self.player_index(user_id)]['username']} の勝ち"
            self.status_message = f"{self.player_name(user_id)} が投了しました。"
            return True, self.status_message
        if action.get("type") != "move":
            return False, "その操作はできません。"
        color = self._color_for(user_id)
        if color != self.board.turn:
            return False, "相手の手番です。"
        usi = str(action.get("usi", ""))
        legal = {move.usi() for move in self.board.legal_moves}
        if usi not in legal:
            return False, "その手は指せません。"
        self.board.push_usi(usi)
        if self.board.is_game_over():
            self.winner = f"{self.player_name(user_id)} の勝ち"
            self.status_message = "対局終了。"
        else:
            self.status_message = f"{self.player_name(user_id)} が指しました。"
        return True, self.status_message
