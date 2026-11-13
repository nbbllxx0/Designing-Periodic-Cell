"""Regenerate every paper asset (plan item A1, batches 1 and 2) from the result files:

    python scripts/paper/make_all.py [--only tables|figures|failures|docs]

Writes paper/tables/T*.md|.tex, paper/figures/F*.pdf|.png, paper/ANALYSIS_failures.md, paper/METHODS.md,
paper/SUPPLEMENT_data.md, paper/WRITING_GUIDE.md, paper/README.md and results/claims_ledger.md|.csv. No solver, GPU
or LLM call; `amm` is never imported (checker constants are read from its source text).

Diagram rule: scripts/paper/ holds data plots only. F1 (tool overview, a main diagram) is drawn by
a private script that is never published (user rule; the release script B7 excludes the
folder and asserts it). This script runs it when the folder is present and keeps the existing render otherwise.
Every figure function in scripts/paper/ must declare the result files it plots, and the run fails if one declares none.

T15 hook: V10 writes results/verification/v10/T15_v10.csv; T15 is built when that file exists and skipped otherwise.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from common import FIGURES, PAPER, ROOT, RESULTS, Ledger, rel  # noqa: E402

PRIVATE_F1 = None  # release copy (B7): the main-diagram source is not published; the hashed render is kept


def _f1(L: Ledger):
    """Run the private F1 script if it exists (never published); else keep the hashed render as it is."""
    if PRIVATE_F1 is None or not PRIVATE_F1.exists():
        outs = [FIGURES / "F1_tool_overview.pdf", FIGURES / "F1_tool_overview.png"]
        print("F1: scripts/paper_private/ absent; existing render kept" if all(p.exists() for p in outs)
              else "F1: scripts/paper_private/ absent and no render found")
        return [p for p in outs if p.exists()]
    spec = importlib.util.spec_from_file_location("f1_main_diagram_private", PRIVATE_F1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.draw(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["tables", "figures", "failures", "docs"], default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    L = Ledger()
    written = {}
    if a.only in (None, "tables", "docs"):
        import tables
        import tables2
        for fn in tables.ALL + tables2.ALL:
            out = fn(L)
            if not out:
                print(f"{fn.__name__}: skipped (input not present)")
                continue
            written[fn.__name__] = [rel(p) for p in out]
            print(f"{fn.__name__}: {', '.join(written[fn.__name__])}")
    if a.only in (None, "figures", "docs"):
        import figures
        import figures2
        for fn in figures.ALL + figures2.ALL:
            out = fn(L)
            srcs = getattr(fn, "sources", None)
            assert srcs, f"{fn.__name__} declares no result files: only data plots belong in scripts/paper/"
            written[fn.__name__] = [rel(p) for p in out]
            print(f"{fn.__name__}: {', '.join(written[fn.__name__])}")
        out = _f1(L)
        if out:
            written["f1_main_diagram"] = [rel(p) for p in out]
            print(f"f1_main_diagram (private script): {', '.join(written['f1_main_diagram'])}")
    if a.only in (None, "failures", "docs"):
        import failures
        written["failures"] = [rel(p) for p in failures.build(L)]
        print(f"failures: {', '.join(written['failures'])}")
    if a.only in (None, "docs"):
        import docs2
        for fn in docs2.ALL:
            written[fn.__name__] = [rel(p) for p in fn(L)]
            print(f"{fn.__name__}: {', '.join(written[fn.__name__])}")
        if a.only is not None:
            docs2.finalize_supplement(None)   # partial run: the ledger is not rewritten, so no count is claimed
    if a.only is None:
        import docs2
        n_rows = docs2.ledger_selfcount(L)   # the ledger's own row count, registered after every other row
        L.write(RESULTS / "claims_ledger.csv", RESULTS / "claims_ledger.md")
        docs2.finalize_supplement(n_rows)    # fills that count and the file size into SUPPLEMENT_data.md
        import readme
        readme.write(written, L)
        print(f"ledger: {len(L.rows)} rows, {len(L.conflicts)} conflicts; README written")
        for c in L.conflicts:
            print(f"  CONFLICT {c['asset']} / {c['item']}: {c['values']}")
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
