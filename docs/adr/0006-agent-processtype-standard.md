# 0006. The headless agent runs at launchd ProcessType Standard, without Nice

- Status: accepted 2026-10-19 (Architect gate approved by the owner)
- Date: 2026-10-19
- Spec: `docs/specs/starved-engine.md` (Architecture A1)

## Context
The plist was created with `ProcessType Background` + `Nice 5` in `75956b6` (2026-08-05, "autosync"). The only
rationale is the comment "a background poller, not interactive work". On the owner's shared, heavily loaded Mac this
starved the agent:
- `/api/health` took 3-24 s;
- the 4 s poll ran up to 22 s late;
- 6 of 10 `osascript` probes in that job class took over 10 s, against 0 of 10 under `Standard` at a higher load
  (`docs/audit/alarm-delivery-osascript-diagnosis.md` §4).

Apple's `launchd.plist(5)` recommends `ProcessType` over `Nice`. `Adaptive` only helps XPC services, and `Interactive`
is meant for apps. Reverting is cheap in code, but each change reaches the agent only through a restart of the live
engine. During the 30-day paper run, that restart is scarce.

## Decision
`packaging/com.netrunner3000.sonar.plist` sets `ProcessType Standard` and carries no `Nice` key. Tests pin this on the
template and on the plist that `scripts/install_agent.sh` renders. Because the installer rebuilds the plist from the
template, no stale key can survive an install.

## Consequences
- The agent competes on equal terms with the owner's interactive work. Its CPU use is near zero, so the expected change
  is *when* it runs, not how much. Measure 3 bounds this at ≤ 5 % of one core.
- Under extreme load everything is still slow. This does not promise latency at load 180.
- If poll outages persist, providers are the cause, and the follow-up is a different item.
- Rejected: keeping `Background` and raising client timeouts. That hides slowness and touches the trade-forwarding
  `_post` path.
- Rejected: `Adaptive`, which behaves as Background without XPC.
- Rejected: dropping only `Nice`. Background's I/O and CPU throttling remain (not measured separately).
