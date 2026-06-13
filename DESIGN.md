# Amisys QHSE — Design System (v2, brand edition)

> **Source of truth** for visual decisions. Read this and `PRODUCT.md` before any frontend work. v2 supersedes the ComplianceOS design system: same discipline, new identity. The brand (name, logo, navy + orange, rounded geometric type) comes from the partner's identity asset (Five Rise / Amisys).

---

## 1. Aesthetic positioning

Amisys QHSE sits between **modern documentation sites** (Stripe Docs, Vercel Docs) and **professional QHSE tooling**. The brand adds warmth: a rounded geometric wordmark, deep navy chrome, and a single orange accent. The content area stays light, calm and typographically disciplined — the product is a working surface consulted in long sessions on a 27" monitor.

### The scene-sentence test

> A non-specialist manager, mid-morning, second coffee, opens the gap report from last week's analysis on a large external monitor. They want to scan twenty findings in five minutes, drill into the three Major ones, click through to the source pages, and leave with a list they can hand to their team.

Every design decision must serve that sentence. If it doesn't, it's wrong.

### Reflex-rejected aesthetic lanes

- **Vanta / Drata SaaS-cream + navy + green-accent.** Still banned. Our navy is *brand chrome* (sidebar/header), paired with orange, never with a green accent, never as cream-card decoration.
- **Salesforce / SAP enterprise legacy.** Giant icon-only sidebar, dense tables with inline buttons everywhere, modals on modals.
- **Apple Health / wellness pastels.** Wrong gravitas for regulatory work.
- **Dark tech-bro terminal.** `#000` + neon. The default experience is light content with navy chrome; the dark theme is navy-tinted, never pure black.

### How the brand is applied (decided)

- **Navy chrome + light content.** The sidebar and app chrome use brand navy with white text and orange highlights (echoing the logo lockup). The content area keeps warm light neutrals for data-dense readability. Dark mode re-tints content surfaces toward navy.
- **Orange accent, once.** The orange is the single accent and obeys the same discipline the gold did: one focal use per view.

---

## 2. Color system

### Strategy

**Restrained**: tinted neutrals + brand navy chrome + one orange accent (≤10% of content surface). No gradient text. No glassmorphism. No decorative blur.

The five severity colors are **diagnostic**, not decorative. They never appear outside an actual severity context. The accent orange is *interactive/brand*, never severity — and severity badges always carry icon + label, so the orange-vs-amber proximity can never be the sole signal.

### Tokens (OKLCH)

All colors in OKLCH. Never `#000` or `#fff`. Content neutrals stay warm (hue 90); brand and dark surfaces sit on the navy hue (262).

