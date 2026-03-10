from __future__ import annotations

from typing import Any


class BaseGame:
    game_id = ""
    title = ""
    min_players = 2
    max_players = 2

    def __init__(self) -> None:
        self.players: list[dict[str, str]] = []
        self.started = False
        self.winner: str | None = None
        self.status_message = "プレイヤーを待っています。"

    def add_player(self, user_id: str, username: str) -> bool:
        if self.is_player(user_id):
            return True
        if self.started or len(self.players) >= self.max_players:
            return False
        self.players.append({"user_id": user_id, "username": username})
        if len(self.players) >= self.min_players:
            self.started = True
            self.status_message = "対戦スタート。"
        else:
            self.status_message = "もう1人の参加を待っています。"
        return True

    def is_player(self, user_id: str) -> bool:
        return any(player["user_id"] == user_id for player in self.players)

    def player_index(self, user_id: str) -> int:
        for index, player in enumerate(self.players):
            if player["user_id"] == user_id:
                return index
        return -1

    def player_name(self, user_id: str) -> str:
        for player in self.players:
            if player["user_id"] == user_id:
                return player["username"]
        return "不明"

    def snapshot_base(self, user_id: str) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "title": self.title,
            "started": self.started,
            "winner": self.winner,
            "status_message": self.status_message,
            "seat": self.player_index(user_id),
            "is_player": self.is_player(user_id),
        }
