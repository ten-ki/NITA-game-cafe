from __future__ import annotations

from typing import Any

from .core import BaseGame


class GomokuEngine(BaseGame):
    game_id = "gomoku"
    title = "五目並べ"
    max_players = 2

    def __init__(self) -> None:
        super().__init__()
        self.board = [["." for _ in range(15)] for _ in range(15)]
        self.turn_piece = "B"

    def _piece_for(self, user_id: str) -> str:
        return "B" if self.player_index(user_id) == 0 else "W"

    def _winner_from(self, row: int, col: int) -> bool:
        piece = self.board[row][col]
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for direction in (-1, 1):
                r, c = row, col
                while True:
                    r += dr * direction
                    c += dc * direction
                    if 0 <= r < 15 and 0 <= c < 15 and self.board[r][c] == piece:
                        count += 1
                    else:
                        break
            if count >= 5:
                return True
        return False

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        piece = self._piece_for(user_id) if self.is_player(user_id) else None
        turn_user_id = None
        if self.started and len(self.players) >= 2:
            turn_user_id = self.players[0]["user_id"] if self.turn_piece == "B" else self.players[1]["user_id"]
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "board-grid",
                "board": self.board,
                "rows": 15,
                "cols": 15,
                "piece": piece,
                "turn_piece": self.turn_piece,
                "turn_user_id": turn_user_id,
                "valid_moves": [
                    {"row": r, "col": c}
                    for r in range(15)
                    for c in range(15)
                    if self.board[r][c] == "." and piece == self.turn_piece and self.started and not self.winner
                ],
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if action.get("type") != "place" or not self.started or self.winner:
            return False, "まだ置けません。"
        piece = self._piece_for(user_id)
        if piece != self.turn_piece:
            return False, "相手の手番です。"
        row, col = int(action.get("row", -1)), int(action.get("col", -1))
        if not (0 <= row < 15 and 0 <= col < 15) or self.board[row][col] != ".":
            return False, "そこには置けません。"
        self.board[row][col] = piece
        if self._winner_from(row, col):
            self.winner = f"{self.player_name(user_id)} の勝ち"
            self.status_message = "五目達成。"
        else:
            self.turn_piece = "W" if piece == "B" else "B"
            self.status_message = "着手しました。"
        return True, self.status_message