```css
/* Brand */
--brand-navy:        oklch(27% 0.045 262);  /* Sidebar / chrome      ≈ #1B2944 */
--brand-navy-deep:   oklch(22% 0.040 262);  /* Chrome hover/active wells */
--brand-orange:      oklch(75% 0.145 72);   /* Logo orange, on-navy highlights ≈ #F2A33C */
--on-navy:           oklch(97% 0.005 262);  /* Primary text on navy */
--on-navy-muted:     oklch(74% 0.020 262);  /* Secondary text on navy */

/* Base — warm-tinted neutrals (content area, light theme) */
--bg-page:        oklch(98%  0.005 90);
--bg-surface:     oklch(99%  0.003 90);
--bg-elevated:    oklch(96%  0.006 90);
--bg-sunken:      oklch(94%  0.007 90);

/* Ink */
--text-primary:   oklch(18%  0.012 245);
--text-secondary: oklch(45%  0.010 245);
--text-tertiary:  oklch(60%  0.008 245);
--text-disabled:  oklch(75%  0.005 245);

/* Borders */
--border-subtle:  oklch(92%  0.005 90);
--border-default: oklch(86%  0.007 90);
--border-strong:  oklch(70%  0.010 90);

/* Single accent — brand orange (interactive), used sparingly */
--accent:         oklch(64%  0.15  68);  /* CTA, active nav, links  ≈ #E08A1E */
--accent-hover:   oklch(58%  0.15  68);
--accent-subtle:  oklch(95%  0.04  75);  /* Selected row tint */

/* Severity — diagnostic, never decorative */
--severity-major:        oklch(55% 0.22 25);   /* Red       ≈ #DC2626 */
--severity-major-bg:     oklch(96% 0.04 25);
--severity-minor:        oklch(60% 0.17 55);   /* Deep amber/terracotta — nudged from hue 60 to keep distance from the accent */
--severity-minor-bg:     oklch(96% 0.045 55);
--severity-observation:  oklch(80% 0.16 90);   /* Yellow    ≈ #EAB308 */
--severity-observation-bg: oklch(97% 0.05 90);
--severity-conformant:   oklch(58% 0.16 145);  /* Green     ≈ #16A34A */
--severity-conformant-bg: oklch(96% 0.04 145);
--severity-spof:         oklch(50% 0.19 38);   /* Burnt orange, darker than Minor */
--severity-spof-bg:      oklch(96% 0.05 40);

/* Focus ring */
--focus-ring:     oklch(60%  0.15  68);
```

Dark theme: content surfaces re-tint to the navy hue (`--bg-page ≈ oklch(20% 0.03 262)`, surfaces a step lighter), text inverts, severity foregrounds lift ~10% lightness, `--accent` lifts to `oklch(75% 0.14 70)`. The sidebar is *already navy* in both themes — chrome does not change between themes.

### Rules

1. **The Orange-Once Rule.** The accent orange appears at most once per primary view as a focal element (active nav state, primary CTA, current selection). The logo's orange in the chrome does not count — it is brand, not state.
2. **The Severity-Diagnostic Rule.** Red, amber, yellow, green, burnt orange exist only to signal severity/state (incl. RAG task status). Never decoration, never brand.
3. **The Pair-Color-With-Label Rule.** WCAG 2.1 AA: color is never the sole indicator. Every severity/RAG badge ships with text label + icon. This rule is what makes accent-orange vs Minor-amber coexistence safe.
4. **The Tinted-Neutrals Rule.** Light neutrals tint warm (hue 90); dark surfaces tint navy (hue 262). Pure greys are banned.
5. **The Chrome-Is-Navy Rule.** Sidebar/header are brand navy in both themes. Content area is where light/dark switching happens.

---

## 3. Typography

### Family — "Rounded Geometric × UI Workhorse"

| Role | Font | Source |
|---|---|---|
| Wordmark, display, page titles | **Quicksand** (600–700) | Matches the brand wordmark's rounded geometry. |
| Headlines, section labels, panel headers | **Quicksand** (600) at ≥17px; **Inter** (600) below | Rounded warmth where size allows. |
| Body, finding text, descriptions | **Inter** (400) | The reading workhorse. Quicksand is banned below 15px body — legibility on dense tables. |
| Labels, badges, table headers | **Inter** (500, 11–12px, tracked +0.04em) | UI metadata. |
| Citations, clause IDs, file paths, page refs | **JetBrains Mono** (400–500) | Citation-as-monospace. |

EB Garamond is retired with the ComplianceOS identity. No serif anywhere.

```css
@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

--font-display: 'Quicksand', 'Nunito', system-ui, sans-serif;
--font-sans:    'Inter', system-ui, -apple-system, sans-serif;
--font-mono:    'JetBrains Mono', 'SF Mono', Consolas, monospace;
```

> Implementation note: the legacy token name `--font-serif` may remain as an alias of `--font-display` during migration so existing CSS keeps working; new CSS uses `--font-display`.

### Type scale (fixed, no clamp)

