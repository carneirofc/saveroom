# docs

## Purpose

User and developer documentation, published to `https://carneirofc.github.io/baserow/` with MkDocs Material (`mkdocs.yml` at the root, `.github/workflows/docs.yml` deploys on push to `develop`).

## Ownership

Everything under `docs/`: `index.md` (entry point by reader objective), `architecture.md` (topology, repo layout, request flow), `adr/` (numbered decision records) and the topic folders.

## Local Contracts

- Nav is grouped by objective: Run, Use, Integrate, Develop, Extend. A new guide must be added to `mkdocs.yml` `nav` and the matching `index.md` section. File paths stay put when nav changes (code, Helm values and the README link to them).
- `architecture.md` must stay true to the code: update it when processes, Celery queues, proxy routes, Django apps or frontend modules change.
- ADRs are append-mostly; surface conflicts with an existing ADR instead of silently overriding it.
- Diagrams are Mermaid fenced blocks, not binary images.

## Work Guidance

- Update the doc nearest the change; add an ADR for durable architectural decisions.

## Verification

- `mkdocs build` clean of nav-coverage warnings. Links out of `docs/` (e.g. `deploy/`) are expected to warn.

## Child DOX Index

None.
