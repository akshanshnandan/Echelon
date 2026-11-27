"""Small authoritative HTTP API for Classic and Expanded battles."""
import json
import hashlib
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .doctrines import WEIGHTS, draft
from .drafting import RULES, purchase, remaining, remove, validate
from .engine import STATS, score
from .expanded import strength
from .expanded_game import ExpandedGame
from .live_game import LiveGame
from .model import Order, OrderType
from .recording import state_snapshot
from .command_game import CommandGame
from .command_engine import MAPS


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
SESSION_LIMIT = max(1, int(os.environ.get("ECHELON_MAX_SESSIONS", "256")))
SESSION_TTL = max(60, int(os.environ.get("ECHELON_SESSION_TTL", "3600")))
PPO_CHECKPOINT = os.environ.get("ECHELON_PPO_CHECKPOINT")
POSTHOG_TOKEN = os.environ.get("ECHELON_POSTHOG_PROJECT_TOKEN", "")
POSTHOG_HOST = os.environ.get("ECHELON_POSTHOG_HOST", "https://us.i.posthog.com")
MAX_REQUEST_BYTES = 16_384


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GameRequest(StrictModel):
    ruleset: Literal["Classic", "Expanded"] = "Classic"
    human_army: Literal["Blue", "Red"] = "Blue"
    opponent: str = "heuristic"
    first_army: Literal["Blue", "Red"] = "Blue"
    deployment: Literal["fixed", "random"] = "fixed"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    roster: list[Literal["infantry", "cavalry", "artillery"]] | None = Field(default=None, max_length=RULES.maximum)


class DraftRequest(StrictModel):
    roster: list[Literal["infantry", "cavalry", "artillery"]] = Field(default_factory=list, max_length=RULES.maximum)
    doctrine: Literal["balanced", "cavalry", "artillery", "infantry"] = "balanced"
    human_army: Literal["Blue", "Red"] = "Blue"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class OrderRequest(StrictModel):
    unit_id: str = Field(min_length=1, max_length=20)
    kind: Literal["HOLD", "ADVANCE", "ATTACK", "RETREAT"]
    target: tuple[int, int] | str | None = None


class PurchaseRequest(StrictModel):
    roster: list[Literal["infantry", "cavalry", "artillery"]] = Field(default_factory=list, max_length=RULES.maximum)
    kind: Literal["infantry", "cavalry", "artillery"]


class RemoveRequest(StrictModel):
    roster: list[Literal["infantry", "cavalry", "artillery"]] = Field(max_length=RULES.maximum)
    index: int = Field(ge=0, le=RULES.maximum - 1)


class CommandRequest(StrictModel):
    human_army: Literal["Blue", "Red"] = "Blue"
    opponent: Literal["balanced", "aggressive", "defensive"] = "balanced"
    map: Literal["open_field", "ridge_forest"] = "open_field"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    roster: list[Literal["infantry", "cavalry", "artillery"]] | None = Field(default=None, min_length=2, max_length=8)


class CommandOrderRequest(StrictModel):
    ids: list[str] = Field(min_length=1, max_length=8)
    kind: Literal["MOVE", "ATTACK", "HOLD", "DEFEND", "RETREAT", "STOP"]
    target: tuple[float, float] | str | None = None
    waypoints: list[tuple[float, float]] = Field(default_factory=list, max_length=6)


class CommandControlRequest(StrictModel):
    paused: bool | None = None
    speed: Literal[0.5, 1.0, 2.0, 4.0] | None = None


class FeedbackRequest(StrictModel):
    rating: int = Field(ge=1, le=5)
    category: Literal["gameplay", "controls", "performance", "bug", "other"]


class RateLimiter:
    """Small per-process abuse guard; only salted address digests are held in memory."""

    def __init__(self):
        self.salt = secrets.token_bytes(32)
        self.buckets = {}
        self.lock = threading.Lock()

    def check(self, address, group, limit, window):
        digest = hashlib.blake2s(address.encode(), key=self.salt).hexdigest()
        key = (digest, group)
        now = time.monotonic()
        with self.lock:
            if len(self.buckets) >= 4096:
                self.buckets = {k: v for k, v in self.buckets.items() if v and v[-1] > now - 3600}
                while len(self.buckets) >= 4096:
                    oldest = next((k for k in self.buckets if k[1] != "all"), None)
                    if oldest is None:
                        break
                    self.buckets.pop(oldest)
            bucket = self.buckets.setdefault(key, deque())
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                return max(1, int(window - (now - bucket[0])))
            bucket.append(now)
            return 0


rate_limiter = RateLimiter()


class PublicGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        if path == "/api/health":
            return await self.app(scope, receive, send)
        address = (scope.get("client") or ("unknown", 0))[0]
        if path == "/api/feedback":
            group, limit, window = "feedback", 5, 3600
        elif method == "GET" and (path.endswith("/replay") or path == "/api/replays/sample/expanded"):
            group, limit, window = "replay", 30, 60
        elif method == "GET" and path.startswith("/api/command/"):
            group, limit, window = "command_poll", 3000, 60
        elif method == "POST" and path in ("/api/games", "/api/command"):
            group, limit, window = "create", 12, 60
        elif method == "POST":
            group, limit, window = "write", 120, 60
        else:
            group, limit, window = "read", 360, 60
        retry = rate_limiter.check(address, group, limit, window)
        if not retry:
            retry = rate_limiter.check("global", "all", 6000, 60)
        if retry:
            return await JSONResponse({"detail": "Too many requests; try again shortly"}, status_code=429,
                                      headers={"Retry-After": str(retry)})(scope, receive, send)
        if method in ("POST", "PUT", "PATCH"):
            headers = dict(scope.get("headers", []))
            try:
                length = int(headers.get(b"content-length", b"0"))
            except ValueError:
                length = MAX_REQUEST_BYTES + 1
            if length > MAX_REQUEST_BYTES:
                return await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_REQUEST_BYTES:
                    return await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            original_receive = receive
            sent_body = False

            async def replay_receive():
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = replay_receive
        await self.app(scope, receive, send)


class SessionStore:
    """Bounded in-process sessions. One worker only; restarts lose all games."""

    def __init__(self, limit=SESSION_LIMIT, ttl=SESSION_TTL):
        self.limit, self.ttl = limit, ttl
        self.sessions = OrderedDict()
        self.lock = threading.RLock()

    def _prune(self):
        now = time.monotonic()
        for key, (_, last_seen) in list(self.sessions.items()):
            if now - last_seen > self.ttl:
                del self.sessions[key]
        while len(self.sessions) >= self.limit:
            self.sessions.popitem(last=False)

    def create(self, game):
        with self.lock:
            self._prune()
            key = secrets.token_urlsafe(24)
            while key in self.sessions:
                key = secrets.token_urlsafe(24)
            self.sessions[key] = (game, time.monotonic())
            return key

    def get(self, key):
        with self.lock:
            item = self.sessions.get(key)
            if item is None:
                raise HTTPException(404, "Game session not found or expired")
            game, last_seen = item
            if time.monotonic() - last_seen > self.ttl:
                del self.sessions[key]
                raise HTTPException(404, "Game session not found or expired")
            self.sessions.move_to_end(key)
            self.sessions[key] = (game, time.monotonic())
            return game


sessions = SessionStore()
app = FastAPI(title="Echelon", version="0.10.0")
app.add_middleware(PublicGuard)


def ppo_ready():
    if not PPO_CHECKPOINT or not Path(PPO_CHECKPOINT).is_file():
        return False
    try:
        from .ppo_general import PPOGeneral
        PPOGeneral(Path(PPO_CHECKPOINT), "Blue")
        return True
    except Exception:  # Missing optional ML stack or incompatible local model.
        return False


def serialize_order(order):
    return {"unit_id": order.unit_id, "kind": order.kind.value,
            "target": list(order.target) if isinstance(order.target, tuple) else order.target}


def game_state(game, key):
    state = state_snapshot(game.state)
    human = game.human_army
    return {"id": key, "ruleset": "Expanded" if isinstance(game, ExpandedGame) else "Classic",
            "human_army": human, "opponent": game.opponent_name,
            "first_army": game.first_army, "deployment": game.deployment,
            "seed": game.seed, "round": game.state.completed_rounds + (not game.state.finished),
            "state": state, "legal_orders": [serialize_order(o) for o in game.human_orders()],
            "history": game.decisions,
            "rosters": game.state.rosters if isinstance(game, ExpandedGame) else None,
            "score": ({army: float(strength(game.state, army)) for army in ("Blue", "Red")}
                      if isinstance(game, ExpandedGame) else
                      {army: score(game.state, army) for army in ("Blue", "Red")}),
            "invalid_actions": game.invalid_attempts}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"board_size": 8, "max_rounds": 30,
            "analytics": {"token": POSTHOG_TOKEN, "host": POSTHOG_HOST},
            "command_maps": list(MAPS),
            "classic_opponents": ["random", "heuristic"] + (["ppo"] if ppo_ready() else []),
            "expanded_opponents": list(WEIGHTS),
            "draft": {"gold": RULES.gold, "manpower": RULES.manpower,
                      "maximum": RULES.maximum, "minimum": RULES.minimum,
                      "units": {kind: {"gold": cost, "manpower": people,
                                       "health": STATS[kind][0], "movement": STATS[kind][1],
                                       "attack_power": STATS[kind][2], "attack_range": STATS[kind][3]}
                                for kind, (cost, people) in RULES.costs.items()}}}


