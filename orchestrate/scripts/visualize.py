"""visualize — render the orchestration system as a single self-contained,
interactive HTML map.

Always draws the GENERIC architecture (4 tiers, cross-cutting agents, DA + validation
gates, the budget-driven dispatch loop, the graphify layer). When pointed at an
installed project (a `.claude/orchestration.config.yaml` is present), it OVERLAYS that
project's real Leads, platform-pack critics, custom validators, adaptive Tier-2 leads,
budget settings, and graph integration.

Output is one `.html` file — no build step, no server, no external/CDN deps (inline
SVG + CSS + JS) — so it opens offline in any browser and is easy to share.

Usage:  python -m scripts.visualize [PROJECT_ROOT] [-o OUT.html]
        (also wired as `/orchestrate visualize`)
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:
    from scripts import budget as _budget
    _BUDGET_DEFAULTS = {
        "defaults": _budget.IMPACT_DEFAULTS,
        "overrides": _budget.DEFAULTS["overrides"],
        "deepen_threshold": _budget.DEFAULTS["deepen_threshold"],
        "deepen_cost": _budget.DEFAULTS["deepen_cost"],
        "unleashed": _budget.DEFAULTS["unleashed"],
        "models": _budget.DEFAULTS["models"],
        "mode": "budgeted",
    }
except Exception:  # pragma: no cover
    _BUDGET_DEFAULTS = {
        "defaults": {"LOW": 0, "MEDIUM": 150000, "HIGH": 500000, "CRITICAL": 1200000},
        "overrides": {"cheap": 0.4, "thorough": 3.0},
        "deepen_threshold": 0.7, "deepen_cost": 40000,
        "unleashed": {"max_rounds": 5, "convergence_clean_rounds": 2, "agent_ceiling": 800},
        "models": {"mechanical": "haiku", "judgment": "opus"}, "mode": "budgeted",
    }

# ---- canonical generic structure (always present) ----

CORE_CRITICS = [
    ("edge-case", "null/empty/zero/huge data, timing races, session expiry"),
    ("security", "OWASP Top 10 against the stack"),
    ("performance", "query plans at scale, N+1, bundle size, fan-out cost"),
    ("failure-mode", "queue/cache/DB/3rd-party failure, idempotency, degradation"),
    ("consistency", "API shape, event naming, state-mgmt alignment"),
    ("tech-debt", "pattern drift, unnecessary deps, maintainability"),
    ("alternatives", "always names at least one Plan B with the tradeoff"),
]
PRE_VALIDATORS = [
    ("problem-statement", "does the spec match the user's actual request?"),
    ("requirement-completeness", "all requirements stated + implementable?"),
    ("success-criteria", "is 'done' defined in verifiable terms?"),
    ("assumption", "assumptions explicit; any risky/unverified?"),
    ("scope", "too big / too small / bundled concerns?"),
    ("contradiction", "internal contradictions; constraints vs goals?"),
]
POST_VALIDATORS = [
    ("spec-conformance", "every spec requirement implemented in the diff?"),
    ("acceptance-criteria", "each criterion verified against the code"),
    ("diff-scope", "implementer stayed in scope? no rogue refactors?"),
    ("regression", "existing suite still passes?"),
    ("smoke-test", "golden-path end-to-end check"),
    ("qa-delegator", "runs the project's real lint/test/typecheck once"),
]
CROSS_CUTTING = [
    ("architect", "cross-project planning + change manifests", "assets/cross-cutting/architect.md"),
    ("da-lead", "DA gate router → Pass-1 multi-lens + on-demand deepeners + synthesis", "assets/cross-cutting/da-lead.md"),
    ("pre-impl-validator", "spec gate router → 6 validators, smart-routes on FAIL", "assets/cross-cutting/pre-impl-validator.md"),
    ("post-impl-validator", "code gate router → 5 validators + qa-delegator", "assets/cross-cutting/post-impl-validator.md"),
    ("synthesis-verifier", "dedup → rank → adversarially verify-before-surface", "assets/cross-cutting/synthesis-verifier.md"),
]
TIER3 = [
    ("bug-fixer", "systematic debugging approach"),
    ("feature-builder", "end-to-end feature implementation"),
    ("refactor", "safe refactoring with test preservation"),
    ("migration-writer", "TypeORM-style migration generation + validation"),
]
DISPATCH_LOOP = [
    ("1 · CLASSIFY", "Determine request type (single-repo / cross-repo / opinion / schema / UI / audit)."),
    ("2 · ASSESS IMPACT + BUDGET", "LOW/MEDIUM/HIGH/CRITICAL → resolve the token budget (impact default × any explicit override, capped). Graph snapshot may raise the tier."),
    ("3 · DA GATE", "Tier-scaled. Pass-1 multi-lens reviewer → on-demand specialist deepeners (only hot/uncertain dims the budget affords) → synthesis-verifier. LOW skips."),
    ("4 · ARCHITECT", "If cross-repo, produce a change manifest / spec first."),
    ("4.5 · PRE-IMPL GATE", "Spec validators (Pass-1 + selective deepen). Smart-route back on FAIL, ≤3 retries."),
    ("5 · ROUTE", "Dispatch to Lead(s) — parallel where independent — with skill-injection at dispatch."),
    ("6 · EXECUTE", "Leads + sub-specialists implement. Reserved implementation floor is never consumed by gates."),
    ("6.5 · POST-IMPL GATE", "Run real lint/test/typecheck once + Pass-1 code review + selective deepen. Smart-route on FAIL."),
    ("7 · SYNTHESIZE", "Unify results, resolve conflicts, present with impact tier + a spend report."),
]


def _load_config(project_root: Path) -> dict | None:
    cfg = project_root / ".claude" / "orchestration.config.yaml"
    if not cfg.exists() or yaml is None:
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _asdict(x: Any) -> dict:
    """Return x if it's a dict, else {} — config sections can be any YAML type."""
    return x if isinstance(x, dict) else {}


