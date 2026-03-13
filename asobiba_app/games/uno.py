from __future__ import annotations

import random
from typing import Any

from .core import BaseGame


COLORS = ["red", "yellow", "green", "blue"]


def make_uno_deck() -> list[dict[str, str]]:
    deck: list[dict[str, str]] = []
    index = 0
    for color in COLORS:
        for value in [str(num) for num in range(10)] + ["skip", "reverse", "draw2"]:
            deck.append({"id": f"c{index}", "color": color, "value": value})
            index += 1
    for value in ["wild", "wild4"] * 2:
        deck.append({"id": f"c{index}", "color": "wild", "value": value})
        index += 1
    random.shuffle(deck)
    return deck


def card_label(card: dict[str, str]) -> str:
    color = {"red": "赤", "yellow": "黄", "green": "緑", "blue": "青", "wild": "虹"}[card["color"]]
    value = {
        "skip": "スキップ",
        "reverse": "リバース",
        "draw2": "+2",
        "wild": "ワイルド",
        "wild4": "+4",
    }.get(card["value"], card["value"])
    return f"{color} {value}"


class UnoEngine(BaseGame):
    game_id = "uno"
    title = "UNO"
    max_players = 4

    def __init__(self) -> None:
        super().__init__()
        self.auto_start = False
        self.turn_index = 0
        self.direction = 1
        self.hands: dict[str, list[dict[str, str]]] = {}
        self.draw_pile: list[dict[str, str]] = []
        self.discard: list[dict[str, str]] = []
        self.current_color = "red"

    def add_player(self, user_id: str, username: str) -> bool:
        joined = super().add_player(user_id, username)
        if joined and user_id not in self.hands:
            self.hands[user_id] = []
        return joined

    def on_game_started(self) -> None:
        if not self.discard:
            self._start_game()

    def _start_game(self) -> None:
        self.draw_pile = make_uno_deck()
        for player in self.players:
            self.hands[player["user_id"]] = [self.draw_pile.pop() for _ in range(7)]
        while self.draw_pile:
            top = self.draw_pile.pop()
            if top["color"] != "wild":
                self.discard = [top]
                self.current_color = top["color"]
                break
        self.status_message = "UNO 開始。"

    def _top(self) -> dict[str, str]:
        return self.discard[-1]

    def _turn_user_id(self) -> str:
        return self.players[self.turn_index]["user_id"]

    def _advance(self, steps: int = 1) -> None:
        self.turn_index = (self.turn_index + (steps * self.direction)) % len(self.players)

    def _can_play(self, card: dict[str, str]) -> bool:
        top = self._top()
        return (
            card["color"] == "wild"
            or card["color"] == self.current_color
            or card["value"] == top["value"]
        )

    def snapshot_for(self, user_id: str) -> dict[str, Any]:
        data = self.snapshot_base(user_id)
        data.update(
            {
                "kind": "uno",
                "turn_user_id": self._turn_user_id() if self.started and self.players else None,
                "current_color": self.current_color,
                "top_card": {**self._top(), "label": card_label(self._top())} if self.discard else None,
                "your_hand": [{**card, "label": card_label(card)} for card in self.hands.get(user_id, [])],
                "other_hands": [
                    {"username": player["username"], "count": len(self.hands[player["user_id"]])}
                    for player in self.players
                    if player["user_id"] != user_id
                ],
            }
        )
        return data

    def handle_action(self, user_id: str, action: dict[str, Any]) -> tuple[bool, str]:
        if not self.started or self.winner:
            return False, "まだ遊べません。"
        if user_id != self._turn_user_id():
            return False, "あなたの番ではありません。"
        if action.get("type") == "draw":
            if not self.draw_pile:
                self.draw_pile = self.discard[:-1]
                random.shuffle(self.draw_pile)
                self.discard = self.discard[-1:]
            if self.draw_pile:
                self.hands[user_id].append(self.draw_pile.pop())
            self._advance()
            self.status_message = f"{self.player_name(user_id)} が1枚引きました。"
            return True, self.status_message
        if action.get("type") != "play":
            return False, "その操作はできません。"
        card_id = str(action.get("card_id", ""))
        hand = self.hands[user_id]
        card = next((card for card in hand if card["id"] == card_id), None)
        if not card:
            return False, "そのカードは持っていません。"
        if not self._can_play(card):
            return False, "そのカードは出せません。"
        hand.remove(card)
        self.discard.append(card)
        skip_steps = 1
        chosen_color = str(action.get("chosen_color") or card.get("color"))
        self.current_color = chosen_color if card["color"] == "wild" else card["color"]
        if card["value"] == "reverse":
            self.direction *= -1
            if len(self.players) == 2:
                skip_steps = 2
        elif card["value"] == "skip":
            skip_steps = 2
        elif card["value"] == "draw2":
            target = self.players[(self.turn_index + self.direction) % len(self.players)]["user_id"]
            for _ in range(2):
                if self.draw_pile:
                    self.hands[target].append(self.draw_pile.pop())
            skip_steps = 2
        elif card["value"] == "wild4":
            target = self.players[(self.turn_index + self.direction) % len(self.players)]["user_id"]
            for _ in range(4):
                if self.draw_pile:
                    self.hands[target].append(self.draw_pile.pop())
            skip_steps = 2
        if not hand:
            self.winner = f"{self.player_name(user_id)} の勝ち"
            self.status_message = "手札がなくなりました。"
            return True, self.status_message
        self._advance(skip_steps)
        self.status_message = f"{self.player_name(user_id)} が {card_label(card)} を出しました。"
        return True, self.status_message
