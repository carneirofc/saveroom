# e2e-tests

## Purpose

Playwright suite driving the full stack (backend, frontend, Postgres, Redis) in a real browser.

## Ownership

Everything under `e2e-tests/`: `tests/`, `pages/` (page objects), `fixtures/`, `client.ts`, `playwright.config.ts`, `justfile`, Docker wiring.

## Local Contracts

- Tests run against built CI images (`saveroom/backend:ci`, `saveroom/web-frontend:ci`) on a dedicated Docker network, not a dev server.
- Specs go through page objects in `pages/`, not ad-hoc DOM selectors.
- The DB seed is `fixtures/e2e-db.dump`; restore/dump it via justfile recipes.

## Work Guidance

- `just e2e build|up|test|down`, or `just e2e run` for all four. Prerequisites in `README.md`.

## Verification

- `just e2e run`.

## Child DOX Index

None.
