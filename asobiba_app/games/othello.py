from __future__ import annotations

from typing import Any

from .core import BaseGame


class OthelloEngine(BaseGame):
    game_id = "othello"
    title = "オセロ"
    max_players = 2

    def __init__(self) -> None:
        super().__init__()
        self.board = [["." for _ in range(8)] for _ in range(8)]
        self.board[3][3] = self.board[4][4] = "W"
        self.board[3][4] = self.board[4][3] = "B"
        self.turn_piece = "B"

    def _piece_for(self, user_id: str) -> str:
        return "B" if self.player_index(user_id) == 0 else "W"

    def _valid_moves(self, piece: str) -> list[tuple[int, int]]:
        enemy = "W" if piece == "B" else "B"
        moves: list[tuple[int, int]] = []
        for row in range(8):
            for col in range(8):
                if self.board[row][col] != ".":
                    continue
                found = False
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == dc == 0:
                            continue
                        r, c = row + dr, col + dc
                        seen_enemy = False
                        while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == enemy:
                            seen_enemy = True
                            r += dr
                            c += dc
                        if seen_enemy and 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == piece:
                            found = True
                if found:
                    moves.append((row, col))
        return moves

    def _apply_move(self, row: int, col: int, piece: str) -> None:
        enemy = "W" if piece == "B" else "B"
        self.board[row][col] = piece
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                path: list[tuple[int, int]] = []
                r, c = row + dr, col + dc
                while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == enemy:
                    path.append((r, c))
                    r += dr
                    c += dc
                if path and 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == piece:
                    for pr, pc in path:
                        self.board[pr][pc] = piece

    def _finish(self) -> None:
        black = sum(cell == "B" for row in self.board for cell in row)
        white = sum(cell == "W" for row in self.board for cell in row)
        if black == white:
            self.winner = "引き分け"
        elif black > white:
            self.winner = f"{self.players[0]['username']} の勝ち"
        else:
            self.winner = f"{self.players[1]['username']} の勝ち"
        self.status_message = f"対局終了: 黒 {black} / 白 {white}"

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        piece = self._piece_for(user_id) if self.is_player(user_id) else None
        valid = self._valid_moves(piece) if self.started and piece == self.turn_piece and not self.winner else []
        turn_user_id = None
        if self.started and len(self.players) >= 2:
            turn_user_id = self.players[0]["user_id"] if self.turn_piece == "B" else self.players[1]["user_id"]
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "board-grid",
                "board": self.board,
                "rows": 8,
                "cols": 8,
                "piece": piece,
                "turn_piece": self.turn_piece,
                "turn_user_id": turn_user_id,
                "valid_moves": [{"row": r, "col": c} for r, c in valid],
                "scores": {
                    "B": sum(cell == "B" for row in self.board for cell in row),
                    "W": sum(cell == "W" for row in self.board for cell in row),
                },
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if action.get("type") != "place" or not self.started or self.winner:
            return False, "まだ打てません。"
        piece = self._piece_for(user_id)
        if piece != self.turn_piece:
            return False, "相手の手番です。"
        row, col = int(action.get("row", -1)), int(action.get("col", -1))
        valid = self._valid_moves(piece)
        if (row, col) not in valid:
            return False, "そこには置けません。"
        self._apply_move(row, col, piece)
        next_piece = "W" if piece == "B" else "B"
        next_moves = self._valid_moves(next_piece)
        current_moves = self._valid_moves(piece)
        if next_moves:
            self.turn_piece = next_piece
            self.status_message = "着手しました。"
        elif current_moves:
            self.turn_piece = piece
            self.status_message = "相手は置ける場所がなくパスです。"
        else:
            self._finish()
        return True, self.status_message
