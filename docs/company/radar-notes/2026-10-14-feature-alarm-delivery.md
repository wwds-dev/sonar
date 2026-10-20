# Radar check: feature, alarm-delivery (2026-10-14)

Scope: off-machine alarm for the launchd agent via ntfy push (HTTPS POST, private topic), daily
heartbeat, `notify_failures` in `/api/health`; diagnose `osascript display notification` timeouts
(45/47 in `~/Library/Logs/SONAR/agent.err.log`). Read: app-context Stack + Security surface,
`pyproject.toml` (stdlib only), `packaging/com.netrunner3000.sonar.plist`, playbooks (all `baseline`).

| Finding | Source | Impact | Recommendation | Approval needed |
|---|---|---|---|---|
| ntfy publish is a plain HTTP POST/PUT to `https://ntfy.sh/<topic>` with `X-Title`, `X-Priority` (1-5), `X-Tags` headers; fits SONAR's stdlib-only rule (`urllib`), no new dependency | https://docs.ntfy.sh/publish/ (read 2026-10-14) | P2 | adopt | none (no package) |
| On ntfy.sh without an account "the topic is essentially a password": anyone who knows it can read and post. Treat the topic as a secret (Keychain/`.env` in Application Support, never in repo, logs or `/api/health`); use a long random topic; access-token auth (`Authorization: Bearer`) exists if the owner later reserves the topic | https://docs.ntfy.sh/publish/ | P1 (secret handling) | adopt | Secure phase required (network + secret) |
| Alarm text leaves the machine. Keep bodies to generic status ("no price poll for 14 min"), no balances, positions or P&L | app-context Invariants; ntfy.sh is a third-party host | P1 (privacy) | adopt | owner OK on what text leaves the Mac |
| CVE-2026-39087 (GO-2026-5551): SSRF in the ntfy **server** < 2.22.0, published 2026-04-23. Affects self-hosting only; a client POSTing to ntfy.sh is not affected | https://osv.dev/vulnerability/GO-2026-5551 | P3 | watch: if self-hosting, run >= 2.22.0 | none |
| launchd `ProcessType Background` applies resource limits meant to keep the job from disturbing the user (CPU and I/O throttling); Apple recommends ProcessType over `Nice`. Plist sets both (`Background`, `Nice 5`), which plausibly explains slow osascript and 3-24 s health on a loaded Mac | `launchd.plist(5)`, https://keith.github.io/xcode-man-pages/launchd.plist.5.html | P1 (item 2 of tier-3; relevant to cause) | adopt: consider `Standard` (or `Adaptive`) and drop `Nice`; decide in Architect / tier-3 item 2 | architect, owner gate |
| osascript notifications are attributed to Script Editor; on macOS 26 there are reports of `display notification` silently not showing. No Apple doc covers a timeout from a launchd agent. Cause stays "not verified" until tested in the agent's context | https://developer.apple.com/forums/thread/808496 ; forum reports | P1 | adopt: diagnose in the agent's own context (`launchctl asuser`) and count failures; never rely on the banner alone | none |

## Checked, nothing new
- No better-fitting connector or plugin is needed. ntfy's phone app (iOS/Android, free) is the only install, and it's on the owner's phone, not in SONAR.
- Alternatives (Pushover, Telegram bot, SMTP) need an account or token plus more secrets. ntfy is the simplest match for the owner's choice.

## Stack pass (2026-10-14, before Architect)
This reuses the findings above. The stack choices are all built into Python or macOS:
- **HTTP:** stdlib `urllib.request`. No dependency.
- **Topic storage:** the Keychain, via `/usr/bin/security find-generic-password -w`. It is built into macOS. A launchd agent can read the user's login keychain while the user is logged in. That access has not been verified in the agent's own context, so the engineer must test it there.
- **launchd:** the ProcessType finding goes to tier-3 item 2.

Checked, nothing new: no library is needed, and none was proposed.
