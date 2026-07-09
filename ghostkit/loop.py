"""The embodied loop — your ghost's mind, running on your keys.

Each tick mirrors the reference orchestrator: read the body (energy, skills,
inventory affordances, salient memories) through the gateway's organ proxy,
let the LOW engine choose an action (with a bare-word fallback for terse
models), optionally let the HIGH engine veto infeasible attempts, then act —
and pay for it: every affordance resolves through ``world.act`` into a real
success/failure, every outcome becomes a memory, every token drains energy,
and every (belief, outcome, order) triple lands in the calibration organ.
"""
from __future__ import annotations

import random
import re
import time

_DIRECTIONS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
_PRED_MIN, _PRED_MAX = 0.05, 0.95


def _clamp_conf(difficulty) -> float:
    try:
        d = float(difficulty)
    except (TypeError, ValueError):
        d = 0.0
    if d != d or d == float("inf"):
        return _PRED_MIN
    return max(_PRED_MIN, min(_PRED_MAX, 1.0 - d))


def _finite(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 999.0 if (v != v or v in (float("inf"), float("-inf"))) else v


def _tod() -> str:
    return time.strftime("%H:%M")


def _system_prompt(meta: dict) -> str:
    soul = (meta.get("soul") or "").strip() or \
        "You are a person in a medieval fantasy world."
    return (soul + " Act in character toward your goal. Choose ONE action from the list. "
            "Answer with exactly one line: ACTION: <name>")


def _user_prompt(aid: str, meta: dict, energy: dict, mems: list, actions: list[str],
                 low_energy: bool) -> str:
    goal = (meta.get("goal") or "").strip()
    recent = "; ".join(m.get("content", "") for m in mems[:3]) or "nothing"
    urgency = "\nYou are exhausted — seek rest soon." if low_energy else ""
    return (f"You are {aid}. Energy: {energy.get('energy')}. Time {_tod()}.{urgency}\n"
            + (f"Your goal: {goal}\n" if goal else "")
            + f"Recently: {recent}.\nAvailable actions:\n"
            + "\n".join(f"- {a}" for a in actions) + "\nReply: ACTION: <name>")


def _pick_action(engine, sysmsg: str, usrmsg: str, actions: list[str], charge) -> tuple[str | None, str]:
    raw, usage = engine.chat([{"role": "system", "content": sysmsg},
                              {"role": "user", "content": usrmsg}])
    charge(usage)
    m = re.search(r"ACTION:\s*([A-Za-z_.]+)", raw)
    pick = m.group(1).split(".")[-1].lower() if m else None
    if not pick and raw:
        pick = next((a for a in actions if a in raw.lower()), None)
    if not pick:
        # bare-word fallback: terse local models answer a single word
        bare = (f"Which do you do next? Choose one word from: {', '.join(actions)}. One word only.")
        braw, busage = engine.chat([{"role": "system", "content": "You answer with exactly one word."},
                                    {"role": "user", "content": bare}])
        charge(busage)
        word = braw.strip().split()[0].strip(".,!:;\"'").lower() if braw.strip() else ""
        if word in actions:
            pick, raw = word, braw
    return pick, raw


def run_loop(ghost, engine_low, engine_high=None, *, tick_seconds: float = 5.0,
             max_ticks: int = 0, on_tick=None) -> None:
    aid = ghost.id
    meta = ghost.meta
    heading = random.choice(_DIRECTIONS)
    n = 0

    def charge(usage: dict) -> None:
        pt, ct = int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)
        if pt or ct:
            ghost.organ("energy", "consume_tokens", prompt_tokens=pt, completion_tokens=ct)

    while max_ticks == 0 or n < max_ticks:
        n += 1
        outcome = "?"
        try:
            energy = ghost.organ("energy", "get_energy") or {}
            level = float(energy.get("energy", 1.0) or 0)
            if level < 0.1:                       # critical: the body overrides the mind
                ghost.organ("energy", "rest", hours=2)
                outcome = "rest (critical energy — no thought spent)"
            else:
                affs = ghost.organ("inventory", "get_relevant_tools", include_unavailable=True) or []
                mems = ghost.organ("memory", "recall", limit=6) or []
                by_short = {str(a["tool"]).split(".")[-1]: a for a in affs}
                actions = ["rest", "wait", "walk"] + sorted(by_short)
                pick, raw = _pick_action(engine_low, _system_prompt(meta),
                                         _user_prompt(aid, meta, energy, mems, actions, level < 0.3),
                                         actions, charge)
                pick = pick or "wait"

                vetoed = False
                aff = by_short.get(pick)
                if aff is not None and engine_high is not None and aff.get("skill"):
                    skills = ghost.organ("skills", "get_skills") or {}
                    q = (f"An adventurer will attempt to {pick}. Relevant skill "
                         f"{aff['skill']} = {skills.get(aff['skill'], 0)}, needed "
                         f"{aff.get('required_level')}. Feasible right now? Answer YES or NO.")
                    verdict, vusage = engine_high.chat(
                        [{"role": "system", "content": "You are a terse feasibility judge. Answer YES or NO only."},
                         {"role": "user", "content": q}])
                    charge(vusage)
                    v = verdict.lower()
                    vetoed = ("no" in v) and ("yes" not in v)

                if vetoed:
                    outcome = f"{pick} vetoed by the judge → waited"
                elif pick == "rest":
                    r = ghost.organ("energy", "rest", hours=1)
                    outcome = f"rested → energy {round(float(r.get('energy', 0)), 2)}"
                elif pick == "wait":
                    outcome = "waited"
                elif pick == "walk":
                    if random.random() < 0.3:
                        heading = random.choice(_DIRECTIONS)
                    r = ghost.organ("world", "walk", direction=heading) or {}
                    outcome = f"walked {heading} ({'ok' if r.get('status') == 'ok' else 'blocked'})"
                elif aff is not None:
                    pred = _clamp_conf(aff.get("difficulty", 0.0))
                    order = int(aff.get("order", 0))
                    rec = ghost.organ("calibration", "record_prediction",
                                      kind="tick_action", affordance_order=order,
                                      model=f"ghostkit:{engine_low.model}",
                                      predicted_confidence=pred, action=aff["tool"],
                                      state_summary=f"tod={_tod()}")
                    res = ghost.organ("world", "act", action=aff["tool"],
                                      difficulty=_finite(aff.get("difficulty", 0.0)),
                                      order=order, tod=_tod()) or {}
                    ok = bool(res.get("success"))
                    if rec and rec.get("prediction_id"):
                        ghost.organ("calibration", "record_outcome",
                                    prediction_id=rec["prediction_id"],
                                    outcome=1.0 if ok else 0.0,
                                    details=f"p={res.get('p_effective')}")
                    ghost.organ("energy", "consume_action", action=pick)
                    outcome = f"{pick} → {'success' if ok else 'failure'} (p={res.get('p_effective')})"
                else:
                    outcome = f"chose unknown action {pick!r} → waited"

                ghost.organ("memory", "remember", content=f"{pick}: {outcome}",
                            salience=0.6, kind="episodic")
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad tick shouldn't kill the ghost
            outcome = f"tick error: {exc}"

        line = f"[{aid} tick {n}] {outcome}"
        print(line, flush=True)
        if on_tick:
            on_tick({"tick": n, "outcome": outcome})
        time.sleep(tick_seconds)