@app.post("/api/feedback", status_code=202)
def feedback(request: FeedbackRequest):
    # Fixed vocabulary only; never log visitor identifiers or free text.
    import logging
    logging.getLogger("uvicorn.error").info("player_feedback rating=%d category=%s",
                                            request.rating, request.category)
    return {"status": "received"}


@app.post("/api/draft/preview")
def draft_preview(request: DraftRequest):
    try:
        validate(request.roster, allow_empty=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ai_army = "Red" if request.human_army == "Blue" else "Blue"
    ai_roster = draft(request.doctrine, f"{request.seed}:draft:{ai_army}")
    return {"roster": request.roster, "remaining": remaining(request.roster),
            "ai_roster": ai_roster, "ai_army": ai_army}


@app.post("/api/draft/purchase")
def draft_purchase(request: PurchaseRequest):
    try:
        validate(request.roster, allow_empty=True)
        roster = purchase(request.roster, request.kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"roster": roster, "remaining": remaining(roster)}


@app.post("/api/draft/remove")
def draft_remove(request: RemoveRequest):
    try:
        validate(request.roster)
        roster = remove(tuple(request.roster), request.index)
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"roster": roster, "remaining": remaining(roster)}


@app.post("/api/games", status_code=201)
def create_game(request: GameRequest):
    try:
        if request.ruleset == "Classic":
            if request.roster is not None:
                raise ValueError("Classic uses its fixed three-formation roster")
            if request.opponent not in config()["classic_opponents"]:
                raise ValueError("Classic opponent is unavailable")
            game = LiveGame(request.human_army, request.opponent, request.first_army,
                            request.deployment, request.seed,
                            Path(PPO_CHECKPOINT) if request.opponent == "ppo" else None)
        else:
            if request.opponent not in WEIGHTS:
                raise ValueError("Expanded opponent must be a drafting doctrine")
            if request.deployment != "random":
                raise ValueError("Expanded requires seeded random deployment")
            roster = validate(request.roster or ())
            game = ExpandedGame(roster, request.opponent, request.human_army,
                                request.first_army, request.seed)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc
    key = sessions.create(game)
    return game_state(game, key)


@app.get("/api/games/{key}")
def get_game(key: str):
    with sessions.lock:
        return game_state(sessions.get(key), key)


@app.post("/api/games/{key}/orders")
def submit_order(key: str, request: OrderRequest):
    order = Order(request.unit_id, OrderType(request.kind), request.target)
    with sessions.lock:
        game = sessions.get(key)
        if order not in game.human_orders():
            raise HTTPException(409, "Illegal order; battle state was not changed")
        game.submit(order)
        return game_state(game, key)


@app.get("/api/games/{key}/replay")
def export_replay(key: str):
    with sessions.lock:
        game = sessions.get(key)
        if not game.state.finished:
            raise HTTPException(409, "Finish the battle before exporting its replay")
        return JSONResponse(game.recording(), headers={
            "Content-Disposition": f'attachment; filename="echelon-{key[:8]}.json"'})


@app.get("/api/replays/sample/{ruleset}")
def sample_replay(ruleset: Literal["classic", "expanded", "command"]):
    if ruleset == "classic":
        return json.loads((ROOT / "examples" / "sample_battle.json").read_text(encoding="utf-8"))
    if ruleset == "command":
        return json.loads((ROOT / "examples" / "sample_command.json").read_text(encoding="utf-8"))
    from .expanded_game import ai_battle
    return ai_battle(("cavalry", "cavalry", "cavalry", "infantry"),
                     ("infantry", "infantry", "cavalry", "artillery"), 42)


def command_state(game, key):
    return {"id": key, **game.state()}


@app.post("/api/command", status_code=201)
def create_command(request: CommandRequest):
    try:
        game = CommandGame(request.human_army, request.opponent, request.map, request.seed, request.roster)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    key = sessions.create(game)
    return command_state(game, key)


def command_session(key):
    game = sessions.get(key)
    if not isinstance(game, CommandGame):
        raise HTTPException(404, "Command session not found")
    return game


@app.get("/api/command/{key}")
def get_command(key: str):
    with sessions.lock:
        return command_state(command_session(key), key)


@app.post("/api/command/{key}/orders")
def submit_command(key: str, request: CommandOrderRequest):
    with sessions.lock:
        game = command_session(key)
        try:
            game.order(request.ids, request.kind, request.target, request.waypoints)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return command_state(game, key)


@app.post("/api/command/{key}/control")
def control_command(key: str, request: CommandControlRequest):
    with sessions.lock:
        game = command_session(key)
        try:
            game.control(request.paused, request.speed)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return command_state(game, key)


@app.get("/api/command/{key}/replay")
def command_replay(key: str):
    with sessions.lock:
        game = command_session(key)
        if not game.battle.finished:
            raise HTTPException(409, "Finish the battle before exporting its replay")
        return game.recording()


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="website")
