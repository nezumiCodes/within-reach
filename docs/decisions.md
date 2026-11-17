# Decision record

Decisions from spec section 15. Gate 0 requires D1–D5, D9, D11 and D13 to be settled.

| ID | Decision | Outcome | Date |
|---|---|---|---|
| D1 | Starting point | Start fresh; reuse the Part 2 script's logic in the pipeline | 17 Nov 2026 |
| D2 | Engine language in the browser | TypeScript | 17 Nov 2026 |
| D3 | Routing engine | OSRM for walking and driving | 17 Nov 2026 |
| D4 | Area unit and catchment radius | Councils in England and Scotland, health boards in Wales, plus a buffer. Radius to be set in config in Phase 1 | 17 Nov 2026 |
| D5 | Project licence | AGPL-3.0-only | 17 Nov 2026 |
| D9 | Ownership and pilot data | Cleared: personal project, no employer claim | 17 Nov 2026 |
| D11 | App framework | Svelte 5 with Vite, bundled, no CDN | 17 Nov 2026 |
| D13 | Static host | Cloudflare Pages at withinreach.vasnik.net (DNS stays at GoDaddy) | 17 Nov 2026 |
| D6, D7, D8, D10, D12, D14, D15 | | Open: due at later phases | |

## Other Phase 0 choices

- The repository stays private until the Phase 0 gate, then goes public.
- Folder names inside the repository are lowercase, which is the code convention.
- `'wasm-unsafe-eval'` is left out of the CSP until a WebAssembly dependency is added.
- Pushes to `main` deploy a preview. Tags `v*` deploy to production.
