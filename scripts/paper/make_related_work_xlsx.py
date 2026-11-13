"""Build research/related_work.xlsx from research/related_work.csv.

Sheets:
  entries      every row of related_work.csv
  T1_features  feature-comparison draft for Table T1; each cell code is paired with the evidence text
               taken from the entry's "evidence" column (tag OS/GUI/STIFF/GAP3D/THERM/VERIF/BOUNDS/AGENT/STL)
  categories   counts and verification status per category, plus a one-line summary

Usage (from anywhere):
  python scripts/paper/make_related_work_xlsx.py [--md]
  --md also prints the T1 draft as a Markdown table (used in research/related_work.md).

Re-runnable: everything except the T1 cell codes below comes from the CSV.
"""
import csv
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "research" / "related_work.csv"
XLSX_PATH = ROOT / "research" / "related_work.xlsx"

FEATURES = OrderedDict([
    ("OS", "Open source"), ("GUI", "GUI"), ("STIFF", "Stiffness (homogenized)"), ("GAP3D", "Bandgap 3D (Bloch)"),
    ("THERM", "Thermal"), ("VERIF", "Verification / certificates"), ("BOUNDS", "Refusal / bounds"),
    ("AGENT", "Agent interface"), ("STL", "STL export"),
])
# Codes: Y = yes (seen in docs/repo), P = partial or building block only, N = not offered per inspected docs,
#        ? = not inspected / not stated. Order of values follows FEATURES.
T1 = OrderedDict([
    ("LatticeWorks", ("A01", "Y N P N N ? N N Y")),
    ("MSLattice", ("A02", "N ? N N N N N N Y")),
    ("FLatt Pack", ("A03", "N Y N N N N N N ?")),
    ("TPMS Designer", ("A05", "Y Y ? N N N N N ?")),
    ("TPMSgen", ("A07", "Y Y N N N N N N Y")),
    ("Top6Meta", ("A08", "Y Y N N N N N N Y")),
    ("nTop (Homogenize Unit Cell)", ("A10", "N Y Y N Y P N ? ?")),
    ("MetamatBench", ("A11", "Y Y Y N N P N N ?")),
    ("homo3d", ("B01", "Y N Y N N N N N N")),
    ("FANS", ("B06", "Y N Y N Y P N N N")),
    ("fibergen", ("B07", "Y Y Y N Y P N N N")),
    ("SfePy (homogenization, band_gaps)", ("B09+C01", "Y N Y P ? ? N N N")),
    ("dolfinx_mpc", ("C02", "Y N P P P P N N N")),
    ("PhoXonic.jl", ("C03", "Y N N P N P N N N")),
    ("AgenticTO (author, 2611.04077)", ("F05", "Y Y P N N Y P Y Y")),
])
THIS_WORK = ("This work (amm, planned)", "Y Y Y Y P Y Y Y Y",
             "Planned per plan/SOFTWARE_PAPER_PLAN.md S1-S2 (thermal optional, gate T); to be evidenced by V2 capability matrix and V9 release, not yet verified")
CATEGORY_NAMES = OrderedDict([
    ("a", "Metamaterial / lattice / TPMS design software"), ("b", "Homogenization codes"),
    ("c", "Phononic / Bloch band-structure codes and gap-design workflows"), ("d", "ML inverse design of metamaterials"),
    ("e", "LLM agents for engineering / materials design"), ("f", "Author's prior work"),
])
CATEGORY_SUMMARY = {
    "a": "Generators (TPMS/strut, graded, infill) with GUIs and STL; none computes Bloch bands or issues acceptance outcomes.",
    "b": "Static periodic homogenization (FE, FFT, GPU, commercial plug-ins); stiffness and sometimes conductivity; no wave physics.",
    "c": "Band solvers are libraries, scripts or commercial workflows; no open tool couples 3D Bloch gaps with stiffness targets and convergence guards.",
    "d": "Learned forward/inverse models (field bar: new representation + experiments); stiffness dominates; gap targets rare; only CertMix certifies (statistically).",
    "e": "LLM agents generate or call solvers; acceptance is mostly self-critique or task success; none refuses with physical-bound evidence for cells.",
    "f": "Author's agent/refusal/clarification/registry line; supplies the architecture and principles credited as non-claims (T10).",
}


