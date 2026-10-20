# 0005. Off-machine alarms: ntfy.sh push from the agent, topic in the Keychain, allowlisted body

- Status: proposed (Architect gate)
- Date: 2026-10-14

## Context
The agent's only alarm is the macOS banner (`sonar/server.py:236-252`), and 45 of 47 attempts timed out.
The owner chose an in-agent ntfy push (spec `docs/specs/alarm-delivery.md`, Owner decisions 2, 4, 5, 7).
Three choices are expensive to reverse:
- **Which third party gets text from the Mac.** After it leaves, it cannot be recalled. ntfy.sh keeps messages
  for a while, and anyone who knows the topic can read them.
- **Where the topic is kept and how it is read.** The owner's phone subscribes to it. Changing it means
  re-subscribing, and a leak cannot be undone.
- **What a push may say.** Once a free-text path exists, later code tends to widen it.

## Decision
1. **Channel.** One HTTPS POST to `https://ntfy.sh/<topic>` with stdlib `urllib`. No account and no self-hosting.
   - Headers: `X-Title`, `X-Priority` (4 for alarms and "stopped"; 2 for recoveries, the heartbeat and the test alarm).
   - Redirects are not followed and environment proxies are ignored, the same as `core._follow_opener` (`sonar/core.py:66-71`).
   - Any 2xx counts as delivered; anything else counts as a failure.
   - The base URL is a constant, not a setting.
2. **Secret.** The topic is a generic password in the login Keychain: service `com.netrunner3000.sonar.ntfy`,
   account `topic`.
   - It is read with `/usr/bin/security find-generic-password -s ... -a ... -w`, once, at agent start, with a 5 s timeout.
   - It is validated against `^[A-Za-z0-9_-]{24,64}$`.
   - If it is absent, invalid, denied or times out, the push channel is `not configured`. Today's behaviour stays.
   - The owner creates the item with `security add-generic-password ... -w` and types the value at the prompt,
     not as an argument. That way the item's ACL trusts `/usr/bin/security`, which is Apple-signed and stable.
     Each ad hoc signed SONAR build has a new code identity, so a direct Security.framework call from SONAR would
     need a new Keychain approval after every build. Nobody is at the Mac to give it.
   - **What this protects (corrected at Review, security P3-1).** Because the ACL trusts `/usr/bin/security`,
     any process running as the owner can read the topic without a prompt while the login Keychain is
     unlocked. The Keychain keeps the topic out of the repo, the data directory and its copies, logs and
     `/api/health`. It is not a barrier against other code running as the same user. That residual risk is
     accepted: the topic protects alarm text that is already allowlisted.
3. **Body.** Every push is built from an allowlist of closed vocabularies, as structured fields:
   - the problem kind, mapped to a fixed phrase;
   - a whole-minute or whole-hour duration;
   - a build version that matches a regex;
   - each channel's state word;
   - the title prefix "SONAR (paper)".

   No caller can pass free text to the push channel. `problems[].text`, exception text and server text stay in the
   local log.
4. **In-agent.** The agent itself sends the push, on background sender threads. The external probe is a separate
   follow-up (Owner decision 1).

## Alternatives considered
- **Topic in Application Support `.env`.** Simpler, but it is a plain file beside the book. Any whole-directory copy
  would include it, such as Time Machine or the Drive job (which of these copy the directory is not verified).
  Any process running as the user can also read it. Rejected by the
  owner (decision 4).
- **Keychain through Security.framework (ctypes or pyobjc).** Not stdlib in practice. The ad hoc identity changes
  every build, so each new build hits a Keychain prompt that nobody answers. Rejected.
- **Pushover, Telegram or SMTP.** Each needs an account and more secrets. The radar note prefers ntfy. Rejected.
- **A reserved ntfy topic with an access token.** Stronger, because only the token holder can read or post. It needs
  an account and a second secret. It is deferred, and it is compatible with this design: it adds an
  `Authorization: Bearer` header read from a second Keychain item.
- **Pushing `problems[].text` after redaction.** A denylist cannot be proven complete (domain P1-1). Rejected for
  an allowlist.

## Consequences
- A push goes to a third-party host. If ntfy.sh is down or rate-limited, the push is lost. That is counted in
  `/api/health` (`notify.ntfy`), not hidden.
- **ntfy.sh terms and the unauthenticated topic (security P3-2, accepted by the owner 2026-10-19).**
  - The topic is the only access control. Anyone who knows it can read the pushes, and can post fake ones,
    including a fake "alive" heartbeat.
  - ntfy.sh caches messages for about 12 hours. It may log IP addresses and topics. It delivers to phones
    through Google Firebase. Source:
    https://docs.ntfy.sh/privacy/, read by the security engineer from search snippets on 2026-10-19 and not
    fetched in full.
  - The owner accepts this because the body is allowlisted: problem kind, duration, build and channel states,
    with no balances, positions, symbols, prices, error text or paths.
  - The stronger option, a reserved topic with an access token, is on the backlog (TODO.md) next to the
    external probe follow-up.
- A new problem kind added to `core.Live.health` pushes as "other problem" until someone adds a phrase. The
  allowlist test fails if a kind has no phrase, so this cannot happen silently.
- Changing the topic needs an agent restart, because it is read once.
- Whether `security` can read the login Keychain from the launchd agent's context is **not verified**. The Build
  and Verify phases must show it from the real agent context (spec measure 6 via the heartbeat). A locked Keychain
  (logged out, or after a reboot before login) means `not configured`, logged at start.
- Rolling back to an older build: its `_stopped_notice_due` rewrites `alarm.json` with only `stopped_at`, so the
  heartbeat keys are dropped. The worst result is one duplicate heartbeat on the day of the rollback.
