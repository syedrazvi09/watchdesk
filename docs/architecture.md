# Architecture

## Request path

1. The traffic generator sends requests with an `X-Tenant` header.
2. **Nginx** is the only service published to the host. It generates a unique `request_id`, forwards it to the API as `X-Request-ID`, and returns it to the client.
3. **FastAPI** validates the tenant, applies any active faults, uses Redis as a cache for the product list, and reads and writes PostgreSQL.
4. A logging middleware writes one JSON line per request with the tenant, status and latency.

## Components and what each is for

| Component | Role | What it makes possible later |
|---|---|---|
| Nginx | Edge. Logs every request that reaches the system | Telling "the app failed" apart from "the app was unreachable" |
| FastAPI | The application | 500 errors, slow endpoints, bad deploys |
| PostgreSQL | Source of truth | Connection limits, slow queries, outages |
| Redis | Disposable cache | Degraded behavior when a dependency is down |
| Traffic generator | Constant realistic activity | Incidents that happen against live traffic |
| Fluent Bit | Collects container logs | Central search without logging into containers |
| OpenSearch | Stores and indexes logs | Fast filtering by tenant, status, request and time |
| Dashboards | Search interface | Saved investigative searches |

## Logging pipeline

```text
container stdout -> Docker fluentd logging driver -> Fluent Bit (parse JSON, add service) -> OpenSearch (daily index watchdesk-logs-YYYY.MM.DD) -> Dashboards
```

- Fluent Bit parses JSON log lines into real fields. Postgres and Redis stay plain text and get a `service` field from their tag.
- An index template (`monitoring/opensearch/index-template.json`) sets field types before data arrives, so `tenant` and `request_id` are exact-match keywords and `status` and `latency_ms` support range queries.
- Docker keeps its own local copy of each container's logs in addition to what Fluent Bit ships.

## Design decisions

- **Request ID is created at Nginx**, so it exists even for requests that never reach the API.
- **Tenant is read in the logging middleware**, not only in the endpoints, so requests rejected early still get a log line.
- **Health checks do not apply faults**, so a failing customer endpoint can coexist with a passing `/health`. This is deliberate: it shows why error-rate monitoring is needed.
- **Faults live in memory** and reset on restart, so a restart always returns the system to healthy.

## Known limitations

- Fluent Bit buffers in memory, so a long OpenSearch outage can lose logs.
- Nginx logs with one-second timestamp precision and logs on completion, so its row can sort after the API row for the same request.
- Both the JSON line and the original plain-text line from Uvicorn and Nginx's default log reach OpenSearch, producing some duplicate-looking rows. The plain-text ones have no `request_id` and do not match request searches.
- Postgres does not log successful queries by default, so database activity is confirmed with the application status and direct checks.
