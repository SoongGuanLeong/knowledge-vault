# Infrastructure Standards

These standards were written on June 2, 2026 using Context7. Verify currency before project start if found older than 6 months.

## Docker
- All services use `docker compose` (v2 syntax, not `docker-compose`).
- Shared services live in `infra/docker/`.
- Add healthchecks to all long-running services.

## Networking
- Use a semantically named network (e.g., `<project>-net`, `data-platform-net`).
- Create multiple networks if isolation requires it (e.g., `app-net`, `data-net`).
- Services may join multiple networks if needed.

## Secrets
- No hardcoded secrets.
- Use `.env` files (gitignored).
- Provide `.env.example`.

## Container Hardening
- Set resource limits: `mem_limit`, `cpus`.
- Run as non-root user.
- Use specific image tags, not `latest`.

## Execution
- Use Makefile only.
- No raw docker commands in workflows.