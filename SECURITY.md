# Security

SONAR is a free, open-source paper-trading demo maintained by one person. It cannot place
real orders (`sonar/alpaca.py` refuses any non-paper host), but it handles API keys and runs a
localhost-only HTTP server, so security reports are welcome.

## Report privately

Use GitHub's private report form: **Security → Report a vulnerability** on
<https://github.com/wwds-dev/sonar/security/advisories/new>. Please do not open a public issue
for a vulnerability.

Include the version (the window title, e.g. `v2.370`), what you did, and what happened.

## What to expect

- **Acknowledgement within 7 days.**
- **A first assessment within 14 days**, and a fix or a written reason within 90 days.
- No bounty, and no service-level promise beyond this: one person keeps this project, in
  their own time. If a deadline slips, the report gets a reply saying so.
- Credit in the CHANGELOG if you want it.

## Supported versions

Only the latest build on `master` is supported. There are no binary releases; SONAR is
distributed as source.

## Scope

In scope: this repository, and the nested modules `sonar/macro` and `sonar/playmaker`.
Out of scope: vulnerabilities in Qt, PySide6, Python or the data providers themselves
(report those upstream), and anything that needs an attacker who already controls your Mac.
