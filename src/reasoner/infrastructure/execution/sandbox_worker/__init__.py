"""Sandbox worker — the only process with Docker access.

Runs as its own container in the deployment (see docker-compose.yml's
``sandbox-worker`` service), reachable from the ``backend`` API container
only over the internal Compose network with a bearer token. The API
container never touches Docker directly.
"""