def collect(project_root: Path) -> dict[str, Any]:
    cfg = _load_config(project_root)
    installed = cfg is not None
    cfg = cfg or {}
    nodes: list[dict] = []
    edges: list[dict] = []

    def add(nid, label, kind, role="", file="", extra=None):
        nodes.append({"id": nid, "label": label, "kind": kind, "role": role, "file": file, "extra": extra or {}})

    # Tier 0
    add("root", "Root Orchestrator", "tier0", "Classifies, assesses impact+budget, routes, synthesizes. Never writes code.", "CLAUDE.md")

    # Cross-cutting Tier 1
    for nid, role, file in CROSS_CUTTING:
        add(nid, nid, "crosscut", role, file)
        edges.append({"from": "root", "to": nid, "kind": "gate"})

    # DA critics (core + pack)
    for nid, role in CORE_CRITICS:
        add(f"critic:{nid}", nid, "critic", role, f"assets/da/core/{nid}-critic.md")
        edges.append({"from": "da-lead", "to": f"critic:{nid}", "kind": "deepen"})
    packs = []
    if installed:
        packs = [str(p) for p in (_asdict(cfg.get("platform_pack")).get("critics") or []) if p is not None]
        for p in packs:
            add(f"pack:{p}", p, "pack", "platform-pack critic (on-demand deepener)", f"assets/da/{(cfg.get('platform_pack',{}) or {}).get('name','pack')}/{p}-critic.md")
            edges.append({"from": "da-lead", "to": f"pack:{p}", "kind": "deepen"})

    # Validators
    for nid, role in PRE_VALIDATORS:
        add(f"pre:{nid}", nid, "validator", role, f"assets/validators/pre-impl/{nid}.md")
        edges.append({"from": "pre-impl-validator", "to": f"pre:{nid}", "kind": "deepen"})
    for nid, role in POST_VALIDATORS:
        add(f"post:{nid}", nid, "validator", role, f"assets/validators/post-impl/{nid}.md")
        edges.append({"from": "post-impl-validator", "to": f"post:{nid}", "kind": "deepen"})

    # Tier 1 Leads — live overlay or generic
    adaptive = {str(x) for x in (_asdict(cfg.get("adaptive_tier2")).get("enabled_leads") or [])} if installed else set()
    if installed:
        for proj in (_asdict(cfg.get("profile")).get("projects") or []):
            if not isinstance(proj, dict):
                continue
            name = str(proj.get("name") or "?")
            subs = [str(x) for x in (proj.get("subdomains") or []) if x is not None]
            is_t2 = name in adaptive
            qa = proj.get("qa_scripts") if isinstance(proj.get("qa_scripts"), dict) else {}
            role = f"Lead — {proj.get('framework') or 'static'} · {proj.get('file_count', 0)} files · {proj.get('complexity', '?')} complexity"
            add(f"lead:{name}", name, "lead", role, f"{name}/CLAUDE.md",
                extra={"subdomains": subs, "adaptive_tier2": is_t2, "qa": qa})
            edges.append({"from": "root", "to": f"lead:{name}", "kind": "route"})
            if is_t2:
                # one Tier-2a domain-lead cluster node, listing the subdomains it owns
                add(f"t2:{name}", f"{name} · Tier-2 domain leads", "tier2",
                    f"Adaptive Tier-2 ({len(subs)} subdomains ≥ thresholds): {', '.join(subs)}", f"{name}/CLAUDE.md")
                edges.append({"from": f"lead:{name}", "to": f"t2:{name}", "kind": "tier2"})
    else:
        for nid in ("project-lead", "ui-ux-lead", "qa-lead"):
            add(f"lead:{nid}", nid, "lead", "Project / cross-cutting Lead (generated per repo at install)", "<project>/CLAUDE.md")
            edges.append({"from": "root", "to": f"lead:{nid}", "kind": "route"})

    # Tier 3
    for nid, role in TIER3:
        add(f"t3:{nid}", nid, "tier3", role, f"assets/task-agents/{nid}.md")
        edges.append({"from": "root", "to": f"t3:{nid}", "kind": "task"})
    if installed:
        for persona in (cfg.get("user_choices", {}) or {}).get("install_personas", []) or []:
            add(f"persona:{persona}", persona, "persona", "user-perspective persona", f"assets/personas/{persona}.md")
            edges.append({"from": "root", "to": f"persona:{persona}", "kind": "task"})

    # Budget + graph (config sections may be any YAML type — coerce defensively)
    budget = {**_BUDGET_DEFAULTS, **_asdict(cfg.get("budget"))}
    for k, v in _BUDGET_DEFAULTS.items():            # nested dicts must stay dicts
        if isinstance(v, dict):
            budget[k] = {**v, **_asdict(budget.get(k))}
    graph = _asdict(cfg.get("graph_integration")) or {"enabled": False}

    name = "Architecture (generic)"
    if installed:
        prof = _asdict(cfg.get("profile"))
        projs = prof.get("projects") or []
        name = f"{project_root.name} · {len(projs) if isinstance(projs, list) else 0} projects · {prof.get('shape', '?')}"

    return {
        "title": "Orchestration Map",
        "subtitle": name,
        "installed": installed,
        "generated_at": (cfg or {}).get("generated_at", "") if installed else "",
        "nodes": nodes,
        "edges": edges,
        "loop": [{"step": s, "detail": d} for s, d in DISPATCH_LOOP],
        "budget": budget,
        "graph": graph,
        "counts": {
            "leads": sum(1 for n in nodes if n["kind"] == "lead"),
            "critics": sum(1 for n in nodes if n["kind"] in ("critic", "pack")),
            "validators": sum(1 for n in nodes if n["kind"] == "validator"),
            "tier2": sum(1 for n in nodes if n["kind"] == "tier2"),
        },
    }


