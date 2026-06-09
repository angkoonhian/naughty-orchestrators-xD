# Impact Classification Rules

Universal default rules. Tunable per-project via `.claude/orchestration.config.yaml`.

## Tiers

### LOW (skip all gates)

- Bug fixes without interface or schema change
- Typo / copy / translation changes
- CSS / styling-only changes
- Config-file changes (`.env`, `docker-compose`, `tsconfig`, ESLint/Prettier config)
- Patch or minor dependency bumps with no breaking changes
- Adding logs, comments, or documentation
- Fixing lint warnings

### MEDIUM (DA advisory, pre-impl advisory, post-impl blocking)

- New features within a single project
- Refactoring existing code (renames, module restructuring)
- Adding a new dependency
- New UI components or pages within an existing app
- New API endpoints that follow existing patterns
- Changes to existing business logic
- Adding or modifying tests

### HIGH (all gates blocking)

- Cross-project changes (touching 2+ projects)
- Database schema changes (new tables, column modifications, migrations)
- New API contracts (new DTOs, new response shapes consumed by other apps)
- Authentication / authorization changes
- Changes to shared packages
- Removing or renaming existing API endpoints
- Deployment-configuration changes (Dockerfile, CI/CD)
- Adding a new database connection or data source

### CRITICAL (all gates blocking + structured FOR/AGAINST debate)

- Architecture decisions ("should we X vs Y")
- Technology migrations (changing framework, library, or paradigm)
- New project creation (adding a new app to the monorepo)
- Auth model changes
- New communication patterns (e.g., adding GraphQL alongside REST)
- Merging or splitting projects
- Any request the user explicitly flags as needing careful consideration

## Bump rule

When the change touches **security, authentication, or money**, bump one tier higher.

Examples:
- "Fix a typo in the welcome email" → LOW
- "Fix a typo in the password-reset email" → bumped to MEDIUM (touches auth-related flow)
- "Add a new endpoint following existing patterns" → MEDIUM
- "Add a new endpoint for billing webhook" → bumped to HIGH (touches money)

## Ambiguity rule

When impact tier is unclear, default to MEDIUM. The DA advisory gate provides cheap coverage without blocking, so under-classification has bounded downside.

## Per-project bumps (configurable)

Projects can define additional bump rules in `.claude/orchestration.config.yaml`:

```yaml
impact_bumps:
  - condition: "touches files matching pii*"
    bump_to_minimum: HIGH
  - condition: "touches migrations/"
    bump_to_minimum: HIGH
```

These are merged on top of the universal rules at bootstrap time.
