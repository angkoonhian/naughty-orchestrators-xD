# Stack Detection Extras

Less-common stacks the scanner recognizes via specific signal patterns.

## Elixir / Phoenix

| Signal | Interpretation |
|---|---|
| `mix.exs` at root | Elixir project |
| `phoenix` in deps | Phoenix framework |
| `ecto` in deps | Ecto ORM (informs DB critics) |
| `phoenix_live_view` | LiveView (informs real-time critics) |
| `broadway`, `oban` | Background processing (triggers queue-system pack) |

## .NET / ASP.NET

| Signal | Interpretation |
|---|---|
| `*.csproj`, `*.sln` | .NET project |
| `Microsoft.AspNetCore.*` in csproj | ASP.NET Core |
| `EntityFrameworkCore.*` | EF Core (informs DB critics) |
| `Microsoft.AspNetCore.SignalR` | SignalR (triggers socket-realtime) |
| `Hangfire`, `Quartz` | Background processing (triggers queue-system) |

## Java / Spring

| Signal | Interpretation |
|---|---|
| `pom.xml`, `build.gradle` | Java project |
| `spring-boot-starter-web` | Spring Boot web |
| `spring-boot-starter-data-jpa` | JPA (informs DB critics) |
| `spring-boot-starter-websocket` | WebSocket (triggers socket-realtime) |
| `spring-cloud-stream`, `spring-rabbit`, `spring-kafka` | Message bus (triggers queue-system) |

## Rust

| Signal | Interpretation |
|---|---|
| `Cargo.toml` | Rust project |
| `actix-web`, `axum`, `rocket`, `warp` | Web framework |
| `sqlx`, `diesel`, `sea-orm` | ORM/DB layer |
| `tokio-tungstenite`, `axum-extra/typed-routing` | WebSocket |

## Ruby / Rails

| Signal | Interpretation |
|---|---|
| `Gemfile` with `rails` | Rails |
| `activerecord` | AR ORM |
| `actioncable` | ActionCable (triggers socket-realtime) |
| `sidekiq`, `resque`, `delayed_job` | Queues (triggers queue-system) |

## PHP / Laravel

| Signal | Interpretation |
|---|---|
| `composer.json` with `laravel/framework` | Laravel |
| `laravel/sanctum`, `laravel/passport` | Auth (triggers jwt-auth) |
| `laravel/echo`, `pusher/pusher-php-server` | Real-time (triggers socket-realtime) |
| `laravel/horizon` | Queue dashboard (triggers queue-system) |

## How to add a new stack

1. Identify the manifest file(s) for the stack.
2. Identify dep / pattern signals that map to capabilities.
3. Add to this doc with explicit signal → interpretation table.
4. Update `scripts/scan.py` to parse the manifest format.

The skill's scanner is extensible — add detectors without breaking existing ones.
