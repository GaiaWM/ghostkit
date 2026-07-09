"""ghostkit — own a ghost in the GaiaWM world.

The world is shared; the mind is private. ghostkit connects to a Ghost
Gateway with your owner key, lets you imprint a soul and a goal, and runs
your agent's perceive→decide→vet→act loop on YOUR inference keys (BYOK) —
they never leave your machine. The shell (energy, memory, skills, abilities,
inventory, comms, world, calibration) stays hosted.

    from ghostkit import World, Engine

    world = World("https://svc.ingmmo.com", owner_key="own-…")
    ghost = world.create("mirabel", soul="A cheerful wandering tinker…",
                         goal="Reach Neverwinter market before the frost.")
    low  = Engine("http://localhost:11434/v1", "ollama", "llama3.2")
    high = Engine("https://openrouter.ai/api/v1", "sk-or-…", "anthropic/claude-haiku-4.5")
    ghost.run(low, high, tick_seconds=5)
"""
from ghostkit.client import Ghost, GhostKitError, World
from ghostkit.engine import Engine

__version__ = "0.1.0"
__all__ = ["World", "Ghost", "Engine", "GhostKitError", "__version__"]
