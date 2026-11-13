"""Shared helpers for the paper-asset generators (plan item A1).

Everything here reads result files only. Nothing imports `amm` (another agent may be editing it, and importing the
package must never trigger a solve); constants of the checker are read from its source text with `ast`.

Ledger: every number that a table or figure shows is registered with its source file, the field or expression it
came from, the generating script and a status:
    verified  copied from a result file (rounding only);
    derived   computed here from result-file values (count, difference, ratio, median, unit change);
    conflict  two result files (or a result file and its NOTES) disagree; both values are recorded, none is chosen.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
TABLES = PAPER / "tables"
FIGURES = PAPER / "figures"
RESULTS = ROOT / "results"


def rel(p) -> str:
    """Path relative to the project root, forward slashes."""
    p = Path(p)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def read_json(p):
    with open(ROOT / p, encoding="utf-8") as f:
        return json.load(f)


def read_csv(p) -> list[dict]:
    with open(ROOT / p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(p) -> list[dict]:
    out = []
    with open(ROOT / p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def read_text(p) -> str:
    return (ROOT / p).read_text(encoding="utf-8-sig")


def sha16(p) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()[:16]


def fnum(x) -> float | None:
    if x is None or x == "" or x == "None":
        return None
    return float(x)


# --------------------------------------------------------------------------------------------------- source parsing
def find_line(path, pattern: str) -> int | None:
    """1-based line number of the first line of `path` matching the regex `pattern` (None if absent)."""
    rx = re.compile(pattern)
    for i, line in enumerate(read_text(path).splitlines(), 1):
        if rx.search(line):
            return i
    return None


def module_constants(path) -> dict:
    """Module-level NAME = literal assignments of a Python source file, with their line numbers and trailing
    comments: {name: (value, line, comment)}. Read with ast; the module is never imported."""
    src = read_text(path)
    lines = src.splitlines()
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                val = ast.literal_eval(node.value)
            except Exception:
                continue
            line = lines[node.lineno - 1]
            com = line.split("#", 1)[1].strip() if "#" in line else ""
            out[node.targets[0].id] = (val, node.lineno, com)
    return out


def function_defaults(path) -> dict:
    """{function name: {arg: (default literal, line)}} for module-level functions and methods (by bare name)."""
    src = read_text(path)
    out = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef):
            args = node.args.args + node.args.kwonlyargs
            defs = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults) + \
                list(node.args.kw_defaults)
            d = {}
            for a, dv in zip(args, defs):
                if dv is None:
                    continue
                try:
                    d[a.arg] = (ast.literal_eval(dv), dv.lineno)
                except Exception:
                    if isinstance(dv, ast.Name):
                        d[a.arg] = (dv.id, dv.lineno)
            out.setdefault(node.name, d)
    return out


# ------------------------------------------------------------------------------------------------------------ ledger
class Ledger:
    FIELDS = ["id", "asset", "item", "value", "unit", "status", "source", "field", "script", "note"]

    def __init__(self):
        self.rows: list[dict] = []
        self.conflicts: list[dict] = []
        self._ids: set = set()

    def add(self, asset, item, value, source, field="", status="verified", unit="", script="", note=""):
        base = f"{asset}:{item}"
        rid, k = base, 2
        while rid in self._ids:
            rid, k = f"{base}#{k}", k + 1
        self._ids.add(rid)
        if isinstance(value, float):
            value = f"{value:.6g}"
        row = dict(id=rid, asset=asset, item=item, value=str(value), unit=unit, status=status,
                   source=source if isinstance(source, str) else "; ".join(source), field=field,
                   script=script, note=note)
        self.rows.append(row)
        return value

    def conflict(self, asset, item, values: dict, script="", note=""):
        """values: {source description: value}. Recorded as one ledger row with status conflict, plus a conflict
        entry for the report."""
        txt = " | ".join(f"{k}: {v}" for k, v in values.items())
        self.add(asset, item, txt, list(values), status="conflict", script=script, note=note)
        self.conflicts.append(dict(asset=asset, item=item, values=values, note=note))

    def write(self, csv_path, md_path):
        csv_path, md_path = Path(csv_path), Path(md_path)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.FIELDS)
            w.writeheader()
            w.writerows(self.rows)
        from collections import Counter
        st = Counter(r["status"] for r in self.rows)
        assets = Counter(r["asset"] for r in self.rows)
        L = ["# Claims ledger (paper assets, batch A1)", "",
             "Generated by `scripts/paper/make_all.py`; do not edit by hand. Coverage: the numbers in the tables "
             "(`paper/tables/`), the numbers printed on the figures and one row per plotted series "
             "(`paper/figures/F*.pdf`), `paper/ANALYSIS_failures.md`, the constants of `paper/METHODS.md`, the counts "
             "of `paper/SUPPLEMENT_data.md`, the numbers of `paper/figures/CAPTIONS.md` and the result numbers of "
             "`paper/WRITING_GUIDE.md` (cited there by id). Not covered: editorial numbers (section, table, figure and "
             "plan-item numbers, dates, word budgets, character limits, version and schema labels) and the free text "
             "of the NOTES files. Each row gives the source file, the field or expression it came from, the script "
             "and a status:",
             "- **verified**: copied from a result file (rounding only);",
             "- **derived**: computed by the script from result-file values (count, difference, ratio, median, unit "
             "change); the `field` column gives the expression;",
             "- **conflict**: two result files, or a result file and its NOTES, disagree. Both values are recorded and "
             "neither is chosen.", "",
             "Figure series (many plotted points from one file) are recorded as one row per series with the point "
             "count; numbers printed on a figure (bar labels, annotations) have a row each.", "",
             f"Rows: {len(self.rows)} ({', '.join(f'{k} {v}' for k, v in sorted(st.items()))}).", "",
             "| asset | rows |", "|---|---|"]
        L += [f"| {a} | {n} |" for a, n in sorted(assets.items())]
        L += ["", "## Conflicts", ""]
        if self.conflicts:
            for c in self.conflicts:
                L.append(f"- **{c['asset']} / {c['item']}**: " +
                         "; ".join(f"`{k}` = {v}" for k, v in c["values"].items()) +
                         (f". {c['note']}" if c["note"] else ""))
        else:
            L.append("None.")
        L += ["", "## All rows", "", "| id | value | unit | status | source | field | script | note |",
              "|---|---|---|---|---|---|---|---|"]
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
        for r in self.rows:
            L.append("| " + " | ".join(esc(r[k]) for k in ("id", "value", "unit", "status", "source", "field",
                                                             "script", "note")) + " |")
        md_path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------------- tables
_TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
_UNI = {"±": r"$\pm$", "≤": r"$\le$", "≥": r"$\ge$", "→": r"$\rightarrow$", "×": r"$\times$", "−": "-",
        "ν": r"$\nu$", "ρ": r"$\rho$", "φ": r"$\phi$", "μ": r"$\mu$", "Γ": r"$\Gamma$", "–": "--", "·": r"$\cdot$",
        "≈": r"$\approx$", "Δ": r"$\Delta$", "≠": r"$\neq$", "√": r"$\surd$", "²": r"$^2$", "³": r"$^3$",
        "∗": "*", "°": r"$^\circ$", "µ": r"$\mu$"}


def tex_escape(s) -> str:
    s = str(s)
    s = s.replace("**", "")
    out = []
    for ch in s:
        out.append(_TEX.get(ch, _UNI.get(ch, ch)))
    t = "".join(out)
    t = re.sub(r"`([^`]*)`", r"\\texttt{\1}", t)
    return t


def md_escape(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_table(name: str, title: str, header: list, rows: list[list], notes: list[str] | None = None,
                colspec: str | None = None, label: str | None = None, small: bool = True) -> list[Path]:
    """Write paper/tables/<name>.md and .tex (booktabs). `rows` are lists of cell strings; a row that is a single
    string starting with '##' is a group heading spanning all columns."""
    TABLES.mkdir(parents=True, exist_ok=True)
    notes = notes or []
    md = [f"# {title}", "", "| " + " | ".join(md_escape(h) for h in header) + " |",
          "|" + "---|" * len(header)]
    for r in rows:
        if isinstance(r, str):
            md.append("| **" + md_escape(r.lstrip("# ")) + "** |" + " |" * (len(header) - 1))
        else:
            md.append("| " + " | ".join(md_escape(c) for c in r) + " |")
    if notes:
        md += [""] + [f"- {n}" for n in notes]
    md += ["", f"Generated by `scripts/paper/make_all.py` ({name}); numbers and sources in "
               "`results/claims_ledger.md`."]
    pm = TABLES / f"{name}.md"
    pm.write_text("\n".join(md) + "\n", encoding="utf-8")

    colspec = colspec or ("l" * len(header))
    tx = ["% Generated by scripts/paper/make_all.py; do not edit. Needs \\usepackage{booktabs}.",
          "\\begin{table}[htbp]", "\\centering"]
    if small:
        tx.append("\\small")
    tx += [f"\\caption{{{tex_escape(title)}}}"]
    if label:
        tx.append(f"\\label{{{label}}}")
    tx += [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule",
           " & ".join(tex_escape(h) for h in header) + " \\\\", "\\midrule"]
    first = True
    for r in rows:
        if isinstance(r, str):
            if not first:
                tx.append("\\midrule")
            tx.append(f"\\multicolumn{{{len(header)}}}{{l}}{{\\textit{{{tex_escape(r.lstrip('# '))}}}}} \\\\")
        else:
            tx.append(" & ".join(tex_escape(c) for c in r) + " \\\\")
        first = False
    tx += ["\\bottomrule", "\\end{tabular}"]
    if notes:
        tx.append("\\par\\smallskip\\footnotesize")
        tx += [tex_escape(n) + "\\par" for n in notes]
    tx.append("\\end{table}")
    pt = TABLES / f"{name}.tex"
    pt.write_text("\n".join(tx) + "\n", encoding="utf-8")
    return [pm, pt]


def pct(x, d=2, sign=True) -> str:
    if x is None:
        return "n/a"
    s = f"{100 * x:+.{d}f}" if sign else f"{100 * x:.{d}f}"
    return s + " %"


def g(x, d=4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{d}g}"
