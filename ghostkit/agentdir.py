"""Agent folders as ghosts.

A haunt can define a ghost the same way the custodial stack defines an
agent: a folder of markdown files with YAML frontmatter (the gaia_agent
``agents/<name>/`` format — keep the two parsers in sync):

    garrick/
    ├── character.md      # frontmatter: agent_id, preset?, goal?, tick_seconds?,
    │                     #   engine? {low,high}; body: the soul
    ├── skills.md         # frontmatter: {skill_name: level, ...}
    ├── inventory.md      # frontmatter: items: [{what, affordances?}, ...]
    ├── memories.md       # frontmatter: memories: [{content, salience?, kind?}, ...]
    └── lore/*.md         # each body → one kind="lore" memory (salience 0.85)

The body of character.md is the soul; skills, inventory and memories become
BIRTH-TIME state, seeded through the gateway's organ proxy when ``ghostkit
up`` first creates the ghost — the folder is the birth certificate, not a
reset button, so a living ghost's acquired state is never clobbered by a
re-run. Spawn coordinates in the frontmatter are noted but not applied:
placing a body in the world is custodial (the owner tier cannot teleport).

Parsing needs PyYAML: ``pip install 'ghostkit[agents]'``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _yaml():
    try:
        import yaml  # noqa: PLC0415 — optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "ghostkit: agent folders need PyYAML — pip install 'ghostkit[agents]'"
        ) from exc
    return yaml


def parse_md(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into (frontmatter dict, body)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text.strip()
    meta = _yaml().safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must parse to a mapping")
    return meta, m.group(2).strip()


def is_agent_dir(path: Path) -> bool:
    return (path / "character.md").is_file()


def _read(path: Path) -> tuple[dict[str, Any], str]:
    return parse_md(path.read_text(encoding="utf-8"))


def load_agent_dir(path: Path) -> tuple[str, dict]:
    """(ghost_id, ghost config) from an agent folder.

    The returned config has the same shape as a ``*.ghost.toml`` (preset,
    soul, goal, tick_seconds, engine) plus a ``seed`` block carrying the
    birth-time state.
    """
    meta, soul = _read(path / "character.md")
    gid = str(meta.get("agent_id") or path.name).strip()
    cfg: dict[str, Any] = {
        "soul": soul,
        "goal": str(meta.get("goal") or "").strip(),
    }
    if meta.get("preset"):
        cfg["preset"] = str(meta["preset"])
    if meta.get("tick_seconds") is not None:
        cfg["tick_seconds"] = float(meta["tick_seconds"])
    if isinstance(meta.get("engine"), dict):
        cfg["engine"] = meta["engine"]

    seed: dict[str, Any] = {}

    skills_md = path / "skills.md"
    if skills_md.is_file():
        sm, _ = _read(skills_md)
        skills = sm.get("skills") if "skills" in sm else sm
        if skills:
            seed["skills"] = {str(k): float(v) for k, v in skills.items()}

    inv_md = path / "inventory.md"
    if inv_md.is_file():
        im, _ = _read(inv_md)
        if im.get("items"):
            seed["items"] = list(im["items"])

    memories: list[dict[str, Any]] = []
    mem_md = path / "memories.md"
    if mem_md.is_file():
        mm, _ = _read(mem_md)
        memories += list(mm.get("memories") or [])
    lore_dir = path / "lore"
    if lore_dir.is_dir():
        for lore_path in sorted(lore_dir.glob("*.md")):
            lm, lbody = _read(lore_path)
            if lbody:
                memories.append({"content": lbody,
                                 "salience": float(lm.get("salience", 0.85)),
                                 "kind": str(lm.get("kind", "lore"))})
    if memories:
        seed["memories"] = memories

    if isinstance(meta.get("spawn"), dict):
        seed["spawn"] = meta["spawn"]

    if seed:
        cfg["seed"] = seed
    return gid, cfg
