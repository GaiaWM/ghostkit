"""World and Ghost — the connection to the shared shell.

Everything goes through the Ghost Gateway with your owner key; the gateway
enforces that this key can only see and act as its own ghosts.
"""
from __future__ import annotations

import time
from typing import Any, Iterator

import httpx


class GhostKitError(RuntimeError):
    pass


class World:
    """A connection to a GaiaWM Ghost Gateway."""

    def __init__(self, url: str, owner_key: str, timeout: float = 60.0):
        self.url = url.rstrip("/")
        self._key = owner_key
        self._http = httpx.Client(base_url=self.url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {owner_key}"})

    # -- plumbing ----------------------------------------------------------
    def _req(self, method: str, path: str, *, params: dict | None = None,
             json: Any = None) -> Any:
        r = self._http.request(method, path, params=params, json=json)
        try:
            body = r.json()
        except ValueError:
            raise GhostKitError(f"{method} {path} → HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            msg = body.get("error")
            if isinstance(msg, dict):
                msg = msg.get("message")
            raise GhostKitError(f"{method} {path} → HTTP {r.status_code}: {msg}")
        return body

    def organ(self, ghost_id: str, organ: str, tool: str, **params) -> Any:
        """Call one organ tool as ``ghost_id`` (identity enforced server-side)."""
        body = self._req("POST", f"/my/organ/{organ}/{tool}",
                         params={"ghost": ghost_id}, json=params)
        if not body.get("ok"):
            raise GhostKitError(f"{organ}.{tool}: {body.get('error')}")
        return body.get("result")

    # -- roster ------------------------------------------------------------
    def ghosts(self) -> list[dict]:
        return self._req("GET", "/my/ghosts")["ghosts"]

    def ghost(self, ghost_id: str) -> "Ghost":
        ids = [g["id"] for g in self.ghosts()]
        if ghost_id not in ids:
            raise GhostKitError(f"you don't own a ghost named {ghost_id!r} (you own: {ids})")
        return Ghost(self, ghost_id)

    def create(self, ghost_id: str, *, preset: str = "adventurer", soul: str = "",
               goal: str = "", mode: str = "heuristic") -> "Ghost":
        self._req("POST", "/my/ghosts", params={
            "id": ghost_id, "preset": preset, "mode": mode,
            "soul": soul, "goal": goal, "autostart": "false"})
        return Ghost(self, ghost_id)


class Ghost:
    """Your agent: a handle over its organs, identity, and (via run) its mind."""

    def __init__(self, world: World, ghost_id: str):
        self.world = world
        self.id = ghost_id

    # -- identity ------------------------------------------------------------
    def imprint(self, soul: str | None = None, goal: str | None = None) -> dict:
        return self.world._req("POST", f"/my/ghosts/{self.id}/imprint", params={
            "soul": soul if soul is not None else "",
            "goal": goal if goal is not None else ""})

    @property
    def meta(self) -> dict:
        for g in self.world.ghosts():
            if g["id"] == self.id:
                return g
        raise GhostKitError(f"ghost {self.id!r} vanished from your roster")

    # -- observation -----------------------------------------------------------
    def state(self) -> dict:
        return self.world._req("GET", f"/my/ghosts/{self.id}/state")

    def organ(self, organ: str, tool: str, **params) -> Any:
        return self.world.organ(self.id, organ, tool, **params)

    def events(self, poll_seconds: float = 3.0) -> Iterator[dict]:
        """Yield this ghost's slice of the world's event firehose, forever."""
        since = "0"
        while True:
            body = self.world._req("GET", "/my/events", params={"since": since, "limit": 200})
            for e in body.get("events", []):
                if e.get("agent_id") == self.id:
                    yield e
            since = body.get("last_id", since)
            time.sleep(poll_seconds)

    # -- conversation -----------------------------------------------------------
    def say(self, text: str) -> str:
        """Speak with your agent (its memory will keep the exchange)."""
        body = self.world._req("POST", "/aiproxy/v1/chat/completions", json={
            "model": self.id, "messages": [{"role": "user", "content": text}]})
        return (((body.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""

    # -- the mind -----------------------------------------------------------
    def run(self, engine_low, engine_high=None, *, tick_seconds: float = 5.0,
            max_ticks: int = 0, on_tick=None) -> None:
        """Run the embodied loop on YOUR engines. Blocks; Ctrl-C to stop."""
        from ghostkit.loop import run_loop
        run_loop(self, engine_low, engine_high, tick_seconds=tick_seconds,
                 max_ticks=max_ticks, on_tick=on_tick)
