# gaiawm/ghost — Form A of DISTRIBUTION.md: the pure, independent ghost runner.
#
# ghostkit + an entrypoint, nothing else. Mount a haunt folder at /haunt,
# provide the owner key via env, and the container syncs the haunt to the
# world (`ghostkit up`) then breathes every configured mind (`ghostkit run`).
# The container talks ONLY to the Ghost Gateway URL in the haunt's
# ghostkit.toml with the owner key, and to each mind's own engine base_url
# with its own key (BYOK). Your machine sleeps → your ghosts sleep.
#
#   docker build -t gaiawm-ghost .
#   docker run -d --restart unless-stopped \
#     -v /path/to/my-haunt:/haunt:ro \
#     -e GHOSTKIT_OWNER_KEY=own-... \
#     gaiawm-ghost
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src
COPY pyproject.toml README.md ./
COPY ghostkit ./ghostkit
RUN pip install --no-cache-dir .

WORKDIR /haunt
ENTRYPOINT ["/bin/sh", "-c", "ghostkit up && exec ghostkit run"]
