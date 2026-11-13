"""GUI backend for amm (plan items B4/B5). Lives outside `amm/` so that the frozen E4 code identity is untouched.

Modules:
  server.py    Starlette app: REST + server-sent events over the amm tool contract, one GPU worker queue
  backend.py   MockBackend (recorded results, never imports amm), the one-worker JobQueue (progress, cancel)
  live.py      LiveBackend (wraps amm.tools.Session), the shared solver lock, progress/cancel hooks, band tap
  e2e_live.py  live end-to-end check: headless Edge over CDP against a live server on localhost
  mockdata.py  index of recorded development sessions, certificates and atlas rows
  outcomes.py  five-outcome evidence cards built from a session log
  physics.py   unit conversion (mirror of amm/units.py), cubic tensor helpers, band-gap helpers
  geom.py      preview geometry (level sets, boundary mesh, STL)
  toolspec.py  tool contract parsed from amm source with `ast`
"""
__version__ = "0.2.0"
