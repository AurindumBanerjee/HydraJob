# HydraJob UI & Visual Style Guide

HydraJob uses a warm-paper editorial palette designed for high legibility, calm contrast, and immediate visual hierarchy across dashboards, documentation figures, and diagnostic views.

## 1. Color Palette

### Surfaces & Hairlines

| Token | Hex | Usage |
| :--- | :--- | :--- |
| `--paper` | `#FBFAF6` | Primary page & canvas background |
| `--paper-warm` | `#F3EFE5` | Secondary cards, figure zones, callout backgrounds |
| `--paper-cool` | `#EEE9DD` | Table headers, code blocks, metadata strips |
| `--rule` | `#D9D4C6` | 1px hairline dividers, card borders, grid lines |

### Ink & Typography Hierarchy

| Token | Hex | Usage |
| :--- | :--- | :--- |
| `--ink` | `#14140F` | Primary headings, body text, diagram strokes |
| `--ink-soft` | `#3B3A34` | Secondary body copy, subheadings |
| `--graphite` | `#6B6960` | Captions, section kickers, timestamps, axis labels |

### Semantic Accents & Diagram Fills

| Token | Accent Hex | Soft Fill / Bg Hex | Semantic Meaning |
| :--- | :--- | :--- | :--- |
| `--accent` | `#7A2E3B` | `#F1D9DD` | Primary accent, critical alerts, errors, external entry |
| `--blueprint` | `#1F4A5C` | `#DCE8EC` | Informational, API endpoints, application/system nodes |
| `--sage` | `#4E6A56` | `#E4EDE4` / `#EDF2EC` | Healthy, OK, verified, data & private inference stores |
| `--amber` | `#B47A28` | `#EEE8DA` / `#FAF3E7` | Degraded, warning, pending, orchestration/proxy |

## 2. Typography

- **System font stack only:** Use native system sans-serif (`system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`) and monospace (`ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace`) stacks.
- **No external font loading:** Do not load Google Fonts or remote font CDNs (keeps the UI fast, offline-capable, and privacy-preserving on AWS EC2 and local dev).

## 3. Layout & Component Rules

1. **Section Kickers:** Introduce major sections with crisp uppercase kickers (e.g., `§ 01 / SERVICE HEALTH`) in `--graphite` (`#6B6960`).
2. **Left-Accented Callouts & Status Cards:** Use crisp `1px solid #D9D4C6` borders with a `3px`–`4px` solid semantic left border (`#7A2E3B`, `#1F4A5C`, `#4E6A56`, or `#B47A28`) on `--paper-warm` (`#F3EFE5`) or semantic soft-fill backgrounds.
3. **Semantic Status Badges:** Pair concise text labels (`OK`, `DEGRADED`, `UNAVAILABLE`) with matching semantic tint + ink rather than relying on color alone.
4. **Diagram & Asset Clarity:**
   - Store all diagrams and visual assets inside `figures/`.
   - Keep one clear idea per diagram with generous whitespace and zero overlapping text.
   - Use responsive SVG `viewBox` coordinates without fixed pixel `width`/`height` attributes.
5. **Timezone Display:** Format user-facing timestamps in `Asia/Kolkata` while preserving UTC storage in PostgreSQL.