def _safe_json(obj: Any) -> str:
    """json.dumps hardened for embedding inside a <script> block: neutralize anything
    that could break out of the script context or act as a JS line terminator
    (</script>, <, >, &, U+2028, U+2029). Config values come from scanning an arbitrary
    repo, so this is untrusted input."""
    return (json.dumps(obj)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace(" ", "\\u2028").replace(" ", "\\u2029"))


def render_html(data: dict) -> str:
    # Title/subtitle are HTML-escaped and substituted first, so a value inside the DATA
    # blob can never be mistaken for a placeholder; DATA is embedded last, script-safe.
    out = (_TEMPLATE
           .replace("__TITLE__", html.escape(str(data.get("title", "Orchestration Map"))))
           .replace("__SUBTITLE__", html.escape(str(data.get("subtitle", "")))))
    return out.replace("__DATA__", _safe_json(data))


def main(argv: list[str]) -> int:
    root = Path(".").resolve()
    out = None
    args = list(argv)
    if "-o" in args:
        i = args.index("-o")
        out = Path(args[i + 1]); del args[i:i + 2]
    if args:
        root = Path(args[0]).resolve()
    out = out or (root / "orchestration-map.html")
    data = collect(root)
    out.write_text(render_html(data), encoding="utf-8")
    print(f"wrote {out}  ({'installed overlay' if data['installed'] else 'generic architecture'}; "
          f"{len(data['nodes'])} nodes, {data['counts']['leads']} leads)")
    return 0


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — __SUBTITLE__</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--ink:#e6edf3;--mut:#8b949e;--acc:#58a6ff;
--tier0:#f778ba;--crosscut:#bc8cff;--critic:#ff7b72;--pack:#ffa657;--validator:#79c0ff;
--lead:#3fb950;--tier2:#56d4dd;--tier3:#d29922;--persona:#a5d6ff;}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Helvetica,Arial}
header{padding:12px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header h1{font-size:16px;margin:0}header .sub{color:var(--mut);font-size:13px}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.badge.on{color:#3fb950;border-color:#238636}
nav{display:flex;gap:4px;margin-left:auto}
nav button{background:transparent;border:1px solid var(--line);color:var(--mut);padding:5px 12px;border-radius:7px;cursor:pointer;font:inherit}
nav button.active{background:var(--panel);color:var(--ink);border-color:var(--acc)}
.wrap{position:absolute;top:54px;left:0;right:0;bottom:0;display:flex}
.view{flex:1;position:relative;overflow:hidden;display:none}.view.active{display:block}
#hsvg{width:100%;height:100%;cursor:grab;touch-action:none}#hsvg.drag{cursor:grabbing}
.side{width:300px;border-left:1px solid var(--line);background:var(--panel);padding:16px;overflow:auto;display:none}
.side.show{display:block}.side h3{margin:.2em 0;font-size:15px}.side .k{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin-top:12px}
.side code{background:#0d1117;border:1px solid var(--line);padding:1px 5px;border-radius:5px;font-size:12px;word-break:break-all}
.side ul{margin:6px 0;padding-left:18px}.chip{display:inline-block;font-size:11px;background:#0d1117;border:1px solid var(--line);border-radius:5px;padding:1px 7px;margin:2px}
.legend{position:absolute;left:12px;bottom:12px;background:rgba(22,27,34,.92);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:11px}
.legend span{display:inline-flex;align-items:center;gap:5px;margin-right:10px}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
.hint{position:absolute;right:12px;bottom:12px;color:var(--mut);font-size:11px}
.pad{padding:22px;max-width:980px;margin:0 auto;overflow:auto;height:100%}
.loop{display:flex;flex-direction:column;gap:8px}
.loop .st{border:1px solid var(--line);border-radius:9px;padding:12px 14px;background:var(--panel);cursor:pointer}
.loop .st b{color:var(--acc)}.loop .st p{margin:6px 0 0;color:var(--mut);display:none}.loop .st.open p{display:block}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}
.grid button{padding:10px;border-radius:9px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer;font:inherit}
.grid button.active{border-color:var(--acc);color:var(--acc)}
.bars{margin:14px 0}.bar{height:26px;border-radius:6px;margin:6px 0;display:flex;align-items:center;padding:0 10px;font-size:12px;color:#0d1117;font-weight:600;white-space:nowrap;overflow:hidden}
table{border-collapse:collapse;width:100%;margin:10px 0}td,th{border:1px solid var(--line);padding:7px 10px;text-align:left}th{color:var(--mut);font-weight:600}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.mut{color:var(--mut)}
.card{border:1px solid var(--line);border-radius:9px;padding:14px 16px;background:var(--panel);margin:10px 0}
.layer{display:flex;gap:10px;align-items:stretch;margin:8px 0}
.layer .lx{flex:1;border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:var(--panel)}
.arrow{color:var(--mut);align-self:center}
</style></head><body>
<header>
<h1>__TITLE__</h1><span class="sub" id="subt"></span>
<span class="badge" id="modeb"></span>
<nav>
<button data-v="hier" class="active">Hierarchy</button>
<button data-v="loop">Dispatch loop</button>
<button data-v="budget">Budget engine</button>
<button data-v="graph">Graphify</button>
</nav></header>
<div class="wrap">
 <div class="view active" id="hier">
   <svg id="hsvg"></svg>
   <div class="legend" id="legend"></div>
   <div class="hint">scroll = zoom · drag = pan · click a node</div>
 </div>
 <div class="view" id="loop"><div class="pad"><h2>Budget-driven dispatch loop</h2><p class="mut">Click a step. Agent count + depth at each gate is governed by the resolved token budget (see Budget engine).</p><div class="loop" id="loopl"></div></div></div>
 <div class="view" id="budget"><div class="pad" id="budgetp"></div></div>
 <div class="view" id="graph"><div class="pad" id="graphp"></div></div>
 <aside class="side" id="side"></aside>
</div>
<script>
const DATA = __DATA__;
const KINDS = {tier0:'Root',crosscut:'Cross-cutting',critic:'Core critic',pack:'Pack critic',validator:'Validator',lead:'Lead (Tier 1)',tier2:'Tier 2',tier3:'Task agent',persona:'Persona'};
const COL = k => getComputedStyle(document.documentElement).getPropertyValue('--'+k).trim();
document.getElementById('subt').textContent = '· '+DATA.subtitle;
const mb=document.getElementById('modeb'); mb.textContent = DATA.installed?'live install':'generic architecture'; if(DATA.installed)mb.classList.add('on');

// ---- tabs ----
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById(b.dataset.v).classList.add('active');
});

// ---- hierarchy layout (tier bands, with row-wrapping) ----
const ORDER = ['tier0','crosscut','critic','pack','validator','lead','tier2','tier3','persona'];
const BAND = {tier0:0,crosscut:1,critic:2,pack:2,validator:3,lead:4,tier2:5,tier3:6,persona:6};
const BANDLABEL = {0:'Tier 0',1:'Cross-cutting (Tier 1)',2:'DA critics — on-demand deepeners',3:'Validators — pre / post-impl',4:'Project Leads (Tier 1)',5:'Tier 2 — domain leads',6:'Task agents & personas (Tier 3)'};
const byId = {}; DATA.nodes.forEach(n=>byId[n.id]=n);
const bands = {}; DATA.nodes.forEach(n=>{const b=BAND[n.kind]??6;(bands[b]=bands[b]||[]).push(n);});
const NW=150,NH=44,GX=20,GYV=26,MAXCOLS=9,LBLW=160; let W=0;
const bandKeys=Object.keys(bands).map(Number).sort((a,b)=>a-b); const bandY={};
let y=64;
bandKeys.forEach(b=>{const row=bands[b];const cols=Math.min(MAXCOLS,row.length);bandY[b]=y;
  row.forEach((n,i)=>{n._x=LBLW+(i%cols)*(NW+GX)+GX;n._y=y+Math.floor(i/cols)*(NH+GYV);n._w=NW;});
  W=Math.max(W,LBLW+cols*(NW+GX)+GX); y+=Math.ceil(row.length/cols)*(NH+GYV)+44;});
const H=y+20;
const svg=document.getElementById('hsvg');
let vb={x:0,y:0,w:Math.max(W,1100),h:H};
function setVB(){svg.setAttribute('viewBox',`${vb.x} ${vb.y} ${vb.w} ${vb.h}`);}setVB();
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function draw(){
  let s='';
  bandKeys.forEach(b=>{s+=`<line x1="14" y1="${bandY[b]-12}" x2="${W}" y2="${bandY[b]-12}" stroke="${COL('line')}" stroke-width="1" opacity=".35"/>`+
    `<text x="16" y="${bandY[b]+22}" fill="${COL('mut')}" font-size="12" font-weight="700" opacity=".85">${BANDLABEL[b]||''}</text>`;});
  DATA.edges.forEach(e=>{const a=byId[e.from],b=byId[e.to];if(!a||!b)return;
    const x1=a._x+a._w/2,y1=a._y+NH,x2=b._x+b._w/2,y2=b._y;
    s+=`<path d="M${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2}, ${x2} ${y2}" fill="none" stroke="${COL('line')}" stroke-width="1.2" opacity=".7"/>`;});
  DATA.nodes.forEach(n=>{const c=COL(n.kind);
    s+=`<g class="node" data-id="${esc(n.id)}" style="cursor:pointer"><rect x="${n._x}" y="${n._y}" width="${n._w}" height="${NH}" rx="9" fill="${COL('panel')}" stroke="${c}" stroke-width="1.6"/>`+
       `<rect x="${n._x}" y="${n._y}" width="4" height="${NH}" rx="2" fill="${c}"/>`+
       `<text x="${n._x+12}" y="${n._y+18}" fill="${COL('ink')}" font-size="12.5" font-weight="600">${esc(n.label.length>20?n.label.slice(0,19)+'…':n.label)}</text>`+
       `<text x="${n._x+12}" y="${n._y+33}" fill="${COL('mut')}" font-size="10">${esc(KINDS[n.kind]||n.kind)}</text></g>`;});
  svg.innerHTML=s;
  svg.querySelectorAll('.node').forEach(g=>g.onclick=()=>select(byId[g.dataset.id]));
}
function select(n){const s=document.getElementById('side');s.classList.add('show');
  let h=`<h3>${esc(n.label)}</h3><span class="chip" style="border-color:${COL(n.kind)};color:${COL(n.kind)}">${KINDS[n.kind]||n.kind}</span>`;
  if(n.role)h+=`<div class="k">Role</div><div>${esc(n.role)}</div>`;
  if(n.file)h+=`<div class="k">Defined in</div><code>${esc(n.file)}</code>`;
  const ex=n.extra||{};
  if(ex.subdomains&&ex.subdomains.length)h+=`<div class="k">Subdomains</div>${ex.subdomains.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}`;
  if(ex.adaptive_tier2)h+=`<div class="k">Tier 2</div><div>Adaptive Tier-2 domain leads generated (scope crosses thresholds).</div>`;
  if(ex.qa){const q=Object.entries(ex.qa).filter(([k,v])=>v);if(q.length){h+=`<div class="k">QA commands</div>`+q.map(([k,v])=>`<div><span class="mut">${k}:</span> <code>${esc(v)}</code></div>`).join('');}}
  const ins=DATA.edges.filter(e=>e.to===n.id).map(e=>e.from), outs=DATA.edges.filter(e=>e.from===n.id).map(e=>e.to);
  if(ins.length)h+=`<div class="k">Dispatched by</div>${ins.map(x=>`<span class="chip">${esc((byId[x]||{}).label||x)}</span>`).join('')}`;
  if(outs.length)h+=`<div class="k">Dispatches → (${outs.length})</div>${outs.slice(0,12).map(x=>`<span class="chip">${esc((byId[x]||{}).label||x)}</span>`).join('')}${outs.length>12?' …':''}`;
  s.innerHTML=h;
}
// pan/zoom
let drag=null;
svg.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,vx:vb.x,vy:vb.y};svg.classList.add('drag');svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',e=>{if(!drag)return;const r=vb.w/svg.clientWidth;vb.x=drag.vx-(e.clientX-drag.x)*r;vb.y=drag.vy-(e.clientY-drag.y)*r;setVB();});
svg.addEventListener('pointerup',()=>{drag=null;svg.classList.remove('drag');});
svg.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY<0?.9:1.1;const mx=vb.x+vb.w*e.offsetX/svg.clientWidth,my=vb.y+vb.h*e.offsetY/svg.clientHeight;
  vb.w=Math.min(8000,Math.max(400,vb.w*f));vb.h=Math.min(8000,Math.max(300,vb.h*f));vb.x=mx-vb.w*e.offsetX/svg.clientWidth;vb.y=my-vb.h*e.offsetY/svg.clientHeight;setVB();},{passive:false});
