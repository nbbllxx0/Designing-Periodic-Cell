"""B7: does the released tree regenerate the paper assets? Copy release/staging/amm-0.2.0, add the data bundle
(results/atlas) and the 8 STL files F7 reads (release/excluded_large.tsv, cited), run the released (redacted)
scripts/paper/make_all.py there, and compare every regenerated table and figure file with the staged copy."""
import csv, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
R = Path(r"C:\AI\AgenticMetamaterials")
S = R / "release" / "staging" / "amm-0.2.0"
D = Path(r"C:\AI\AgenticMetamaterials_workspaces\b7\repro_tree")
if D.exists():
    shutil.rmtree(D)
shutil.copytree(S, D)
before = {p.relative_to(D).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (D / "paper").rglob("*") if p.is_file()}
for p in (R / "release" / "data_bundle" / "amm-data-1").iterdir():
    if p.name not in ("README.md", "SHA256SUMS", "data_manifest.json", "NOTES.md"):
        shutil.copy2(p, D / "results" / "atlas" / p.name)
n_stl = 0
with open(R / "release" / "excluded_large.tsv", encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["cited_by_paper_assets"].startswith("yes"):
            (D / r["path"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(R / r["path"], D / r["path"]); n_stl += 1
t0 = time.time()
r = subprocess.run([sys.executable, "-B", "scripts/paper/make_all.py"], cwd=D, capture_output=True, text=True)
secs = time.time() - t0
after = {p.relative_to(D).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (D / "paper").rglob("*") if p.is_file()}
same = sorted(k for k in before if after.get(k) == before[k])
diff = sorted(k for k in before if k in after and after[k] != before[k])
new = sorted(k for k in after if k not in before)
out = dict(exit=r.returncode, seconds=round(secs, 1), stl_added=n_stl, staged_paper_files=len(before), identical=len(same),
           differing=diff, new_files=new, private_hook_line=[l for l in r.stdout.splitlines() if "F1" in l or "main_diagram" in l],
           stdout_tail=r.stdout.splitlines()[-6:], stderr_tail=r.stderr.splitlines()[-6:])
Path(r"C:\AI\AgenticMetamaterials_workspaces\b7\repro_make_all.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
