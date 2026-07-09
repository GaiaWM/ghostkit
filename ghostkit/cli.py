"""ghostkit CLI — run a folder of ghosts.

A *haunt* is a directory holding one ``ghostkit.toml`` (which world, which
owner key) and any number of ``*.ghost.toml`` files (who each ghost is and
which engines power its mind). The folder is declarative: ``ghostkit up``
makes the world match it, ``ghostkit run`` breathes the minds.

    ghostkit init                 scaffold a haunt in the current folder
    ghostkit ls                   your roster (and which ghosts have configs)
    ghostkit up [ID...]           create missing ghosts, sync soul & goal
    ghostkit run [ID...]          run the BYOK loop for each ghost (Ctrl-C stops)
    ghostkit state ID             one snapshot of every organ
    ghostkit say ID TEXT...       talk to a ghost (it remembers)
    ghostkit events [ID]          tail the world's firehose (owned slice)

Keys are BYOK: engine api keys are read from env vars named in the config
and go only to the engine's own base_url — never to the gateway.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import tomllib
from pathlib import Path

from ghostkit.client import Ghost, GhostKitError, World
from ghostkit.engine import Engine

WORLD_FILE = "ghostkit.toml"
GHOST_SUFFIX = ".ghost.toml"

_WORLD_TEMPLATE = """\
# ghostkit haunt — which world, which key
gateway = "https://svc.ingmmo.com"
# the owner key is read from this env var (never write keys into files):
owner_key_env = "GHOSTKIT_OWNER_KEY"
"""

_GHOST_TEMPLATE = """\
# one ghost. the filename stem is its id unless `id` says otherwise.
preset = "adventurer"        # adventurer|scout|warrior|merchant|scholar|novice
tick_seconds = 5

soul = \"\"\"
A cheerful wandering tinker who collects rumours and fixes what is broken.
\"\"\"

goal = \"\"\"
Reach the Neverwinter market before the frost.
\"\"\"

# the mind: any OpenAI-compatible endpoint, key via env (BYOK — the key goes
# only to this base_url, never to the gateway).
[engine.low]
base_url = "https://opencode.ai/zen/v1"
api_key_env = "OPENCODE_API_KEY"
model = "north-mini-code-free"

