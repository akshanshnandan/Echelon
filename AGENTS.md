# Echelon development rules

- Read the existing architecture, README, and relevant documents before changing code.
- Preserve the deterministic battle engine unless the user explicitly requests a game rule change. Document any rule change and its effect on prior comparisons.
- Keep the original research environment, observation/action encoding, sparse reward baseline, and saved checkpoint compatibility intact unless a requested experiment explicitly changes them.
- Never use reserved final-test scenarios for training, tuning, or checkpoint selection. Freeze model choices before opening a new final-test pool.
- Keep simulation, commander logic, training, evaluation, recording, and visualization in separate modules. The viewer reads recordings; it does not run combat.
- Add meaningful tests for new functionality and run the relevant tests before committing. Run the full suite for completed development phases.
- After successfully completing a development phase, review `git diff` and `git status`, make a meaningful Git commit, and push it to the configured GitHub remote.
- Do not commit or push when tests fail.
- Never force-push, expose secrets, remove unrelated remote work, or commit large local training runs without a specific distribution plan.
- If authentication or a remote conflict blocks pushing, report the exact issue and preserve all local work. Do not bypass the block by overwriting history.
- In every final Codex summary, state the GitHub branch, commit SHA, push status, test results, and changed files.
