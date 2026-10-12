# Logging Standard

Every request log is one JSON object on one line, written to stdout.

## Fields

| Field | Type | Notes |
|---|---|---|
| `timestamp` | string (ISO 8601, UTC) | When the service logged the event |
| `level` | string | `INFO` for 1xx-4xx, `ERROR` for 5xx, `WARNING` for operational events such as a fault toggle |
| `service` | string | `api` or `nginx`. Added by Fluent Bit for other services |
| `request_id` | string | Created at Nginx. `unknown` if a call bypassed Nginx |
| `tenant` | string | From `X-Tenant`. `none` (API) or empty (Nginx) if missing |
| `method` | string | HTTP method |
| `path` | string | Request path without the query string |
| `status` | integer | HTTP status code |
| `latency_ms` | float | API only. Time spent in the application, in milliseconds |
| `request_time` | float | Nginx only. Total time in seconds |
| `upstream_status` | string | Nginx only. Status returned by the API. Empty if there was no answer |
| `message` | string | Short human-readable summary. For failures it includes the exception |

## Levels

- `INFO`: normal behavior, including client errors (4xx). A 404 means the server handled a bad request correctly.
- `WARNING`: something operationally significant happened that is not a request failure.
- `ERROR`: the server failed to handle a request (5xx).

## Rules

- Never log passwords, tokens, API keys or personal data.
- Log failures even when the exception is unhandled.
- Use the same field names in every service so one search works everywhere.
- Note the unit difference: `latency_ms` is milliseconds, `request_time` is seconds.
