# Adaptive Tier 2 Depth

When a project Lead's scope crosses a complexity threshold, bootstrap generates intermediate "Domain Leads" inside that Lead, splitting Tier 2 into:

- **Tier 2a (Domain Leads)** — orchestrate within a domain
- **Tier 2b (Specialists)** — execute within a domain

Smaller Leads stay flat (no Tier 2a layer), avoiding overhead where it isn't needed.

## Threshold (default)

A Lead crosses the adaptive threshold if either:
- Source file count in its scope ≥ **30**
- Distinct subdomain count ≥ **5**

Subdomains are detected by scanning the Lead's source tree for top-level dirs (e.g., `src/auth/`, `src/payments/`, `src/users/`).

## Tuning

Bootstrap presents thresholds at install time. The user can adjust. Stored in `.claude/orchestration.config.yaml`:

```yaml
adaptive_tier2:
  file_count_threshold: 30
  subdomain_count_threshold: 5
  always_flat_leads: ["website", "static-site"]
  always_deep_leads: ["api"]
```

## Generation behavior

When a Lead is identified as needing adaptive Tier 2:

1. The Lead's CLAUDE.md is generated with a domain-leads section instead of flat sub-specialists.
2. For each detected subdomain, a Tier 2a domain-lead stub is generated inline (or as a sub-file if domain-lead content is large).
3. Tier 2b specialists are listed under each domain-lead.

Example — for an api-lead with 5 subdomains:

```
api-lead (Tier 1)
├── device-domain-lead (Tier 2a) — ECM, SLM, CCTV, VMS, etc.
│   ├── ecm-specialist
│   ├── slm-specialist
│   ├── cctv-specialist
│   ├── vms-specialist
│   └── heatstress-specialist
├── user-domain-lead (Tier 2a) — companies, users, credentials
│   ├── companies-specialist
│   ├── users-specialist
│   └── credentials-specialist
├── auth-domain-lead (Tier 2a) — JWT, guards, strategies
│   ├── jwt-specialist
│   ├── guards-specialist
│   └── strategies-specialist
├── infra-domain-lead (Tier 2a) — queues, redis, websocket, email
│   ├── queues-specialist
│   ├── redis-specialist
│   ├── websocket-specialist
│   └── email-specialist
└── cms-domain-lead (Tier 2a) — CMS content management
    └── ...
```

## Dispatch semantics under adaptive Tier 2

- Tier 0 dispatches to api-lead (Tier 1)
- api-lead dispatches to the appropriate domain-lead (Tier 2a)
- domain-lead dispatches to specialists (Tier 2b)
- Specialist results bubble up through the same chain

Each tier transition adds latency. Adaptive depth is opt-in per Lead, not universal, so projects without genuinely deep complexity avoid the cost.
