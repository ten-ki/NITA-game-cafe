from __future__ import annotations

import asyncio
import random
import string
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .games.connect_four import ConnectFourEngine
from .games.daifugo import DaifugoEngine
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

    async def connect(self, websocket: WebSocket, user_id: str, username: str) -> None:
        await websocket.accept()
        async with self.lock:
            self.usernames[user_id] = username
            self.connections.setdefault(user_id, []).append(websocket)
            if not self.engine.is_player(user_id):
                self.engine.add_player(user_id, username)
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
                        if self.engine.is_player(user_id):
                            self.engine.handle_action(user_id, message.get("payload", {}))
                await self.broadcast_state()
        except WebSocketDisconnect:
            async with self.lock:
                self.connections[user_id] = [ws for ws in self.connections.get(user_id, []) if ws is not websocket]
                if not self.connections[user_id]:
                    self.connections.pop(user_id, None)
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
                }
                for player in self.engine.players
            ]
            payload["spectators"] = [
                {"user_id": user_id, "username": self.usernames[user_id]}
                for user_id in self.connections
                if not self.engine.is_player(user_id)
            ]
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
