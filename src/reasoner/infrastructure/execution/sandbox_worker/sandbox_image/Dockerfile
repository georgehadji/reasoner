# Minimal non-root Python image used ONLY as the per-job sandbox container.
# Built and tagged as reasoner-sandbox-python:latest — referenced by
# infrastructure/execution/runners/python_runner.py. Never used to run the
# API or the sandbox worker itself; docker_runner.py launches one of these
# per execution request and removes it (--rm) when the job finishes.

FROM python:3.12-slim

# No package manager access is needed at runtime (--network none in
# docker_runner.py prevents any install anyway) — strip apt metadata to
# shrink the attack surface and image size.
RUN rm -rf /var/lib/apt/lists/*

# Low, fixed non-root UID/GID — matches _SANDBOX_UID/_SANDBOX_GID in
# docker_runner.py, which also passes --user explicitly so a misbuilt or
# retagged image can't silently run as root.
RUN groupadd -g 65532 nonroot \
    && useradd -u 65532 -g nonroot -M -s /usr/sbin/nologin nonroot
USER nonroot

WORKDIR /tmp
ENTRYPOINT ["python3"]