# optional second tier that vets risky attempts with YES/NO:
# [engine.high]
# base_url = "https://openrouter.ai/api/v1"
# api_key_env = "OPENROUTER_API_KEY"
# model = "anthropic/claude-haiku-4.5"
"""


# -- config ------------------------------------------------------------------

def _die(msg: str) -> "SystemExit":
    print(f"ghostkit: {msg}", file=sys.stderr)
    return SystemExit(2)


def _load_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise _die(f"{path.name}: {exc}")


def load_haunt(folder: Path) -> tuple[dict, dict[str, dict]]:
    """(world config, {ghost_id: ghost config}) for a haunt folder."""
    wf = folder / WORLD_FILE
    if not wf.exists():
        raise _die(f"no {WORLD_FILE} here — run `ghostkit init` first (folder: {folder})")
    world = _load_toml(wf)
    ghosts: dict[str, dict] = {}
    for path in sorted(folder.glob(f"*{GHOST_SUFFIX}")):
        cfg = _load_toml(path)
        gid = str(cfg.get("id") or path.name[: -len(GHOST_SUFFIX)]).strip()
        if not gid:
            raise _die(f"{path.name}: empty ghost id")
        if gid in ghosts:
            raise _die(f"duplicate ghost id {gid!r} ({path.name})")
        ghosts[gid] = cfg
    return world, ghosts


def _resolve_key(cfg: dict, what: str) -> str:
    if cfg.get("api_key"):
        return str(cfg["api_key"])
    env = cfg.get("api_key_env")
    if env:
        val = os.environ.get(str(env), "")
        if not val:
            raise _die(f"{what}: env var {env} is not set")
        return val
    return "x"  # keyless endpoints (local ollama etc.)


def _engine(cfg: dict | None, what: str) -> Engine | None:
    if not cfg:
        return None
    if not cfg.get("base_url") or not cfg.get("model"):
        raise _die(f"{what}: needs base_url and model")
    return Engine(str(cfg["base_url"]), _resolve_key(cfg, what), str(cfg["model"]),
                  timeout=float(cfg.get("timeout", 180.0)))


def connect(world_cfg: dict) -> World:
    gateway = str(world_cfg.get("gateway") or "").strip()
    if not gateway:
        raise _die(f"{WORLD_FILE}: gateway is required")
    key = str(world_cfg.get("owner_key") or "").strip()
    if not key:
        env = str(world_cfg.get("owner_key_env") or "GHOSTKIT_OWNER_KEY")
        key = os.environ.get(env, "")
        if not key:
            raise _die(f"owner key: env var {env} is not set (or put owner_key in {WORLD_FILE})")
    return World(gateway, owner_key=key)


def _pick(cfgs: dict[str, dict], ids: list[str]) -> dict[str, dict]:
    if not ids:
        return cfgs
    missing = [i for i in ids if i not in cfgs]
    if missing:
        raise _die(f"no *{GHOST_SUFFIX} config for: {', '.join(missing)}")
    return {i: cfgs[i] for i in ids}


# -- commands ------------------------------------------------------------------

def cmd_init(args) -> None:
    folder = Path(args.dir)
    folder.mkdir(parents=True, exist_ok=True)
    wf, gf = folder / WORLD_FILE, folder / f"example{GHOST_SUFFIX}"
    for path, text in ((wf, _WORLD_TEMPLATE), (gf, _GHOST_TEMPLATE)):
        if path.exists():
            print(f"· {path.name} already exists — left alone")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"✚ wrote {path.name}")
    print(f"\nnext: export GHOSTKIT_OWNER_KEY=own-…  then `ghostkit up && ghostkit run`")


def cmd_ls(args) -> None:
    world_cfg, cfgs = load_haunt(Path(args.dir))
    world = connect(world_cfg)
    roster = {g["id"]: g for g in world.ghosts()}
    ids = sorted(set(roster) | set(cfgs))
    if not ids:
        print("no ghosts — write a *.ghost.toml and `ghostkit up`")
        return
    for gid in ids:
        g = roster.get(gid)
        marks = ("⚙" if gid in cfgs else " ") + ("·" if g is None else ("▶" if g.get("running") else "⏸"))
        if g is None:
            print(f"{marks} {gid:<16} (config only — `ghostkit up` creates it)")
        else:
            en = g.get("energy")
            goal = (g.get("goal") or "").replace("\n", " ")[:60]
            print(f"{marks} {gid:<16} energy={'?' if en is None else f'{en:.2f}'}  {goal}")


def cmd_up(args) -> None:
    world_cfg, cfgs = load_haunt(Path(args.dir))
    cfgs = _pick(cfgs, args.ids)
    world = connect(world_cfg)
    have = {g["id"]: g for g in world.ghosts()}
    for gid, cfg in cfgs.items():
        soul = str(cfg.get("soul") or "").strip()
        goal = str(cfg.get("goal") or "").strip()
        if gid not in have:
            world.create(gid, preset=str(cfg.get("preset") or "adventurer"),
                         soul=soul, goal=goal)
            print(f"✚ created {gid}")
        elif (have[gid].get("soul") or "").strip() != soul or (have[gid].get("goal") or "").strip() != goal:
            Ghost(world, gid).imprint(soul=soul, goal=goal)
            print(f"✎ imprinted {gid}")
        else:
            print(f"· {gid} up to date")


def cmd_run(args) -> None:
    world_cfg, cfgs = load_haunt(Path(args.dir))
    cfgs = _pick(cfgs, args.ids)
    if not cfgs:
        raise _die(f"no *{GHOST_SUFFIX} configs here")
    cmd_up(args)  # declarative: the folder is the truth before the minds start
    world = connect(world_cfg)
    stop = threading.Event()

    def spirit(gid: str, cfg: dict) -> None:
        ghost = Ghost(world, gid)
        low = _engine(cfg.get("engine", {}).get("low"), f"{gid}: engine.low")
        high = _engine(cfg.get("engine", {}).get("high"), f"{gid}: engine.high")
        if low is None:
            raise _die(f"{gid}: [engine.low] is required to run")
        tick = float(cfg.get("tick_seconds", 5.0))

        # run_loop prints its own "[id tick n] outcome" lines; the hook is
        # only our cooperative stop signal.
        def on_tick(info: dict) -> None:
            if stop.is_set():
                raise KeyboardInterrupt

        while not stop.is_set():
            try:
                ghost.run(low, high, tick_seconds=tick, max_ticks=args.ticks, on_tick=on_tick)
                return  # max_ticks reached
            except KeyboardInterrupt:
                return
            except GhostKitError as exc:
                print(f"[{gid}] gateway error: {exc} — retrying in 10s", file=sys.stderr)
                stop.wait(10)
            except Exception as exc:  # noqa: BLE001 — a mind must not die silently
                print(f"[{gid}] {type(exc).__name__}: {exc} — retrying in 10s", file=sys.stderr)
                stop.wait(10)

    threads = [threading.Thread(target=spirit, args=(gid, cfg), daemon=True, name=gid)
               for gid, cfg in cfgs.items()]
    print(f"breathing {len(threads)} mind(s): {', '.join(cfgs)} — Ctrl-C to stop")
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nletting the minds rest…")
        stop.set()
        for t in threads:
            t.join(timeout=5)


def cmd_state(args) -> None:
    world_cfg, _ = load_haunt(Path(args.dir))
    st = Ghost(connect(world_cfg), args.id).state()
    en = st.get("energy") or {}
    print(f"{args.id} — {st.get('tod', '?')} {'☾' if st.get('is_night') else '☀'}")
    for k in ("energy", "hunger", "thirst", "stress"):
        v = float(en.get(k) or 0)
        print(f"  {k:<8} {'█' * int(v * 20):<20} {v:.2f}")
    for m in (st.get("memory") or [])[:6]:
        print(f"  ◦ [{m.get('kind', '?')}] {(m.get('content') or '')[:90]}")


def cmd_say(args) -> None:
    world_cfg, _ = load_haunt(Path(args.dir))
    print(Ghost(connect(world_cfg), args.id).say(" ".join(args.text)))


def cmd_events(args) -> None:
    world_cfg, _ = load_haunt(Path(args.dir))
    world = connect(world_cfg)
    since = "0"
    try:
        while True:
            body = world._req("GET", "/my/events", params={"since": since, "limit": 200})
            for e in body.get("events", []):
                if args.id and e.get("agent_id") != args.id:
                    continue
                print(f"{e.get('agent_id', ''):<12} {e.get('kind', ''):<14} "
                      f"{e.get('detail') or e.get('tool') or e.get('response') or e.get('error') or ''}")
            since = body.get("last_id", since)
            time.sleep(3)
    except KeyboardInterrupt:
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ghostkit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-C", "--dir", default=".", help="haunt folder (default: current)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="scaffold a haunt here").set_defaults(fn=cmd_init)
    sub.add_parser("ls", help="roster + configs").set_defaults(fn=cmd_ls)
    sp = sub.add_parser("up", help="create/sync configured ghosts")
    sp.add_argument("ids", nargs="*")
    sp.set_defaults(fn=cmd_up)
    sp = sub.add_parser("run", help="run the minds (BYOK loop)")
    sp.add_argument("ids", nargs="*")
    sp.add_argument("--ticks", type=int, default=0, help="stop after N ticks (0 = forever)")
    sp.set_defaults(fn=cmd_run)
    sp = sub.add_parser("state", help="organ snapshot")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_state)
    sp = sub.add_parser("say", help="talk to a ghost")
    sp.add_argument("id")
    sp.add_argument("text", nargs="+")
    sp.set_defaults(fn=cmd_say)
    sp = sub.add_parser("events", help="tail the firehose")
    sp.add_argument("id", nargs="?")
    sp.set_defaults(fn=cmd_events)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except GhostKitError as exc:
        raise _die(str(exc))


if __name__ == "__main__":
    main()
