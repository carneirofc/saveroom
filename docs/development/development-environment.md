# Saveroom's Dev Environment

The dev environment runs Saveroom services with source code hot reloading enabled. It
also runs the backend django server and web-frontend nuxt server in debug and
development modes.

## Getting Started

Saveroom offers two development approaches. Choose based on your priorities:

| Approach | Guide |
|----------|-------|
| **Docker** | [Running with Docker](running-the-dev-env-with-docker.md) |
| **Local** | [Running Locally](running-the-dev-env-locally.md) |

## Which Should I Use?

### Use Docker if you want:

- **Quick start** - Only requires Docker and `just`, no language runtimes to install
- **Consistency** - Identical environment across all machines and OSes
- **Isolation** - Dependencies contained in images, won't conflict with other projects
- **Security** - Code runs in sandboxed containers

### Use Local development if you want:

- **Speed** - Faster startup, instant hot reload, no container overhead
- **Lower resources** - No Docker daemon or container memory overhead
- **Better debugging** - Direct IDE integration, native breakpoints, no remote debugging setup
- **Simpler tooling** - Standard Python/Node workflows you already know

Both approaches use the same `just` commands and can be switched between freely.

## Quick Start

- **Docker development**: `just dc-dev up -d` - runs all services in Docker containers
- **Local development**: `just dev` - runs services natively with Docker only for db/redis

## Further Reading

- [Running with Docker](running-the-dev-env-with-docker.md) - Complete Docker setup and commands
- [Running Locally](running-the-dev-env-locally.md) - Complete local development setup
- [justfile reference](justfile.md) - All available `just` commands
- [Running tests](running-tests.md) - Testing guide
- [IntelliJ setup](intellij-setup.md) - Configure IntelliJ for Saveroom development
- [VS Code setup](vscode-setup.md) - Configure VS Code for Saveroom development
- [Feature flags](feature-flags.md) - Optionally enabling unfinished features
- [Saveroom Docker API](../installation/install-with-docker.md) - Docker setup configuration

## Fixing git blame

A large formatting only commit was made to the repo when we converted to use the black
auto-formatter on April, 12 2021. If you don't want to see this commit in git blame, you
can run the command below to get your local git to ignore that commit in blame for this
repo:

```bash
$ git config blame.ignoreRevsFile .git-blame-ignore-revs
```
