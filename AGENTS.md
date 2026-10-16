# Saveroom

FOSS fork of Baserow: a no-code database and application platform. Django backend + Nuxt/Vue frontend, run with Docker Compose and shipped via a Helm chart.

## DOX contract

AGENTS.md files are binding contracts for their subtrees.

- Before editing, read every AGENTS.md on the path from the root to each file you touch. The closest doc controls local details; no child may weaken a parent.
- After a meaningful change, update the nearest owning AGENTS.md when it alters scope, contracts, workflows, constraints or user preferences, and refresh any affected Child DOX Index. Delete stale text rather than annotating it.
- Keep docs short and operational: stable contracts, not history. Broad rules go in parents, concrete detail in children; don't repeat a rule across files.
- Child doc sections, in order: Purpose, Ownership, Local Contracts, Work Guidance, Verification, Child DOX Index. Leave Work Guidance/Verification empty when no standard or check exists.

## User preferences

- Scrub pointers, branding and infra ties back to Baserow B.V.; never reintroduce them.
- The product is **Saveroom** ("the safe room for your tables"). Rename only what users and operators see; internal `baserow` identifiers stay (Python package, `BASEROW_*` env vars, API paths, protocol headers, DB/app labels, `local_baserow` types, the `baserow-icon` CSS prefix, the Helm chart's base resource name).
- Keep the MIT attribution to Baserow B.V. (`LICENSE`, file headers, version panel credits, README "Meta" section): it is a license obligation, not branding.

## Layout

`backend/` (Django API + workers), `web-frontend/` (Nuxt app), `e2e-tests/` (Playwright), `deploy/` (all-in-one image + Helm), `docs/`, `changelog/`, `.agents/skills/` (project skills; `.claude/skills` symlinks here).

## Repo-wide rules

- Task runner is `just` (root `justfile` dispatches to per-area justfiles): `just lint`, `just test`, `just fix`; `just backend …`, `just frontend …`, `just e2e …`, `just changelog …`.
- Every user-facing or behavioral change needs a changelog entry (`just changelog add`, see `changelog/AGENTS.md`).
- Commits use Conventional Commits; never add a `Co-Authored-By` or tooling-attribution trailer. `.pre-commit-config.yaml` gates lint/format.
- CVE gate: `just audit deps` (every `uv.lock`/`yarn.lock`) and `just audit images <refs>` run the pinned Trivy image and fail on fixable HIGH/CRITICAL findings; CI enforces the same. Fix by upgrading (yarn `resolutions`, uv constraints); a suppression goes in `.trivyignore.yaml` with a `statement` and `expired_at`. Keep the Trivy version identical in the root `justfile`, `ci.yml` and `build-publish-image.yml`.

## Child DOX Index

- [`backend/AGENTS.md`](backend/AGENTS.md) — Django API, core, contrib domains, workers, migrations, pytest.
- [`web-frontend/AGENTS.md`](web-frontend/AGENTS.md) — Nuxt/Vue modules, components, i18n, branding, Vitest.
- [`e2e-tests/AGENTS.md`](e2e-tests/AGENTS.md) — Playwright suite and its Dockerized stack.
- [`deploy/AGENTS.md`](deploy/AGENTS.md) — all-in-one image, Caddy image, Helm chart, image build rules.
- [`docs/AGENTS.md`](docs/AGENTS.md) — user/developer docs site and ADRs.
- [`changelog/AGENTS.md`](changelog/AGENTS.md) — conflict-free changelog generator.
- [`.agents/skills/AGENTS.md`](.agents/skills/AGENTS.md) — project skills.
