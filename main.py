from __future__ import annotations

from pathlib import Path
import secrets

from fastapi import FastAPI, Form, Request, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from asobiba_app.auth import (
    current_user,
    guest_cookie_value,
    login_cookie_value,
    room_token_for_user,
    validate_room_token,
)
from asobiba_app.catalog import GAME_MAP, GAMES
from asobiba_app.db import (
    authenticate_user,
    close_missing_room_posts,
    close_post,
    create_post,
    create_user,
    get_user_summary,
    init_db,
    list_open_posts,
)
from asobiba_app.room_manager import ROOM_MANAGER
from asobiba_app.security import AuthError


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Asobiba Game Cafe")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def redirect(path: str, message: str | None = None) -> RedirectResponse:
    target = path
    if message:
        sep = "&" if "?" in path else "?"
        target = f"{path}{sep}message={message}"
    return RedirectResponse(target, status_code=303)


def render(request: Request, template_name: str, **context):
    user = current_user(request)
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "user": user,
            "games": GAMES,
            "game_map": GAME_MAP,
            "flash": request.query_params.get("message"),
            **context,
        },
    )


def login_client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def sync_posts_with_rooms() -> None:
    close_missing_room_posts(ROOM_MANAGER.rooms.keys())


@app.on_event("startup")
def startup() -> None:
    init_db()
    sync_posts_with_rooms()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    sync_posts_with_rooms()
    return render(request, "index.html", posts=list_open_posts())


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "register.html")


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    pin: str = Form(...),
):
    try:
        user = create_user(username, pin)
    except AuthError as exc:
        return render(request, "register.html", error=str(exc), username=username)
    response = redirect("/", "登録してログインしました。")
    response.set_cookie("asobiba_session", login_cookie_value(str(user["id"])), httponly=True, samesite="lax")
    return response


@app.post("/guest/login")
def guest_login(request: Request, guest_name: str = Form(...)):
    guest_name = guest_name.strip()
    if not guest_name:
        return render(request, "index.html", posts=list_open_posts(), error="表示名を入力してください。")
    try:
        cookie_value = guest_cookie_value(secrets.token_hex(4), guest_name)
    except AuthError as exc:
        return render(request, "index.html", posts=list_open_posts(), error=str(exc))
    response = redirect("/", f"{guest_name} で参加しました。")
    response.set_cookie(
        "asobiba_session",
        cookie_value,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    pin: str = Form(...),
):
    try:
        user = authenticate_user(username, pin, client_key=login_client_key(request))
    except AuthError as exc:
        return render(request, "login.html", error=str(exc), username=username)
    response = redirect("/", "ログインしました。")
    response.set_cookie("asobiba_session", login_cookie_value(str(user["id"])), httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = redirect("/", "ログアウトしました。")
    response.delete_cookie("asobiba_session")
    return response


@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request):
    user = current_user(request)
    if not user:
        return redirect("/login", "先にログインしてください。")
    if user.get("is_guest"):
        return redirect("/", "ゲストにはプロフィール機能はありません。")
    return render(request, "profile.html", summary=get_user_summary(user["id"]))


@app.post("/rooms/create")
def create_room_route(
    request: Request,
    game_id: str = Form(...),
    title: str = Form(...),
    note: str = Form(""),
):
    user = current_user(request)
    if not user:
        return redirect("/", "表示名を入力してから部屋を作ってください。")
    if game_id not in GAME_MAP:
        return redirect("/", "ゲームを選び直してください。")
    title = title.strip()[:60]
    note = note.strip()[:200]
    if not title:
        title = f"{GAME_MAP[game_id]['name']} 募集"
    room = ROOM_MANAGER.create_room(game_id, str(user["id"]), user["username"], title, note)
    if not user.get("is_guest"):
        create_post(user["id"], user["username"], game_id, title, note, room.code)
    return redirect(f"/rooms/{room.code}", "部屋を作りました。")


@app.post("/posts/{post_id}/close")
def close_post_route(post_id: int, request: Request):
    user = current_user(request)
    if not user:
        return redirect("/login", "ログインしてください。")
    close_post(post_id, user["id"])
    return redirect("/", "募集を閉じました。")


@app.get("/rooms/{code}", response_class=HTMLResponse)
def room_page(code: str, request: Request):
    user = current_user(request)
    if not user:
        return redirect("/", "表示名を入力して参加してください。")
    sync_posts_with_rooms()
    room = ROOM_MANAGER.get_room(code)
    if not room:
        return redirect("/", "部屋が見つかりません。")
    return render(
        request,
        "room.html",
        room=room,
        ws_token=room_token_for_user(user, code),
    )


@app.websocket("/ws/rooms/{code}")
async def room_socket(websocket: WebSocket, code: str, token: str):
    identity = validate_room_token(token, code)
    room = ROOM_MANAGER.get_room(code)
    if not identity or not room:
        await websocket.close(code=4404)
        return
    await room.connect(websocket, str(identity["id"]), identity["username"])
