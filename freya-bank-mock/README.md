# Freya final bank mock — infrastructure only

The final pack includes the 2026-10-01 service contract and test-environment
lookup table. This Worker implements the seven `POST /voice/v1/...` routes from
that contract. Fixture bodies, HTTP status codes and `delaySeconds` come from
`final/test-environment/test-customers.json` without alteration. No database
or invented state is used. `GET /health` returns `bankServicesReady: true`.

```sh
npm ci
npm test
npm run build
npm run dev
npm run deploy
```

Keep the source documents unchanged. If sources conflict, record the file and
version involved before choosing an interpretation. The JSON description used
to name the fixture keys differently; the actual keys are `http`, `response`
and optional `delaySeconds`, matching the current test-environment overview.

The Worker is deployed as
`freya-bank-mock-final-20261011-9a3f21` at
`https://freya-bank-mock-final-20261011-9a3f21.freya-bank-mock-25.workers.dev`.
Live HTTPS checks returned HTTP 200 with `bankServicesReady: true` for
`/health`, and one fixture-exact live response from each of the seven routes.
Local HTTP tests cover all 617 fixture leaves and one delayed response.
