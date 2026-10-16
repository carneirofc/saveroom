# changelog

## Purpose

Conflict-free changelog generator: each change is a standalone JSON entry, so parallel branches never collide on `changelog.md`.

## Ownership

Everything under `changelog/` (`src/`, `entries/` with its `unreleased/` staging area, `releases.json`, `tests/`). The root `changelog.md` is generated output.

## Local Contracts

- Run from the repo root via `just changelog <cmd>`; never edit `changelog.md` by hand.
- `just changelog add` writes a JSON entry to `entries/unreleased/`; `just changelog release <name>` moves them into a release and regenerates `changelog.md`.

## Work Guidance

- The `create-changelog` skill classifies domain/type and drafts the message.

## Verification

- `just changelog-test`.

## Child DOX Index

None.
