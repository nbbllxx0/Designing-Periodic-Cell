"""B7: copy the checkout (without scripts/paper_private, external, node_modules) and run scripts/paper/make_all.py
there with an audit hook that records every file opened for reading. Output: the read set (JSON)."""
import json, os, shutil, subprocess, sys
from pathlib import Path
SRC = Path(r"C:\AI\AgenticMetamaterials")
DST = Path(r"C:\AI\AgenticMetamaterials_workspaces\b7\trace_copy")
if DST.exists():
    shutil.rmtree(DST)
IGN = {"node_modules", "external", "paper_private", "__pycache__", ".pytest_cache", "pilot", "repos_notes", ".claude"}
shutil.copytree(SRC, DST, ignore=lambda d, names: [n for n in names if n in IGN])
hook = DST / "_trace_hook.py"
hook.write_text('''
import sys, json, atexit, os
_seen = set()
def _h(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        mode = args[1] if len(args) > 1 else "r"
        if mode is None or ("w" not in str(mode) and "a" not in str(mode) and "x" not in str(mode)):
            _seen.add(os.path.abspath(os.fsdecode(args[0])))
sys.addaudithook(_h)
def _dump():
    with open(os.environ["TRACE_OUT"], "w", encoding="utf-8") as f:
        json.dump(sorted(_seen), f, indent=0)
atexit.register(_dump)
''')
out = Path(r"C:\AI\AgenticMetamaterials_workspaces\b7\trace_reads.json")
env = dict(os.environ, TRACE_OUT=str(out), PYTHONDONTWRITEBYTECODE="1")
code = f"import sys; sys.path.insert(0, r'{DST}'); import _trace_hook; import runpy; sys.argv=['make_all.py']; runpy.run_path(r'{DST / 'scripts/paper/make_all.py'}', run_name='__main__')"
r = subprocess.run([sys.executable, "-c", code], cwd=DST, env=env, capture_output=True, text=True)
print(r.stdout[-3000:]); print(r.stderr[-3000:]); print("rc", r.returncode)
reads = json.loads(out.read_text())
inside = sorted({Path(p).resolve().relative_to(DST.resolve()).as_posix() for p in reads if Path(p).resolve().is_relative_to(DST.resolve())})
(out.with_name("trace_reads_rel.json")).write_text(json.dumps(inside, indent=0))
print(len(inside))