// legend
document.getElementById('legend').innerHTML=ORDER.filter((k,i,a)=>a.indexOf(k)===i).map(k=>`<span><i style="background:${COL(k)}"></i>${KINDS[k]||k}</span>`).join('');
draw();

// ---- dispatch loop ----
document.getElementById('loopl').innerHTML=DATA.loop.map((s,i)=>`<div class="st" onclick="this.classList.toggle('open')"><b>${esc(s.step)}</b><p>${esc(s.detail)}</p></div>`).join('');

// ---- budget engine ----
const B=DATA.budget, FMT=n=>!isFinite(n)?'∞':n>=1e6?(n/1e6).toFixed(1)+'m':n>=1e3?Math.round(n/1e3)+'k':n;
function alloc(t){if(!isFinite(t))return{understand:Infinity,impl:Infinity,gates:Infinity};const u=Math.min(.1*t,60000),i=.4*t;return{understand:u,impl:i,gates:Math.max(0,t-u-i)};}
const GATES={LOW:'skip — straight to Lead',MEDIUM:'DA advises (non-blocking) · pre/post Pass-1',HIGH:'DA blocks · pre/post + selective deepen',CRITICAL:'DA blocks + FOR/AGAINST debate · full gates',unleash:'full panels · loop-until-dry · tournaments (Workflow engine)'};
function renderBudget(sel){
  const p=document.getElementById('budgetp');const tiers=['LOW','MEDIUM','HIGH','CRITICAL','unleash'];
  const tk = sel==='unleash'?Infinity:(B.defaults[sel]??0); const a=alloc(tk);
  const total=isFinite(tk)?tk:Math.max(1,B.defaults.CRITICAL);
  const bar=(label,v,c)=>`<div class="bar" style="width:${isFinite(tk)?Math.max(8,100*v/total):100}%;background:${c}">${label} ${FMT(v)}</div>`;
  p.innerHTML=`<h2>Budget engine</h2><p class="mut">Pick an impact tier (or unleashed). Budget = impact default × any explicit override, hard-capped. Agents/depth scale to it.</p>
  <div class="grid">${tiers.map(t=>`<button class="${t===sel?'active':''}" onclick="renderBudget('${t}')">${t}</button>`).join('')}</div>
  <div class="card"><b>Resolved budget:</b> <span class="mono">${FMT(tk)} tokens</span> &nbsp;·&nbsp; <b>gate behavior:</b> ${GATES[sel]}</div>
  <div class="bars"><div class="k mut">Allocation (implementation floor reserved first)</div>
    ${bar('understand',a.understand,COL('tier2'))}${bar('implementation floor',a.impl,COL('lead'))}${bar('gates (surplus)',a.gates,COL('validator'))}</div>
  <table><tr><th>impact</th><th>default budget</th></tr>${Object.entries(B.defaults).map(([k,v])=>`<tr><td>${k}</td><td class="mono">${FMT(v)}</td></tr>`).join('')}</table>
  <div class="card"><div class="k mut">Override grammar (explicit only)</div>
   <code>keep it cheap</code> ×${B.overrides.cheap} · <code>be thorough</code> ×${B.overrides.thorough} · <code>budget 300k</code> · <code>budget +200k</code> · <code>unleash</code> → ∞.
   Bare prose (max-width, deep link) never rescales. deepen&nbsp;threshold ${B.deepen_threshold}, deepen&nbsp;cost ${FMT(B.deepen_cost)}.</div>
  <div class="card"><div class="k mut">Progressive deepening</div>Pass-1 multi-lens reviewer → on-demand specialist deepeners (only dims with severity≥HIGH or confidence&lt;${B.deepen_threshold} the budget affords; security/auth/data-loss force-deepened on HIGH/CRITICAL) → synthesis-verifier → short-circuit when clean.</div>
  <div class="card"><div class="k mut">Unleashed backstop</div>convergence = ${esc(B.unleashed.convergence_clean_rounds)} clean rounds · max_rounds ${esc(B.unleashed.max_rounds)} · agent_ceiling ${esc(B.unleashed.agent_ceiling)} (code-enforced). models: mechanical=${esc(B.models.mechanical)}, judgment=${esc(B.models.judgment)}.</div>
  <div class="card mono" style="background:#0d1117">⟦orchestration⟧ impact=${sel==='unleash'?'—':sel} · mode=${sel==='unleash'?'unlimited':'budgeted'} · budget=${FMT(tk)} · spent≈… · agents: 1 understand · 1 pass-1 · n deepen · 1 verify</div>`;
}
renderBudget('HIGH');

