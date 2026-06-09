# Scan Signals

This document is the source of truth for what the bootstrap scanner looks for and what it infers.

## Project shape signals

| Signal | Interpretation |
|---|---|
| `package.json` at depth 1 only | Single-app (JS/TS) |
| Multiple `package.json` at depth 1-2 | Monorepo (JS/TS) |
| `pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json` | Confirmed monorepo |
| `Cargo.toml` with `[workspace]` | Rust monorepo |
| `go.mod` with `replace` directives across multiple modules | Go monorepo |
| `pyproject.toml` / `requirements.txt` at depth 1 only | Single-app Python |

## Stack signals (from manifest deps)

### Frontend
| Dep | Framework |
|---|---|
| `react` | React |
| `vue` | Vue |
| `@angular/core` | Angular |
| `svelte` | Svelte |
| `next` | Next.js |
| `nuxt` | Nuxt |
| `remix-run/*` | Remix |
| `astro` | Astro |

### Backend (Node)
| Dep | Framework |
|---|---|
| `@nestjs/core` | NestJS |
| `express` | Express |
| `fastify` | Fastify |
| `koa` | Koa |
| `hono` | Hono |

### Backend (other)
| Dep | Framework |
|---|---|
| `django` (requirements.txt / pyproject.toml) | Django |
| `flask` | Flask |
| `fastapi` | FastAPI |
| `starlette` | Starlette |
| `rails` (Gemfile) | Rails |
| `phoenix` (mix.exs) | Phoenix |
| `spring-boot-starter` (pom.xml/build.gradle) | Spring Boot |
| `gin-gonic/gin` (go.mod) | Gin |
| `labstack/echo` | Echo |
| `gofiber/fiber` | Fiber |

## Infrastructure signals

| Detected | Inferred capability | Triggers pack |
|---|---|---|
| `socket.io`, `ws`, `sockjs`, `@nestjs/websockets` | Real-time | socket-realtime |
| `bull`, `bullmq`, `agenda`, `celery`, `sidekiq` | Background queues | queue-system |
| `amqp`, `amqplib`, `rabbitmq`, `kafkajs` | Message bus | queue-system |
| `ioredis`, `redis`, `@nestjs/cache-manager` | Cache | (informs critics, no dedicated pack) |
| `@sentry/*`, `datadog`, `newrelic`, `bugsnag` | Observability provider | observability-sentry |
| `typeorm`, `prisma`, `sequelize`, `mongoose`, `drizzle`, `sqlalchemy`, `gorm` | ORM | (informs critics) |
| Multiple `DataSource` / `Database` instances in code | Multi-DB | multi-db |
| `multer`, `formidable`, `busboy`, `@nestjs/platform-multer` | File uploads | file-uploads |
| `stripe`, `paypal`, `braintree`, `square` | Payments | stripe-payments (if Stripe) |
| `passport-jwt`, `@nestjs/jwt`, `jsonwebtoken`, `jose` | JWT auth | jwt-auth |
| `@auth0/*`, `@clerk/*`, `next-auth`, `lucia-auth` | Auth provider | jwt-auth (if token-bearing) |
| `node-cron`, `cron`, `node-schedule` | Scheduling | (informs critics) |
| `nodemailer`, `@aws-sdk/client-ses`, `sendgrid` | Email | (informs critics) |
| `graphql`, `apollo-server`, `type-graphql` | GraphQL | graphql |

## Domain markers (code-pattern detection)

| Marker | Indication |
|---|---|
| Repeated `tenant_id`, `company_id`, `organization_id`, `workspace_id` columns/fields across entities | Multi-tenancy → triggers multi-tenant pack |
| Filenames or fields containing `pii`, `gdpr`, `hipaa`, `pci`, `encrypted` | Sensitive data → bump impact rules |
| Heavy `tz`, `moment-timezone`, `dayjs/plugin/timezone`, `pytz`, `zoneinfo` usage | Timezone-sensitive → triggers timezone-sensitive pack |
| Continuously-growing reading/log tables (entity names matching `*_reading`, `*_log`, `*_event`) | Cost-aware → triggers cost-aware pack |

## Module boundaries

The scanner identifies top-level dirs under each project's `src/` (or framework convention equivalent) and counts files per dir to drive:
- Lead-level scope assignment
- Adaptive Tier 2 trigger (default: 30+ source files OR 5+ subdomains)

## Existing orchestration

If any of the following exists, the scanner enters Migrate or Update mode:
- `<root>/CLAUDE.md`
- `<root>/docs/agents/` (any contents)
- `<root>/.claude/orchestration.config.yaml`

## QA infrastructure

The scanner identifies available QA wiring for `qa-delegator`:
- `package.json` scripts containing `lint`, `test`, `typecheck`, `e2e`
- `Makefile` targets
- `.github/workflows/*.yml` jobs
- Test runner config files: `jest.config.*`, `vitest.config.*`, `pytest.ini`, `phpunit.xml`, `karma.conf.*`

The first available chain is wired in priority order: e2e > integration > unit > typecheck > lint.
