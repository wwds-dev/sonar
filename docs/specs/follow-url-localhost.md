# Spec: follow only a holder on this machine

- Status: built (branch `follow-url-localhost`, from master `68b40aa`)
- Owner approval: asked for in chat 2026-10-12 ("restrict the follow URL to localhost").
- Source: `docs/audit/untrusted-text-sweep-security.md` S-F side note: `_fetch` accepts any URL
  scheme from the engine lock, so a `file://` or remote URL there would be read and sent the
  window's changes.
- Phases: Define/Design/Architect skipped (one check at the single entry point, no state or
  concurrency change). Secure required (network).

## Change
- `sonar/core.py`: `_loopback_url(url)`: true only for `http` with host in `FOLLOW_HOSTS`
  (`127.0.0.1`, `localhost`, `::1`, equal to `server.LOOPBACK`) and a valid port. The follow loop
  (the only place a holder's URL enters `Live`) treats any other URL as no URL: read-only, not
  followed, nothing fetched or posted, and the status detail says the lock gives an address not on
  this machine (the URL `_clean`ed, capped at 80).
- `sonar/server.py`: `lock_url()` brackets an IPv6 host (`http://[::1]:8787`; `http://::1:8787`
  was not a valid URL), and `PaperServer6` binds `::1` (the base server is IPv4 only).

### Added after security review (`docs/audit/follow-url-localhost-security.md`)
- F1/F2: `_fetch`/`_post` use `_follow_opener()`: no proxy (environment or macOS system proxy,
  which does not exempt 127.0.0.1) and no redirects.
- F3: `_loopback_url` also refuses userinfo, a missing/zero/out-of-range port, surrounding
  whitespace or control characters, a path other than `/`, a query or a fragment.
- F5: `describe_conflict` survives a non-numeric `since` (it raised inside the follow loop).

## Success measure
`tests/test_follow.py`: `test_only_a_plain_http_address_on_this_machine_is_followed` (12 cases),
`test_the_follow_hosts_are_the_ones_the_server_binds_to`,
`test_a_lock_naming_another_address_is_not_followed` (`file:///etc/passwd` in the lock: not
followed, read-only, zero fetches, detail says why). Mutations, each killed: loop check off; scheme
unchecked; host unchecked; port unchecked; detail line dropped. After review: 11 more URL cases,
`test_following_uses_no_proxy`, `test_a_redirect_is_not_followed_off_the_machine`,
`test_the_lock_url_brackets_an_ipv6_host`, `test_the_server_binds_ipv6_loopback`,
`test_a_lock_with_a_bad_start_time_still_reads_as_a_conflict`; each fix's mutation dies.

## Non-goals
- Authenticating the holder (a same-user process can already write the lock).