| Token | Size | Line-height | Weight | Family | Use |
|---|---|---|---|---|---|
| `display`  | 32px | 1.2  | 700 | display | Once per analysis page |
| `h1`       | 24px | 1.3  | 600 | display | Page sections |
| `h2`       | 20px | 1.35 | 600 | display | Panel headings, clause titles |
| `h3`       | 17px | 1.4  | 600 | sans  | Sub-sections, card headers |
| `body`     | 15px | 1.55 | 400 | sans  | Reading body |
| `body-sm`  | 13px | 1.5  | 400 | sans  | Secondary metadata |
| `label`    | 11px | 1.0  | 500 | sans  | Tracked +0.04em, UPPERCASE badges |
| `mono`     | 13px | 1.4  | 400 | mono  | Citations, IDs |
| `mono-sm`  | 11px | 1.3  | 400 | mono  | Page refs in chips |

### Rules

1. **The Display-as-Brand Rule.** Quicksand carries the brand at display/h1/h2. Below 17px it is banned — Inter takes over. The page does not become a children's book.
2. **The Mono-as-Citation Rule.** JetBrains Mono only for machine identifiers and citations. Never decoration.
3. **The Body-Reading Rule.** Body line-length capped at 65–75ch.
4. **The Fixed-Scale Rule.** No `clamp()`, no fluid sizing.
5. **The Hierarchy-Through-Contrast Rule.** Hierarchy = scale × weight × family, not color.

---

## 4. Layout

### Grid

- **Page max-width:** 1440px.
- **Primary gutters:** 24px. Mobile out of scope.
- **Sidebar:** fixed 240px, brand navy, never auto-collapsed.
- **Main column:** grid/flex as needed. No "everything-is-a-card-grid" reflex.

### Pane patterns

| Page | Layout |
|---|---|
| Dashboard | Sidebar + single rich content column |
| New analysis wizard | Sidebar + single column, progressive steps |
| Results | Sidebar + content column with expandable findings |
| Documents (DMS) | Sidebar + 2-pane: folder tree left, document list right |
| Tasks | Sidebar + RAG board / timeline |
| Chat | 3-column: threads, conversation |

### Spacing scale (4px base)

```
4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96
```

Vary the rhythm. Cards 20px padding, panels 24–32px, page hero 48–64px.

### Cards — only where they earn their place

A card needs: (1) clear "this is one thing" boundary, (2) an action on the card, (3) separation that justifies the border. **Banned:** identical card grids, nested cards.

### Surfaces and elevation

Flat by default. State via background-tint + 1px border shifts, not shadows.

```css
/* rest */    background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px;
/* hover */   border-color: var(--border-default); background: var(--bg-elevated);
/* selected */background: var(--accent-subtle); border-color: var(--accent);
```

---

## 5. Components

The codebase uses **hand-rolled components on vanilla CSS tokens** (no shadcn, no Tailwind — see §9). Specs below are the contract.

### Logo / wordmark

Inline SVG: orange "A" monogram (rounded strokes + three node circles) + "Amisys" wordmark (Quicksand 600) + "qhse" suffix (lighter, smaller, `--on-navy-muted` on chrome). On navy chrome: white wordmark + orange mark. On light surfaces (login card): navy wordmark + orange mark. Favicon = the monogram alone.

### Button

- **Primary**: navy background (`--brand-navy`), white text — the action-of-the-page.
- **Accent**: orange background — the *one* orange CTA per view ("Run analysis", "Download report").
- **Secondary**: border + transparent bg. **Ghost**: borderless. **Destructive**: severity-major, irreversible actions only.

Touch target ≥ 44×44px.

### Severity / RAG badge

Always icon + UPPERCASE label, `--severity-*-bg` background + `--severity-*` foreground. RAG task states reuse severity tokens (red=overdue, amber=due soon, green=on track) with the same label rule.

### Citation chip / Clause ID

Inline mono (`procedure.pdf:p3`, `9001_8.4`). Hover popover with excerpt.

