# FAERS Overview dashboard — direction contract

## Scope & visitor mode
Operate. Single surface: the Reporting overview (main Overview dashboard). Visitor is a pharmacovigilance reviewer completing the task of assessing report volume and seriousness under chosen filters.

## Audience, job, action, proof, constraints
Audience: pharmacovigilance analysts, clinical researchers, regulatory affairs professionals.
Job: review reporting volume and seriousness, spot the headline numbers quickly, then drill into top drugs/reactions.
Action: set filters in sidebar, refresh, read the metrics and trend, download aggregates.
Proof: aggregate-only outputs from services.analytics_service.get_reporting_summary (report_count, serious_count, serious_pct, monthly series, top drugs, top reactions).
Constraints: preserve the services/ SQL contract and existing app navigation/flow; code-led build (no image generation); teal brand color carried forward; no same-size cards, no eyebrow above headings, no hero-metric template as page structure.

## Chosen direction & memorable moment
Restrained color strategy: ink #0F172A, muted #64748B, surface #FFFFFF, background #F8FAFC, primary teal #0F766E, serious accent #DC2626. System UI type (Inter stack). First viewport leads with total reports and serious-report rate set large as the dominant readout (volume & seriousness up front), then monthly trend, then top drugs/reactions as supporting detail. No eyebrow; heading carries its own weight. One authored motion moment (metric reveal on load), not scattered effects.

## Unresolved decisions
None at build time.

## Direction contract
THESIS: Volume and seriousness are the headline of the overview; the page opens with them large and unmistakable, refusing the same-size card grid and the eyebrow-above-heading default.

OWN-WORLD: Restrained neutrals (#F8FAFC ground, #FFFFFF surface, #0F172A ink, #64748B muted) with one clinical teal (#0F766E) carrying 30-40% of chroma; serious accent #DC2626 reserved for seriousness readouts; Inter/system-ui type at a clear scale; 1px #E2E8F0 borders only; shadows with offset + blur, never zero-offset halos.

STORY: Visitor opens the page → sees total reports and serious rate first (large, tabular numerals) → understands the reporting period → scans the monthly trend → drills into top drugs/reactions → downloads if needed.

FIRST VIEWPORT: Page title at top (no eyebrow). Directly below, two dominant metrics: total reports (large) and serious-report rate (large, with serious count inline). Then a horizontal rule, then monthly trend chart full width. Below that fold, two columns: top suspect drugs and top reactions, each with a small bar and a paginated table.

FORM: Code-led build in app.py, overriding _inject_styles and _render_results. Form position: whole-surface hierarchy revision within the existing app navigation. Seed key: none (code-led, no concept-seed run for an established surface extension).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and documentation; as an extension of an established surface, DESIGN.md is not rewritten.
