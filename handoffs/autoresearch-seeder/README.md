# AutoResearch Seeder — GLM implementation handoff

Read [HANDOFF.md](HANDOFF.md) first. This folder transfers the Mac Mini source references to the MacBook Air. No Mac Mini filesystem access is required.

## Contents

- HANDOFF.md: implementation requirements, constraints and acceptance tests.
- reference/: supporting source snapshot with original repository-relative layout. This includes untracked modules that were missing from the GitHub main branch.
- MANIFEST.sha256.json: original source-file SHA-256 hashes; paths are relative to reference/.

## Working on the MacBook Air

Fetch branch `handoff/autoresearch-seeder`, then create your implementation branch from it, e.g. `implementation/autoresearch-seeder`. Work in the checkout you actually have; replace machine-specific assumptions with checkout-relative paths.

The reference/ directory is a snapshot, not an installed Python package. Inspect and selectively integrate needed files into the normal repository paths before implementing scripts/autoresearch_seeder/. Compare any existing local changes first. Some snapshots refer to omitted upstream packages or task data.

No API keys, credential files, live run histories, improved candidate artifacts, large competition data, virtual environments or upstream DreamRSI checkout are included. Obtain dependencies/data separately when needed. Offline implementation/testing does not require private Mac Mini credentials.

Deliver a disabled configuration and tested implementation; do not start paid research jobs or change production campaigns. Codex will review and run the bounded MiniMax acceptance test afterward. Push your completed implementation branch and provide its name/commit.
