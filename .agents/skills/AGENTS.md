# .agents/skills

## Purpose

Project skills: reusable procedures for recurring multi-layer Baserow tasks (backend layers, registries, permissions, services, formulas, notifications, tests, changelog).

## Ownership

Every skill directory here. `.claude/skills` is a symlink to this folder.

## Local Contracts

- One directory per skill containing a `SKILL.md`; the directory name must equal the frontmatter `name`, and `description` must say when to use it.
- Keep skills in sync with the code paths they reference.

## Work Guidance

- Add a skill only when a multi-file task recurs; update it when its referenced paths or steps change.

## Verification

## Child DOX Index

None.
