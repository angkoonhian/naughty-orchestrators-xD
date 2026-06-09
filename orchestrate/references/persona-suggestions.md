# Persona Suggestions by Domain

When the user states the project domain at bootstrap, the skill suggests personas to install.

| Domain | Suggested personas |
|---|---|
| IoT / construction / infrastructure | site-engineer, safety-officer, building-manager, facility-manager, maintenance-tech |
| Fleet / transport / logistics | fleet-operator, dispatch-coordinator, driver, lta-inspector |
| E-commerce / retail | customer, merchant, support-agent, fulfillment-manager |
| Fintech / billing | end-user, ops-analyst, compliance-officer, risk-analyst |
| Healthcare | patient, provider, compliance-officer (HIPAA), billing-admin |
| Education | student, instructor, admin, parent (K-12) |
| Developer tools / SaaS | developer, technical-buyer, ops-engineer, security-reviewer |
| Real estate / property | tenant, landlord, agent, property-manager |
| Hospitality | guest, front-desk-agent, housekeeping-lead, general-manager |
| Manufacturing | line-operator, shift-supervisor, quality-inspector, plant-manager |
| Government / public sector | citizen, case-worker, supervisor, auditor |
| Media / publishing | reader, contributor, editor, ad-buyer |
| Media / streaming | viewer, content-creator, moderator |

If domain doesn't match any of the above, the user can:
- Pick from the closest match and customize
- Skip personas entirely
- Use `assets/persona.template.md` to define their own via `/orchestrate add-persona`

## Persona template structure

Each persona file has:
- Role description
- Goals (what they're trying to accomplish)
- Frustrations (what's hard for them today)
- Vocabulary (terms they use)
- Decision criteria (how they evaluate features)
- Channels (how they interact — web, mobile, voice, paper)

The template lives in `assets/persona.template.md`.
