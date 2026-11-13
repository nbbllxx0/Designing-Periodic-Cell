# Concepts

amm designs periodic unit cells (triply periodic minimal surfaces, strut lattices, mass-in-frame resonators) for
stiffness and elastic-wave band-gap targets. The design loop uses two kinds of numbers, and the package keeps
them apart: **search-tier estimates**, which are fast and approximate, and **acceptance-tier certificates**, which
are slower and carry guard bands. The tool contract enforces the difference. Only a certified design can be
released in profile C, and no tool lets an agent write a certificate.

## Units

The solvers work in normalized units: solid Young's modulus E_s = 1, solid density 1, cell edge a = 1.
Stiffness is reported as a fraction of E_s. Frequency is reported as f* = f a / c_t, where c_t is the shear-wave
speed of the solid. The session converts physical requests (Pa, MPa, GPa, psi; Hz, kHz, MHz; mm, cm, m, um, in)
with `amm.units`, using the material's E, Poisson ratio and density and the cell size. Results carry both unit
systems.

Built-in materials (`amm.units.MATERIALS`; typical datasheet values, not measurements):

| Name | E | nu | rho | Process | Typical min. feature |
|---|---|---|---|---|---|
| PA12 | 1.70 GPa | 0.39 | 1010 kg/m^3 | SLS | 0.8 mm |
| Ti6Al4V | 113.8 GPa | 0.342 | 4430 kg/m^3 | LPBF | 0.3 mm |
| 316L | 193.0 GPa | 0.30 | 8000 kg/m^3 | LPBF | 0.3 mm |
| AlSi10Mg | 70.0 GPa | 0.33 | 2670 kg/m^3 | LPBF | 0.4 mm |

A custom material is given as `set_material(E_Pa=..., nu=..., rho_kg_m3=...)`. The search atlas exists only for
solid Poisson ratios 0.3, 0.342 and 0.39. For any other ratio, including AlSi10Mg (0.33), `check_bounds` reports
the atlas verdict `UNAVAILABLE` and `atlas_suggest` returns an error. The bounds, `evaluate`, `search` and `certify`
still work for that ratio.

## Supported targets

| Target (set_target) | Quantity | Unit given as |
|---|---|---|
| `density_max`, `density_min` | solid fraction | dimensionless |
| `E100_min`, `E100_max` | Young's modulus along a cube axis | pressure unit or `"E_s"` |
| `G_min` | shear modulus C44 | pressure unit or `"E_s"` |
| `bulk_min` | bulk modulus | pressure unit or `"E_s"` |
| `nu100_min`, `nu100_max` | Poisson ratio along [100] | dimensionless |
| `gap` | complete band gap covering [f_lo, f_hi] (all directions and polarizations) | Hz, kHz, MHz or `"f*"` |

These are the only targets. `evaluate` also reports other quantities: the full tensor C*, the Zener anisotropy
ratio, E110 and E111, and the Voigt and Reuss averages. Those are outputs. None of them can be stated as a target
or certified. For example, a stiff E100 cell can be very anisotropic (tutorial 02 finds a cell with Zener ratio
0.04). Add `G_min` if shear stiffness matters.

## Search tier (estimates)

- **`evaluate`** runs the static homogenization at n = 20 voxels per edge on the CPU (PARDISO) and the band
  diagram at n = 10 on the irreducible-zone path (torch; GPU if available, else CPU). It takes about 1-2 s per
  cell on a GPU machine. The values are biased stiff and high in frequency by several per cent.
- **The search atlas** holds 2,722 precomputed cells per solid Poisson ratio, each one an `evaluate` row with its
  band diagram. `atlas_suggest` ranks atlas cells against the targets at no solve cost.
- **The error model** (`error_model.json`) gives calibrated one-sided error ranges per family and quantity, so
  search-tier values can be read as ranges: nominal, expected, and pessimistic or optimistic.
- **`search`** runs Bayesian optimization (BoTorch) over the family parameters. It is seeded by the atlas and
  ranks candidates by the error-corrected slack.

Slack is the relative distance to the nearest target, minimized over all targets. A positive slack means every
target is met. A search-tier value is never a certificate, and every result is labelled `"tier": "search (not
certified)"`.

## Acceptance tier (certificates)

`certify` (in profile C) checks one design against the current targets:

- **Static block.** Resolution ladders (32, 48, 64), then (48, 64, 80), then (64, 80, 96). Each resolution is
  solved at five grid phases (0, 1/8, 1/4, 3/8 and 1/2 voxel). Per quantity, the phase means are extrapolated with
  a fitted order (capped at 1), and the bound is moved out by twice the estimated remaining error. Numerical
  checks: FP64 residual <= 1e-10, symmetry, positive definiteness, percolation in x, y and z, and at most 1 % of the
  solid removed as islands.
