from __future__ import annotations

from typing import Any

from .core import BaseGame


class ConnectFourEngine(BaseGame):
    game_id = "connect-four"
    title = "四目並べ"
    max_players = 2

    def __init__(self) -> None:
        super().__init__()
        self.board = [["." for _ in range(7)] for _ in range(6)]
        self.turn_piece = "R"

    def _piece_for(self, user_id: str) -> str:
        return "R" if self.player_index(user_id) == 0 else "Y"

    def _drop_row(self, col: int) -> int | None:
        for row in range(5, -1, -1):
            if self.board[row][col] == ".":
                return row
        return None

    def _winner_from(self, row: int, col: int) -> bool:
        piece = self.board[row][col]
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for direction in (-1, 1):
                r, c = row, col
                while True:
                    r += dr * direction
                    c += dc * direction
                    if 0 <= r < 6 and 0 <= c < 7 and self.board[r][c] == piece:
                        count += 1
                    else:
                        break
            if count >= 4:
                return True
        return False

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        piece = self._piece_for(user_id) if self.is_player(user_id) else None
        valid = [
            {"col": col}
            for col in range(7)
            if self._drop_row(col) is not None and piece == self.turn_piece and self.started and not self.winner
        ]
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "connect-four",
                "board": self.board,
                "rows": 6,
                "cols": 7,
                "piece": piece,
                "turn_piece": self.turn_piece,
                "valid_columns": valid,
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if action.get("type") != "drop" or not self.started or self.winner:
            return False, "まだ置けません。"
        piece = self._piece_for(user_id)
        if piece != self.turn_piece:
            return False, "相手の手番です。"
        col = int(action.get("col", -1))
        if not 0 <= col < 7:
            return False, "列を選んでください。"
        row = self._drop_row(col)
        if row is None:
            return False, "その列は埋まっています。"
        self.board[row][col] = piece
        if self._winner_from(row, col):
            self.winner = f"{self.player_name(user_id)} の勝ち"
            self.status_message = "四目達成。"
        else:
            self.turn_piece = "Y" if piece == "R" else "R"
            self.status_message = "着手しました。"
        return True, self.status_message
