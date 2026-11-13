# V21 held-out gap test: run notes and results (2026-11-10)

Protocol: `PROTOCOL.md`, frozen 2026-11-10T05:06:27Z (SHA-256 bc3f34e9…76f0, `FROZEN.txt`). Checker f99ce2b2f65d7630 (released), unchanged. No cell, claim, rule or level was changed after a held-out number existed.

## Deviations from the run plan (none change the protocol)
1. Docker Desktop was stuck after an earlier WSL error. It was restarted with `docker desktop restart` before any held-out solve.
2. Export crashed on the first claim-B certificate (`KeyError: 'convergence'`): a certificate whose counts fail carries no edge estimates. Export now writes null amm edges in that case; the reference needs only the k set and band index. Because of the crash, the loop skipped cell 1's reference, so it was run separately after the loop (`logs/dolfinx_cell1.log`).
3. `analyse` unpacked `compare.edges` (four return values) as two. It now takes the first two, as `compare.analyse` does.
4. All ten cells reached the n = 30 edge-k level, so every reference uses levels [15, 20, 30]. No memory fallback was used.

## Primary outcome: FAIL (one unsound safe edge)
- (a) Unsound safe edges: **1** of 6 graded safe edges (5 sound, 34 edges without a safe value).
- (b) Certified false claims: **0** (17 false claims, all undetermined).
- The protocol's pass condition is both zero, so the held-out test fails on (a).

**The unsound edge.** Cell ho_cb_c0.6191_w0.0657_nu0.3, thin stratum, claim A, upper edge.
- Certificate: undetermined. It has no safe lower edge, and the feature rule failed (bar 2.63 voxels at n = 40, below 3).
- amm edges at n = 20/30/40: 0.741, 0.644, 0.637. Fitted order 6.0, capped at 2; extrapolated value 0.627, remaining error 0.0099, safe upper edge 0.607.
- DOLFINx exact-geometry reference: levels 15/20/30 give 0.583, 0.575, 0.560. The steps grow, so the protocol's non-monotone branch applies: R = 0.560, u = 0.0154. The unsafe-side limit R + 2u is 0.591, below the safe edge of 0.607, so the edge is unsound.
- The safe edge also lies above the finest DOLFINx upper edge, 0.560. On exact geometry that value is a Rayleigh–Ritz upper bound at its wave vector, so this edge is unsound for certain.
- With an order cap of one (V22 alternative), the safe upper edge would be 0.567. That is marginal by the protocol, but still above the Rayleigh–Ritz bound.
- The released checker did not certify the claim. The feature rule and the missing lower edge each withheld it. The certificate still reports the safe upper edge as a guarded estimate.

## Secondary outcomes (`secondary.json`)
- Yield: 2 true claims; 1 certified (cell ho_cb_c0.6875_w0.2229_nu0.3, claim A; margins 19.0 and 2.2 in units of 2u; safe interval gives up 7.8% of the reference gap).
- Truth: 17 false, 2 true, 1 indeterminate of 20 claims. The search-tier gaps (n_bloch = 10) lay above the reference: lower edges 13–34% high, upper edges 6–146% high. So even claim A (the inner half of the search gap) was false on 7 of 10 cells.
- Abstention reasons:
  - false claims: modes inside the claimed interval at every resolution 13, count failures 2, no safe lower edge 1, no safe upper edge 1;
  - the true claim left undetermined (ho_cb_c0.6853_w0.2222_nu0.3 A): no safe upper edge (monotone drift toward the claim);
  - the indeterminate claim: no safe upper edge.
- Wave-vector coverage: DOLFINx's own k search and its full k sets found no more extreme edge than amm's 37 wave vectors (largest relative miss 1.3e−14).
- Two nearly identical regular cells (c 0.6853/0.6875, w 0.2222/0.2229) got different claim-A verdicts: undetermined (no safe upper edge) and certified.

## V22 sensitivity on the complete held-out set
- Gap order cap one: 0 of 20 held-out verdicts change.
- Static drift rule: 0 of 20 change.
