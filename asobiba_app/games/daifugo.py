from __future__ import annotations

import random
from typing import Any

from .core import BaseGame


RANKS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
SUITS = ["♠", "♥", "♦", "♣"]
RANK_ORDER = {rank: index for index, rank in enumerate(RANKS)}


def make_deck() -> list[dict[str, str]]:
    deck = []
    index = 0
    for suit in SUITS:
        for rank in RANKS:
            deck.append({"id": f"d{index}", "rank": rank, "suit": suit, "label": f"{suit}{rank}"})
            index += 1
    random.shuffle(deck)
    return deck


class DaifugoEngine(BaseGame):
    game_id = "daifugo"
    title = "大富豪"
    max_players = 4

    def __init__(self) -> None:
        super().__init__()
        self.turn_index = 0
        self.hands: dict[str, list[dict[str, str]]] = {}
        self.active_play: dict[str, Any] | None = None
        self.last_actor_id: str | None = None
        self.passed: set[str] = set()

    def add_player(self, user_id: str, username: str) -> bool:
        joined = super().add_player(user_id, username)
        if joined and user_id not in self.hands:
            self.hands[user_id] = []
        if self.started and not any(self.hands.values()):
            deck = make_deck()
            for index, card in enumerate(deck):
                target = self.players[index % len(self.players)]["user_id"]
                self.hands[target].append(card)
            for user_cards in self.hands.values():
                user_cards.sort(key=lambda card: (RANK_ORDER[card["rank"]], card["suit"]))
            self.status_message = "大富豪スタート。"
        return joined

    def _turn_user_id(self) -> str:
        return self.players[self.turn_index]["user_id"]

    def _advance(self) -> None:
        self.turn_index = (self.turn_index + 1) % len(self.players)

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "daifugo",
                "turn_user_id": self._turn_user_id() if self.started and self.players else None,
                "your_hand": self.hands.get(user_id, []),
                "other_hands": [
                    {"username": player["username"], "count": len(self.hands[player["user_id"]])}
                    for player in self.players
                    if player["user_id"] != user_id
                ],
                "active_play": self.active_play,
                "passed": list(self.passed),
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if not self.started or self.winner:
            return False, "まだ遊べません。"
        if user_id != self._turn_user_id():
            return False, "あなたの番ではありません。"
        if action.get("type") == "pass":
            if not self.active_play:
                return False, "最初の手ではパスできません。"
            self.passed.add(user_id)
            if len(self.passed) >= len(self.players) - 1 and self.last_actor_id:
                self.active_play = None
                self.passed.clear()
                self.turn_index = self.player_index(self.last_actor_id)
                self.status_message = "場が流れました。"
                return True, self.status_message
            self._advance()
            self.status_message = f"{self.player_name(user_id)} はパスしました。"
            return True, self.status_message
        if action.get("type") != "play":
            return False, "その操作はできません。"
        selected_ids = list(action.get("card_ids", []))
        hand = self.hands[user_id]
        cards = [card for card in hand if card["id"] in selected_ids]
        if not cards or len(cards) != len(selected_ids):
            return False, "カード選択を確認してください。"
        ranks = {card["rank"] for card in cards}
        if len(ranks) != 1:
            return False, "同じ数字だけ出せます。"
        rank = cards[0]["rank"]
        if self.active_play:
            if len(cards) != self.active_play["count"]:
                return False, "場と同じ枚数で出してください。"
            if RANK_ORDER[rank] <= RANK_ORDER[self.active_play["rank"]]:
                return False, "もっと強い数字が必要です。"
        for card in cards:
            hand.remove(card)
        self.active_play = {
            "rank": rank,
            "count": len(cards),
            "cards": [card["label"] for card in cards],
            "by": self.player_name(user_id),
        }
        self.last_actor_id = user_id
        self.passed.clear()
        if not hand:
            self.winner = f"{self.player_name(user_id)} の勝ち"
            self.status_message = "手札がなくなりました。"
            return True, self.status_message
        self._advance()
        self.status_message = f"{self.player_name(user_id)} が {len(cards)} 枚出しました。"
        return True, self.status_message