def load():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def evidence_by_tag(text):
    out = {}
    tags = "|".join(FEATURES)
    for m in re.finditer(r"(?:^|;\s*)(%s|STIFF\+GAP):\s*(.*?)(?=;\s*(?:%s|STIFF\+GAP):|$)" % (tags, tags), text or ""):
        out[m.group(1)] = m.group(2).strip()
    return out


def t1_rows(by_id):
    rows = []
    for name, (ids, codes) in T1.items():
        codes = codes.split()
        assert len(codes) == len(FEATURES), name
        ev = {}
        for i in ids.split("+"):
            for k, v in evidence_by_tag(by_id[i]["evidence"]).items():
                ev[k] = (ev[k] + " | " if k in ev else "") + f"[{i}] {v}"
        rows.append((name, ids, codes, [ev.get(k, "no evidence recorded") for k in FEATURES]))
    return rows


def autosize(ws, maxw=60):
    for col in ws.columns:
        w = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, w + 2), maxw)


def main():
    data = load()
    by_id = {r["id"]: r for r in data}
    wb = Workbook()
    hdr_font = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDEBF7")

    ws = wb.active
    ws.title = "entries"
    cols = list(data[0].keys())
    ws.append(cols)
    for r in data:
        ws.append([r[c] for c in cols])
    for c in ws[1]:
        c.font, c.fill = hdr_font, fill
    ws.freeze_panes = "B2"
    autosize(ws)

    ws = wb.create_sheet("T1_features")
    ws.append(["Tool", "Entry id"] + list(FEATURES.values()) + ["Evidence: " + v for v in FEATURES.values()])
    for name, ids, codes, ev in t1_rows(by_id):
        ws.append([name, ids] + codes + ev)
        row = ws.max_row
        for j, e in enumerate(ev):
            ws.cell(row=row, column=3 + j).comment = Comment(e[:1500], "related_work.csv")
    ws.append([THIS_WORK[0], "-"] + THIS_WORK[1].split() + [THIS_WORK[2]] * len(FEATURES))
    ws.append([])
    ws.append(["Codes: Y = offered (seen in inspected docs/repo); P = partial or building block only; "
               "N = not offered per inspected docs; ? = not inspected or not stated. Y? = docs suggest yes but unclear."])
    for c in ws[1]:
        c.font, c.fill = hdr_font, fill
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    autosize(ws, 45)

    ws = wb.create_sheet("categories")
    ws.append(["Category", "Name", "Entries", "Crossref-verified DOI", "arXiv-verified (no DOI)", "DataCite DOI",
               "No DOI (repo/docs inspected)", "Summary"])
    for k, nm in CATEGORY_NAMES.items():
        rs = [r for r in data if r["category"] == k]
        cr = sum("Crossref OK" in r["id_check"] for r in rs)
        ax = sum("Crossref OK" not in r["id_check"] and "arXiv" in r["id_check"] for r in rs)
        dc = sum(r["doi"].startswith("10.5281/") and "DataCite OK" in r["id_check"] for r in rs)
        nd = len(rs) - cr - ax - dc
        ws.append([k, nm, len(rs), cr, ax, dc, nd, CATEGORY_SUMMARY[k]])
    ws.append(["all", "", len(data)])
    for c in ws[1]:
        c.font, c.fill = hdr_font, fill
    autosize(ws, 90)

    wb.save(XLSX_PATH)
    print(f"wrote {XLSX_PATH} ({len(data)} entries, {len(T1)} T1 rows); categories:",
          dict(Counter(r["category"] for r in data)))

    if "--md" in sys.argv:
        print("\n| Tool | Id | " + " | ".join(FEATURES.values()) + " |")
        print("|" + "---|" * (len(FEATURES) + 2))
        for name, ids, codes, _ in t1_rows(by_id):
            print(f"| {name} | {ids} | " + " | ".join(codes) + " |")
        print(f"| {THIS_WORK[0]} | - | " + " | ".join(THIS_WORK[1].split()) + " |")


if __name__ == "__main__":
    main()
