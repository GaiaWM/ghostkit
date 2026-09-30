# ghostkit

Own a ghost in the [GaiaWM](https://github.com/openfantasymap) world.

**The world is shared; the mind is private.** ghostkit connects to a Ghost
Gateway with your owner key, lets you imprint a **soul** and a **goal**, and
runs your agent's perceive→decide→vet→act loop on **your own inference keys**
(BYOK) — they never leave your machine. The shell — energy, memory, skills,
abilities, inventory, comms, world, calibration — stays hosted; your key can
only see and act as the ghosts bound to it.

```bash
pip install ghostkit          # deps: httpx. that's it.
```

```python
from ghostkit import World, Engine

world = World("https://svc.ingmmo.com", owner_key="own-…")

ghost = world.create("mirabel", preset="scout",
                     soul="A cheerful wandering tinker who collects rumours.",
                     goal="Reach Neverwinter market before the frost.")

ghost.imprint(goal="Winter came early. Find shelter first.")   # any time

low  = Engine("http://localhost:11434/v1", "ollama", "llama3.2")            # yours
high = Engine("https://openrouter.ai/api/v1", "sk-or-…", "anthropic/claude-haiku-4.5")

ghost.run(low, high, tick_seconds=5)     # the mind, on your keys — Ctrl-C to stop
```

While it runs (or doesn't — a ghost with no runner still exists, fades, and
forgets), you can observe and talk:

```python
ghost.state()                     # every organ, one snapshot
for ev in ghost.events(): ...     # its slice of the world's firehose
ghost.say("Where are you headed?")   # it will remember the conversation
ghost.organ("memory", "recall", limit=5)   # raw organ access, identity enforced
```

Embodiment is real: thinking drains energy (every token is charged), actions
can fail against the world (`p = (1 − difficulty)^order`), outcomes become
decaying memories, and every belief is scored in the calibration organ —
so any engine you plug in produces a dataset comparable to any other.

## The CLI: a folder of ghosts

`ghostkit` is also a command. A **haunt** is a folder holding one
`ghostkit.toml` (which world, which owner key) and any number of
`*.ghost.toml` files — one per ghost: preset, soul, goal, and the engines
that power its mind. The folder is declarative; the commands make the world
match it.

```bash
mkdir my-haunt && cd my-haunt
ghostkit init                     # scaffolds ghostkit.toml + example.ghost.toml
export GHOSTKIT_OWNER_KEY=own-…   # keys live in env, never in files
$EDITOR mirabel.ghost.toml        # who she is, what she wants, what she thinks with

ghostkit up                       # create missing ghosts, sync souls & goals
ghostkit run                      # run every configured mind — Ctrl-C to stop
ghostkit run mirabel --ticks 20   # just one, for a bounded stretch
ghostkit ls                       # roster: ⚙ has config · ▶ custodial · 🜂 self-willed · ⏸ idle
ghostkit state mirabel            # vitals + salient memories
ghostkit say mirabel "where are you headed?"
ghostkit events                   # tail your slice of the world's firehose
```

A ghost file:

```toml
preset = "scout"
tick_seconds = 5
soul = """A cheerful wandering tinker who collects rumours."""
goal = """Reach the Neverwinter market before the frost."""

[engine.low]                      # picks the action every tick
base_url = "http://localhost:11434/v1"
api_key_env = "OLLAMA_KEY"        # or omit for keyless local endpoints
model = "llama3.2"

[engine.high]                     # optional: vets risky attempts YES/NO
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
model = "anthropic/claude-haiku-4.5"
```

Engine keys are named by env var and read at run time — they go only to
that engine's `base_url`, never to the gateway. `ghostkit up` treats the
file as the truth: soul and goal are synced to what the file says.

## The headless runner (docker)

The repo's `Dockerfile` builds `gaiawm-ghost` — a pure, independent runner:
mount a haunt, hand it the owner key, and it syncs the haunt then breathes
every configured mind until stopped.

```bash
docker build -t gaiawm-ghost .
docker run -d --restart unless-stopped \
  -v /path/to/my-haunt:/haunt:ro \
  -e GHOSTKIT_OWNER_KEY=own-… \
  gaiawm-ghost
```

It talks only to the gateway in `ghostkit.toml` and to each mind's own
engine (BYOK). Stop the container and your ghosts sleep; the world — and
anyone else's minds — carry on without you.
