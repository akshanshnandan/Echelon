# Phase 13: Public beta analytics and stability

## Analytics and privacy

Analytics are **off by default**. A visitor can explicitly enable them in the banner or change the choice through **Privacy and analytics** in the footer. Global Privacy Control and Do Not Track keep analytics off. The choice is stored locally; the PostHog module is downloaded only after opt-in. A missing project token disables analytics. Echelon uses the browser PostHog SDK with automatic click capture, automatic pageviews, page leaves, session recording, surveys, and person profiles disabled. Its anonymous identifier stays in memory; no account identification is called. The `before_send` filter keeps only the listed event properties, the public project token, and the temporary anonymous ID. Events request no GeoIP enrichment.

| Event | When | Properties |
| --- | --- | --- |
| `page_view` | Once per in-app page transition after consent | `page` (`home`, `play`, `replay`, `lab`) |
| `play_opened` | Play page opens after consent | none |
| `battle_started` | Successful game creation | `mode`, `opponent`, Command `map` |
| `battle_completed` | First observed terminal state per game | `mode`, `opponent`, Command `map`, `winner`, `duration_seconds` |
| `replay_downloaded` | Successful replay fetch for a download | `mode`, Command `map` |
| `app_error` | Action failure or first poll failure in an error episode | `source`, broad `kind` |

`duration_seconds` is wall time from the browser's successful battle creation to its observed result, rounded to seconds. It is not the simulation clock. Per-game completion keys exist only in browser memory and are never sent. No event contains a game ID, seed, order, target, free text, URL, referrer, or raw exception. Poll responses and React renders do not create new events. Anonymous PostHog IDs can still be personal data under some laws; the opt-in and privacy choices are intentional safeguards, not a legal determination.

The optional **Give feedback** form needs no account and accepts only a 1–5 rating and one fixed topic. The API logs those two values as `player_feedback`; it stores no free text or visitor identifier in the feedback record. Hosting access logs and PostHog have their own retention policies. Before public launch, the operator should confirm the privacy controller/contact details, retention settings, regional legal basis, and whether the notice needs localization or additional rights instructions.

## PostHog setup

1. Create a PostHog project in the desired data region. Copy its **project token** and matching ingestion host from project settings. A project token is a client-side identifier, not a private API key. Never put a personal API key in the browser or repository.
2. In the production web service environment, set `ECHELON_POSTHOG_PROJECT_TOKEN` and `ECHELON_POSTHOG_HOST` (for example `https://us.i.posthog.com` or the matching EU host). The FastAPI `/api/config` endpoint supplies these public values at runtime; rebuilding the frontend is unnecessary for a token change, but deploying the changed service environment is necessary. Keep the token unset to run without analytics.
3. In PostHog, create a dashboard such as **Echelon Public Beta**. Add Trends for `page_view`, `play_opened`, `battle_started`, `battle_completed`, `replay_downloaded`, and `app_error`; break battles down by `mode`, `map`, and `opponent`. Add a funnel from `play_opened` to `battle_started` to `battle_completed`, and a duration trend using `duration_seconds`. Check that no raw URL, seed, or game ID properties appear. Avoid enabling autocapture or session replay in project-wide snippets.
4. Test with a browser that has no saved choice: no request should go to PostHog. Opt in and verify named events; opt out and verify capture stops. Check Global Privacy Control and Do Not Track separately. The local development host bypasses PostHog's bot user-agent filter so headless browser tests can verify delivery; the public host keeps that filter. Review PostHog project retention and access controls before launch.

See [PostHog's JavaScript SDK reference](https://posthog.com/docs/references/posthog-js), [product analytics guide](https://posthog.com/docs/product-analytics), and [dashboard guide](https://posthog.com/docs/product-analytics/dashboards).

## Public-demo guardrails

The single-worker API keeps at most `ECHELON_MAX_SESSIONS` sessions (default 256), expires idle sessions after `ECHELON_SESSION_TTL` seconds (default 3600), and loses them on restart. The UI offers **New battle** when a Classic, Expanded, or Command session expires. Command polling stops while paused, after completion, and after expiration. The API rejects request bodies over 16 KiB, including chunked bodies, before JSON parsing. In-memory rate buckets allow 12 creations, 120 other writes, 360 ordinary reads, 3000 Command polls, and 30 replay exports or generated Expanded samples per minute per network address; feedback permits five requests per hour. A separate global cap is 6000 API requests per minute. Health checks are exempt. Responses use 429 with `Retry-After` or 413 for oversized bodies.

These controls are process-local and use a salted in-memory digest of the connection address, not a persisted visitor profile. Behind a proxy, several visitors may share a bucket; a caller can also change networks. This is basic demo protection, not a distributed WAF or durable abuse system. Observe 429 rates and server load during beta before raising capacity. Do not add workers or instances without shared sessions and coordinated limits.

## Production and custom domain steps

The existing `render.yaml` and free plan are unchanged. In the Render service's **Environment** page, add the public PostHog token and host. Render's save options differ: **Save only** waits for a later deployment, while **Save and deploy** activates the environment. Keep any secret service credentials out of `render.yaml` and the repository. Review `ECHELON_MAX_SESSIONS` and `ECHELON_SESSION_TTL` only if beta load measurements justify changes. See [Render environment variable instructions](https://render.com/docs/configure-environment-variables.md).

After separately acquiring a domain and approving any cost, open the service's **Settings → Custom Domains**, add the domain, configure the DNS records specified for that DNS provider, remove conflicting AAAA records, and use **Verify**. Render then provisions TLS and redirects HTTP to HTTPS. Its domain allowance and overage pricing depend on the workspace plan, so confirm the current allowance before adding domains. Test `/api/health`, privacy choice, all three live game modes, replay downloads, and session recovery at the assigned `onrender.com` and custom URLs. See [Render custom domains](https://render.com/docs/custom-domains.md). This phase does not purchase a domain, change a paid plan, merge, or deploy.
