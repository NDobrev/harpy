# Web transport layer

Browser HTTP/SSE contracts and, later, the FastAPI app. Import `harpy.models`
and application facades only. Never import `harpy.semantic`, `harpy.storage`,
`harpy.evidence`, `harpy.github`, `harpy.verification`, or `harpy.git`.

- DTOs reject unknown fields and use snake_case.
- `RequestContext` is created by trusted server code, never deserialized from a browser.
- Do not expose unfinished endpoints as working features.
- No live provider calls from this package.