// ---- graphify ----
const G=DATA.graph;const gp=document.getElementById('graphp');
gp.innerHTML = G && G.enabled ? `<h2>Graphify integration <span class="badge on">enabled</span></h2>
  <p class="mut">Impact assessment + routing + Tier-2 boundaries become structure-aware (not heuristic-only). Strictly additive — never lowers impact below the rule floor.</p>
  <div class="layer">
    <div class="lx"><b>Per-project AST graphs</b><div class="mut">free, no LLM · <code>&lt;proj&gt;/graphify-out/graph.json</code></div></div><div class="arrow">→</div>
    <div class="lx"><b>Seam graph</b><div class="mut">semantic extraction over the contract corpus · cross-project edges</div></div><div class="arrow">→</div>
    <div class="lx"><b>Baked snapshot</b><div class="mut"><code>${esc(G.snapshot||'.claude/orchestration.graph.json')}</code></div></div>
  </div>
  <div class="card"><div class="k mut">Trust model</div>EXTRACTED facts may raise impact / add a coupled Lead autonomously${G.trust&&G.trust.raise_impact_on_hub?' (hub touch → +1 tier)':''}; INFERRED/seam facts are advisory${G.trust?' (co-fire blocking when '+esc(G.trust.cofire_blocking_when||'EXTRACTED')+')':''}. hub_top_n=${esc(G.hub_top_n==null?8:G.hub_top_n)}.</div>
  <div class="card"><div class="k mut">Runtime</div>Snapshot-first; for a changeset Tier 0 may run <code>scripts/blast_radius.py &lt;proj&gt;/graphify-out/graph.json "&lt;target&gt;"</code>. Rebuild with <code>/orchestrate refresh-graph</code> (opt-in, never auto).</div>`
  : `<h2>Graphify integration <span class="badge">disabled</span></h2><p class="mut">Not enabled for this install (or generic view). When enabled, orchestrate consumes a graphify knowledge graph to make impact/routing/Tier-2 structure-aware. Enable via the bootstrap, then run <code>/orchestrate refresh-graph</code>.</p>`;
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
