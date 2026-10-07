# AGENTS.md

Project guidance for coding agents lives in `CLAUDE.md`. Read it before working in this repository.

## Git Worktrees

These rules override any skill or plugin that tells you to isolate work in a git worktree (for example superpowers `using-git-worktrees`).

- Do not create git worktrees by default. Work in `/var/app/ingestify-to-ai` on a new branch.
- Only create a worktree when the user asks for one, or when another session is already working in this checkout. Never create worktrees as sibling folders in `/var/app/`.
- Put any worktree under `/data/tmp/ingestify/<short-name>` (for example `git worktree add -b fix/foo /data/tmp/ingestify/fix-foo main`).
- Once the branch is merged into `main`, remove the worktree (`git worktree remove <path>` then `git worktree prune`). Never use `--force` while it has uncommitted changes.
