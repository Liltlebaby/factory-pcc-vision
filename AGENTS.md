# Workspace structure

This workspace contains two independent applications.

- `PCC/` is the Next.js Production Control Center. Read `PCC/AGENTS.md` before changing it.
- `rack_ai/` is the Python Rack AI service and Rack Monitor.

Keep model weights, datasets, training notebooks, and generated artifacts outside `PCC/`.

Deploying to the factory server from Git: follow `docs/operations/server-deploy-codex.md`.
