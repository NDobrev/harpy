# Identity and access

Principals, memberships, grants, and capability checks. No rendering and
no browser credential persistence.

- `RequestContext` / access context is created by trusted server code.
- Membership is `(issuer, subject)`, never email.
- Least privilege of role and repository grant.
- Do not import `harpy.web`, `harpy.storage`, `harpy.semantic`, or `subprocess`.
