# Platform Pack Library

Each pack is a directory under `~/.claude/skills/orchestrate/platform-packs/` containing a `pack.yaml` manifest and one or more critic markdown files.

## Available packs

| Pack | Triggers | Critics |
|---|---|---|
| `socket-realtime` | socket.io, ws, sockjs, @nestjs/websockets | socket-fanout-critic, reconnect-correctness-critic |
| `queue-system` | bull, bullmq, agenda, celery, sidekiq, amqp, kafkajs | queue-backpressure-critic, job-idempotency-critic |
| `multi-tenant` | repeated tenant_id / company_id / organization_id / workspace_id columns | cross-tenant-leak-critic, tenant-scoping-critic |
| `jwt-auth` | passport-jwt, @nestjs/jwt, jsonwebtoken, jose | jwt-lifecycle-critic, refresh-token-critic |
| `stripe-payments` | stripe + webhook handler patterns | webhook-replay-critic, idempotency-key-critic, pii-exposure-critic |
| `observability-sentry` | @sentry/*, datadog, newrelic, bugsnag | observability-critic |
| `timezone-sensitive` | tz / moment-timezone / dayjs-timezone / pytz heavy usage | timezone-critic |
| `multi-db` | multiple DataSource / Database / connection instances | multi-db-consistency-critic |
| `graphql` | graphql, apollo-server, type-graphql | resolver-complexity-critic, n-plus-one-graphql-critic |
| `file-uploads` | multer, formidable, busboy | file-upload-critic |
| `cost-aware` | continuously-growing tables (*_reading, *_log, *_event), quota-bound APIs | cost-critic |

## Pack manifest (`pack.yaml`) schema

```yaml
name: <pack-name>
description: <one-line summary>
triggers:
  any_of:
    - dep_present: <dep-name>
    - dep_present: <another-dep>
    - code_pattern: <pattern>
    - file_pattern: <glob>
  all_of:                  # optional — all conditions must match
    - dep_present: <required-base>
critics:
  - <critic-filename-without-extension>
  - <another-critic>
```

Bootstrap matches `triggers` against the scan output to decide whether to present this pack for user confirmation.

## Selection at bootstrap

1. Scanner outputs a profile.
2. For each pack, infer evaluates triggers against the profile.
3. Matching packs are presented one-by-one for user confirmation.
4. Confirmed packs are copied (or symlinked, depending on `--copy` vs `--link` flag — default copy) into `<project>/docs/agents/da/<pack-name>/`.
5. The `pack.yaml` is read by `da-lead` at dispatch time to know which critics to invoke.

## Adding a new pack (extension)

1. Create `~/.claude/skills/orchestrate/platform-packs/<pack-name>/`
2. Write `pack.yaml` and one or more critic markdown files following `assets/critic.template.md`
3. Add the pack to this index doc
4. Optional: contribute upstream

Bootstrap auto-discovers packs by listing the platform-packs directory; new packs don't require code changes.
