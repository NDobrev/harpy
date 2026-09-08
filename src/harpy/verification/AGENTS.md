# Verification layer

Optional Docker runner from trusted user profiles.

- The analyzer must never call this package.
- Profiles live in user configuration. A PR cannot define a trusted command.
- Live Docker tests stay outside `make check`.