- **Bloch block** (only with a `gap` target). Inertia counts (Sylvester's law) at resolutions 20 and 30 on the
  irreducible-zone path, random interior k, and the worst interior k found by an adversarial search. Edge
  convergence is guarded by n = 40 and by grid phases, and the edges are moved inward by twice the estimated error.
- **As-built block.** The surface is eroded and dilated by 0.01 a, and the static targets and gap counts are
  checked again. This is a robustness flag (`robust`). It is not needed for release.

The verdict is one of three:

- `certified`: every target is accepted within the guarded bounds.
- `refuted`: a target is violated beyond its guard band.
- `undetermined`: the certificate neither proves nor disproves a claim. The claim lies inside the guard band, a
  gap edge has no safe value, or the finest resolution does not resolve the load-path feature.

With static targets only, a certificate takes about 20 s to a few minutes on a desktop CPU (tutorial 02: 20 s).
With a gap target it takes 2-20 minutes, and the Bloch block uses the GPU when one is available.

### What a certificate guarantees, and what it does not

A certificate **does** say the following:

- The stated design, the stated solid (isotropic, linear elastic, small strain) and the stated targets were checked
  by solvers the agent cannot influence.
- Every static target holds for the extrapolated value, after a guard of twice the estimated discretization error
  and the grid-phase spread.
- For a gap, the inertia counts at every sampled k (path, random interior points and the adversarial worst case)
  put no band inside the claimed interval at the counted resolutions. The interval also lies inside the
  convergence-guarded edges. An edge that moves toward the claim without an admissible convergence order has no
  safe value, so such a gap stays undetermined. An order is admissible when some p in [0.25, 8] solves the order
  equation of f = f0 + C h^p through the three edge values; the test is on h, not on raw steps, so on a ladder with
  equal h-steps (n = 30, 40, 60) a sequence whose steps do not shrink can still have an admissible order p <= 1
  (`bloch._order`; corrected in amm 0.2.0 before release).
- The finest resolution of each block places at least three voxels across the load-path feature (bar width,
  strut diameter, or the narrowest ligament of a minimal surface; `certify.FEATURE_MIN_VOXELS`). Otherwise a
  certified result is withheld as undetermined; a refutation still stands.
- The certificate is tied to the checker code (`certify.checker_hash()`), the geometry, the targets, the material
  and the Poisson ratio. Changing any of them makes it invalid for the new request.

A certificate **does not** say the following:

- It is not a continuum theorem. The guard bands come from fitted convergence orders and sampled grid phases.
  They are not rigorous a-priori error bounds.
- Between sampled k points, a band could in principle enter the gap. The adversarial search reduces this risk but
  does not remove it.
- It is certified for the infinite periodic lattice, not for a finite printed block, its boundaries or its
  mounting.
- It is not a printability statement. Surface roughness, defects, porosity, anisotropy from printing and residual
  stress are not modelled. The as-built offset is a robustness flag, not a tolerance analysis.
- The material values are typical datasheet inputs, not properties of a printed part.

## The five outcomes, plus "information needed"

Every `submit` returns an outcome card (`amm-outcome/1`):

| Outcome | Meaning | Needs (profile C) |
|---|---|---|
| `certified_candidate` | the certificate accepts every target | release of a design certified in this session for the current targets |
| `refuted_candidate` | the certificate shows a target is violated beyond its guard band | refusal citing a refuted certificate |
| `proven_infeasible` | a named rigorous bound is violated | refusal citing a `check_bounds` bound violation, or a `set_target` rejection of a gap containing f = 0 (rule W1) |
| `not_found_in_families` | nothing found in a bounded search of the declared families (not a proof of impossibility) | refusal citing an atlas NOT_FOUND verdict or a `search` over every declared family that found nothing |
| `numerically_undetermined` | a claim lies inside the guard band | refusal citing an undetermined certificate |
| `need_info` ("Information needed") | the request cannot be stated in solver units (for example a stiffness in MPa with no material, or a frequency in Hz with no cell size) | `submit(decision="need_info")` |

Rigorous bounds (`amm.bounds`):

- **V1, Voigt**: any geometry, C* <= phi C_s.
- **S1, cubic stability**: confines nu100 to (-1, 1/2) for a cubic design space.
- **P1, positivity and consistency**: minima must be positive, and a minimum cannot exceed its maximum.
- **W1**: a complete gap cannot contain f = 0.

The Hashin-Shtrikman bounds are advisory for cubic requests. A refusal must cite evidence that the session holds
for the *current* specification: the same normalized targets and Poisson ratio, and for certificates the same
material. Evidence from before a change of targets does not count. Profile B, the benchmark ablation arm, records
the claimed outcome without checking evidence (`evidence_checked: false`).

## Profiles, logs and replay

- **Profile C** is the full system. **Profile B** has no `check_bounds`, `certify` or `as_built`, and B releases
  are reported as `uncertified_release`.
- A session with a directory writes `session.jsonl`: one header record, then one record per call (arguments,
  result or error, state hash, timing). Certificates are written to `certificates/`.
- `amm.tools.replay(path)` re-runs every call of a log in a fresh session, with no LLM, and compares results and
  state hashes. Clarification answers are taken from the log. Replay is exact only against the code that wrote
  the log (`amm.tools.code_hash()`). Logs of schema `amm-tools/1` replay against the version-1 projection.
- `import amm` sets `MKL_CBWR=AUTO,STRICT`, so PARDISO results are bit-reproducible between processes on the same
  machine and replay can be exact. It also sets `MKL_NUM_THREADS=16`, which you can override.