### Table

No zebra-striping. Row hover = `--bg-elevated`. Selected = `--accent-subtle` + 1px `--accent` border. Header = `label` typography. Severity column first; file column last; page column right-aligned mono.

### Empty states

Short display-font headline, plain sub-line, one CTA.

### Loading states

Skeletons matching layout shape; never spinners mid-content. Page-top progress = 1px accent bar.

---

## 6. Motion

- **Durations:** 150ms state, 200ms sheet/popover, 250ms max.
- **Easing:** `cubic-bezier(0.25, 1, 0.5, 1)`. No bounce/spring.
- **Never animate** layout properties; only `transform` + `opacity`.
- Respect `prefers-reduced-motion`.

---

## 7. Accessibility — non-negotiable floor

| Check | Standard |
|---|---|
| Body text contrast | ≥ 4.5:1 hard floor (7:1 aim) |
| Large text contrast | ≥ 4.5:1 |
| On-navy text | `--on-navy` ≥ 7:1 on `--brand-navy`; orange on navy only ≥17px/600 |
| Focus visible | 2px `--focus-ring`, 2px offset, always |
| Keyboard navigable | Every interactive element; tab order = visual order |
| Color never sole indicator | Severity/RAG = colour + icon + label |
| Touch targets | ≥ 44×44px |
| Dark theme | Implemented (navy-tinted), toggle in chrome; both themes ship AA |

---

## 8. Anti-patterns — refused on sight

### Visual
- ❌ Side-stripe borders >1px on cards/list-items.
- ❌ Gradient text. Glassmorphism. Hero-metric gradient template.
- ❌ Identical card grids. Nested cards.
- ❌ Pure `#000`/`#fff`.
- ❌ Pie charts of severity buckets.
- ❌ Orange accent on anything severity-adjacent (badges, finding chrome) — accent is interactive/brand only.
- ❌ Quicksand below 15px or on data tables.
- ❌ Modals as a first thought.

### Copy
- ❌ Em dashes in product copy. ❌ Emoji in UI. ❌ Celebratory language. ❌ Auditor jargon. ❌ Restating the heading in the first sentence. UK English always.

### Interaction
- ❌ Hover-only affordances. ❌ Layout-shifting hover. ❌ Auto-collapsing sidebar. ❌ Toasts for ordinary success.

---

## 9. Stack — implementation contract (reconciled with reality)

| Concern | Decision |
|---|---|
| Build tool | Vite |
| Framework | React 19 |
| Language | TypeScript (strict) |
| Routing | react-router 7 |
| Server state | TanStack Query |
| Client state | Local hooks + localStorage stores (chat); no Zustand in use |
| Styling | **Vanilla CSS with OKLCH custom properties** (`index.css` tokens + `pages.css` components). No Tailwind, no shadcn. |
| Icons | Inline SVG (consistent stroke style) |
| SSE / streaming | `fetch` reader with Bearer auth (no EventSource — it can't send headers) |
| Charts | Hand-rolled SVG sparklines; severity bars. No pie charts. |

---

## 10. Pre-delivery checklist

### Visual
- [ ] OKLCH tokens only; no raw hex in components.
- [ ] Orange accent at most once per view as focal element (chrome logo excluded).
- [ ] Severity/RAG colours only with icon + label.
- [ ] Quicksand only ≥17px; Inter body; mono only citations/IDs.
- [ ] Navy chrome consistent across themes; content AA in both.
- [ ] No gradients, glassmorphism, nested cards, emoji.

### Interaction
- [ ] cursor-pointer on clickables; visible focus ring; stable hover; 44×44 targets; skeleton loading.

### Accessibility
- [ ] Contrast ≥ 4.5:1; tab order; labels on fields; aria-label on icon buttons; reduced-motion respected.

### Copy
- [ ] UK English, no Italian leakage, no em dashes, no celebratory tone, findings ≤150 words.
