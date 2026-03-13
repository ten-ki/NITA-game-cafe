from __future__ import annotations

import asyncio
import random
import string
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .games.connect_four import ConnectFourEngine
from .games.daifugo import DaifugoEngine, RANK_ORDER
from .games.gomoku import GomokuEngine
from .games.othello import OthelloEngine
from .games.shogi_game import ShogiEngine
from .games.uno import UnoEngine


ENGINE_FACTORIES = {
    "othello": OthelloEngine,
    "gomoku": GomokuEngine,
    "connect-four": ConnectFourEngine,
    "shogi": ShogiEngine,
    "uno": UnoEngine,
    "daifugo": DaifugoEngine,
}


def room_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


@dataclass
class Room:
    code: str
    title: str
    note: str
    game_id: str
    engine: Any
    connections: dict[str, list[WebSocket]] = field(default_factory=dict)
    usernames: dict[str, str] = field(default_factory=dict)
    chat: list[dict[str, str]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready_player_ids: set[str] = field(default_factory=set)
    fill_decision_open: bool = False
    fill_votes: dict[str, str] = field(default_factory=dict)
    cpu_counter: int = 0

    @staticmethod
    def _is_cpu(user_id: str) -> bool:
        return user_id.startswith("cpu:")

    def _human_player_ids(self) -> list[str]:
        return [player["user_id"] for player in self.engine.players if not self._is_cpu(player["user_id"])]

    def _next_cpu_identity(self) -> tuple[str, str]:
        self.cpu_counter += 1
        return f"cpu:{self.code}:{self.cpu_counter}", f"CPU-{self.cpu_counter}"

    def _add_cpu_player(self) -> bool:
        if self.engine.started or len(self.engine.players) >= self.engine.max_players:
            return False
        cpu_id, cpu_name = self._next_cpu_identity()
        return self.engine.add_player(cpu_id, cpu_name)

    def _turn_user_id(self) -> str | None:
        if not self.engine.started or not self.engine.players:
            return None
        snapshot = self.engine.snapshot_for(self.engine.players[0]["user_id"])
        return snapshot.get("turn_user_id")

    def _close_fill_decision(self) -> None:
        self.fill_decision_open = False
        self.fill_votes.clear()

    def _update_waiting_status(self) -> None:
        humans = self._human_player_ids()
        if not humans:
            self.engine.status_message = "参加者を待っています。"
            return
        ready_count = sum(1 for user_id in humans if user_id in self.ready_player_ids)
        self.engine.status_message = f"準備OK {ready_count}/{len(humans)}"

    def _maybe_start_multiplayer(self) -> None:
        if self.engine.auto_start or self.engine.started or self.engine.winner:
            return
        humans = self._human_player_ids()
        if len(self.engine.players) < self.engine.min_players:
            self._close_fill_decision()
            self._update_waiting_status()
            return
        if any(user_id not in self.ready_player_ids for user_id in humans):
            self._close_fill_decision()
            self._update_waiting_status()
            return
        if len(self.engine.players) >= self.engine.max_players:
            self.engine.start_game()
            return
        if not self.fill_decision_open:
            self.fill_decision_open = True
            self.fill_votes.clear()
            self.engine.status_message = "全員準備OK。不足人数をCPUで補充するか選択してください。"

    def _apply_fill_decision(self) -> None:
        humans = self._human_player_ids()
        if not humans or any(user_id not in self.fill_votes for user_id in humans):
            return
        choices = {self.fill_votes[user_id] for user_id in humans}
        if len(choices) > 1:
            self.fill_votes.clear()
            self.engine.status_message = "意見が分かれています。全員で同じ選択をしてください。"
            return
        decision = choices.pop()
        if decision == "fill":
            while len(self.engine.players) < self.engine.max_players:
                if not self._add_cpu_player():
                    break
            self.engine.status_message = "CPUを補充しました。"
        self._close_fill_decision()
        self.engine.start_game()

    def _pick_cpu_action(self, cpu_id: str) -> dict[str, Any] | None:
        snapshot = self.engine.snapshot_for(cpu_id)
        if self.game_id in {"othello", "gomoku"}:
            moves = snapshot.get("valid_moves") or []
            if not moves:
                return None
            move = random.choice(moves)
            return {"type": "place", "row": move["row"], "col": move["col"]}
        if self.game_id == "connect-four":
            columns = snapshot.get("valid_columns") or []
            if not columns:
                return None
            choice = random.choice(columns)
            return {"type": "drop", "col": choice["col"]}
        if self.game_id == "shogi":
            legal = snapshot.get("legal_moves") or []
            if not legal:
                return None
            return {"type": "move", "usi": random.choice(legal)["usi"]}
        if self.game_id == "uno":
            hand = snapshot.get("your_hand") or []
            top = snapshot.get("top_card")
            current_color = snapshot.get("current_color")
            playable = []
            for card in hand:
                if card["color"] == "wild" or card["color"] == current_color or (top and card["value"] == top["value"]):
                    playable.append(card)
            if not playable:
                return {"type": "draw"}
            card = random.choice(playable)
            action: dict[str, Any] = {"type": "play", "card_id": card["id"]}
            if card["color"] == "wild":
                colors = [item["color"] for item in hand if item["color"] != "wild"]
                action["chosen_color"] = max(colors, key=colors.count) if colors else random.choice(["red", "yellow", "green", "blue"])
            return action
        if self.game_id == "daifugo":
            hand = sorted(snapshot.get("your_hand") or [], key=lambda card: (RANK_ORDER[card["rank"]], card["suit"]))
            if not hand:
                return None
            active = snapshot.get("active_play")
            grouped: dict[str, list[dict[str, str]]] = {}
            for card in hand:
                grouped.setdefault(card["rank"], []).append(card)
            if not active:
                lowest_rank = min(grouped.keys(), key=lambda rank: RANK_ORDER[rank])
                return {"type": "play", "card_ids": [grouped[lowest_rank][0]["id"]]}
            needed_count = int(active["count"])
            active_rank = active["rank"]
            candidates = [
                cards for rank, cards in grouped.items()
                if len(cards) >= needed_count and RANK_ORDER[rank] > RANK_ORDER[active_rank]
            ]
            if not candidates:
                return {"type": "pass"}
            cards = min(candidates, key=lambda items: RANK_ORDER[items[0]["rank"]])
            return {"type": "play", "card_ids": [card["id"] for card in cards[:needed_count]]}
        return None

    def _run_cpu_turns(self) -> None:
        for _ in range(24):
            if not self.engine.started or self.engine.winner:
                return
            turn_user_id = self._turn_user_id()
            if not turn_user_id or not self._is_cpu(turn_user_id):
                return
            action = self._pick_cpu_action(turn_user_id)
            if not action:
                return
            self.engine.handle_action(turn_user_id, action)

    def _handle_room_action(self, user_id: str, payload: dict[str, Any]) -> bool:
        action_type = str(payload.get("type", ""))
        if action_type == "ready_toggle":
            if self.engine.started or not self.engine.is_player(user_id) or self._is_cpu(user_id):
                return False
            if payload.get("ready"):
                self.ready_player_ids.add(user_id)
            else:
                self.ready_player_ids.discard(user_id)
                self._close_fill_decision()
            self._maybe_start_multiplayer()
            return True
        if action_type == "fill_decision":
            if not self.fill_decision_open or user_id not in self._human_player_ids():
                return False
            choice = str(payload.get("choice", ""))
            if choice not in {"fill", "start"}:
                return False
            self.fill_votes[user_id] = choice
            self._apply_fill_decision()
            return True
        if action_type == "add_cpu":
            if user_id not in self._human_player_ids():
                return False
            if self._add_cpu_player():
                if self.engine.auto_start:
                    self._run_cpu_turns()
                else:
                    self._maybe_start_multiplayer()
            return True
        return False

    async def connect(self, websocket: WebSocket, user_id: str, username: str) -> None:
        await websocket.accept()
        async with self.lock:
            self.usernames[user_id] = username
            self.connections.setdefault(user_id, []).append(websocket)
            if not self.engine.is_player(user_id):
                self.engine.add_player(user_id, username)
            if not self.engine.auto_start:
                self._update_waiting_status()
                self._maybe_start_multiplayer()
            self._run_cpu_turns()
        await self.broadcast_state()
        try:
            while True:
                message = await websocket.receive_json()
                async with self.lock:
                    if message.get("type") == "chat":
                        text = str(message.get("text", "")).strip()[:160]
                        if text:
                            self.chat.append({"author": username, "text": text})
                            self.chat = self.chat[-40:]
                    elif message.get("type") == "action":
                        payload = message.get("payload", {})
                        handled = self._handle_room_action(user_id, payload)
                        if not handled and self.engine.is_player(user_id):
                            self.engine.handle_action(user_id, payload)
                        self._run_cpu_turns()
                await self.broadcast_state()
        except WebSocketDisconnect:
            async with self.lock:
                self.connections[user_id] = [ws for ws in self.connections.get(user_id, []) if ws is not websocket]
                if not self.connections[user_id]:
                    self.connections.pop(user_id, None)
                if user_id not in self.connections:
                    self.ready_player_ids.discard(user_id)
                    self.fill_votes.pop(user_id, None)
                    self._maybe_start_multiplayer()
            await self.broadcast_state()

    async def broadcast_state(self) -> None:
        stale: list[tuple[str, WebSocket]] = []
        for user_id, sockets in list(self.connections.items()):
            payload = self.engine.snapshot_for(user_id)
            payload["type"] = "state"
            payload["room"] = {
                "code": self.code,
                "title": self.title,
                "note": self.note,
                "game_id": self.game_id,
            }
            payload["chat"] = self.chat
            payload["players"] = [
                {
                    "user_id": player["user_id"],
                    "username": player["username"],
                    "online": player["user_id"] in self.connections,
                    "is_cpu": self._is_cpu(player["user_id"]),
                }
                for player in self.engine.players
            ]
            payload["spectators"] = [
                {"user_id": user_id, "username": self.usernames[user_id]}
                for user_id in self.connections
                if not self.engine.is_player(user_id)
            ]
            human_players = self._human_player_ids()
            payload["room_controls"] = {
                "ready_player_ids": list(self.ready_player_ids),
                "fill_decision_open": self.fill_decision_open,
                "fill_votes": self.fill_votes,
                "can_add_cpu": not self.engine.started and len(self.engine.players) < self.engine.max_players,
                "cpu_count": sum(1 for player in self.engine.players if self._is_cpu(player["user_id"])),
                "human_player_count": len(human_players),
                "current_player_count": len(self.engine.players),
                "max_players": self.engine.max_players,
                "min_players": self.engine.min_players,
                "uses_ready_flow": not self.engine.auto_start,
            }
            for socket in list(sockets):
                try:
                    await socket.send_json(payload)
                except Exception:
                    stale.append((user_id, socket))
        for user_id, socket in stale:
            self.connections[user_id] = [ws for ws in self.connections.get(user_id, []) if ws is not socket]
            if not self.connections[user_id]:
                self.connections.pop(user_id, None)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def create_room(self, game_id: str, owner_id: str, owner_name: str, title: str, note: str) -> Room:
        code = room_code()
        while code in self.rooms:
            code = room_code()
        engine = ENGINE_FACTORIES[game_id]()
        engine.add_player(owner_id, owner_name)
        room = Room(code=code, title=title, note=note, game_id=game_id, engine=engine)
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Room | None:
        return self.rooms.get(code)


ROOM_MANAGER = RoomManager()
