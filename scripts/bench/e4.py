"""E4 full runs (plan section 3; pre-registration plan/E4_PREREG.md; audit 2026-11-06, results/audit/).

    e4.py plan    --tag e4 [--reps 3] [--claude-reps 1] [--seed 20261107]   -> results/bench/<tag>/jobs.json (once)
    e4.py run     --tag e4 --phase K [--limit N]       (phases: PHASES below; --ids/--arms/... only with --smoke)
    e4.py score   --tag e4 [--done-only] [--no-certify]                     -> scores.json, summary.json
    e4.py analyze --tag e4 [--interim] [--amended A1|A2]                       -> analysis[_A*].json (pre-registered tests)
    e4.py quota-check --tag e4                                               -> amendments/quota_check.json (A1)
    run under amendment A1: add --amendment A1 (phases 1 and 3 only; see AMENDMENTS)

Design (audit F03, F08, F09):
  * jobs.json is written once and never changed: one job per (provider, arm, repeat, brief); arm O (no LLM, oracle
    spec) once per non-ambiguous brief. Order: repeat blocks; inside a block the briefs are shuffled and so is the arm
    order per brief (seeded). Every scheduled job is scored; a job without a session log is no_answer.
  * isolation: each job runs in an opaque workspace outside the repository (WS_ROOT/<tag>/<hash>/) holding only a
    de-identified request (text, intended spec and oracle facts; no id, class or truth). Codex runs with a read-only
    sandbox in which no shell command can run; Claude runs with no built-in tools. The finished workspace is moved to
    results/bench/<tag>/jobs/<job_id>/.
  * serial: one runner at a time (WS_ROOT/e4_runner.lock; a second runner refuses to start) and one job at a time
    under the solver lock shared with every other solver runner (WS_ROOT/gpu.lock: scoring certificates,
    witness_recert, run_indep); a job starts only when nvidia-smi answers and lists no Python compute process (fail
    closed: an unreadable GPU state stops the run). Arm O runs in a child process, so the runner never holds a CUDA
    context itself.
  * frozen identity: `run` refuses to start when the tool code, checker, full source, brief data, atlas and error
    model, or the pre-registration text differ from the plan-time snapshot (jobs.json meta), unless --allow-drift
    (logged in run_log.txt).
  * attempts: a workspace with a run.json (run_brief writes it only at the end; interrupted before the move) is
    recovered, never rerun; one without run.json (a crash) is moved to attempts/ and rerun; timeouts and errors are
    final and scored as they are.
  * analysis: refuses unless every primary job is finished and scored, no run record is newer than the scores, the
    scores used the frozen checker, and every compared spec was scored in both arms (else --interim, labelled).
  * hidden files: the de-identified request (with the oracle facts) lives in WS_ROOT/<tag>/_hidden/, outside every
    agent workspace.
  * partition: `development` = intended specs seen in the pilot or the near-miss runs (incl. ambiguous pairs);
    `confirmatory` = the rest. The primary analysis uses the confirmatory partition only.
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from amm import bench, certify, tools  # noqa: E402
import scoring  # noqa: E402

BRIEFS = ROOT / "bench" / "v1" / "briefs"
WS_ROOT = ROOT.parent / "AgenticMetamaterials_workspaces"  # outside the repository (labels live in bench/)
DEV_RUNS = ("pilot", "nearmiss")
# execution phases (plan/E4_PREREG.md section 4); a job belongs to the first phase that selects it
PHASES = {1: dict(provider="codex", arms="DBC", reps=(1,), partition="confirmatory"),
          2: dict(provider="codex", arms="DBC", reps=(2, 3), partition="confirmatory"),
          3: dict(provider="none", arms="O", reps=(1,), partition=None),
          4: dict(provider="codex", arms="DBC", reps=(1, 2, 3), partition="development"),
          5: dict(provider="claude", arms="DBC", reps=(1,), partition=None)}
PRIMARY_PHASES = (1, 2)
# Protocol amendments (plan/E4_PREREG.md section 9). A1 (2026-11-07): the paper became a software paper; phases 2, 4
# and 5 are cut for overlap and cost, decided before any confirmatory outcome was scored or inspected (29 phase-1 jobs
# had run). Only this harness file and the pre-registration may differ from the plan-time snapshot; tool code,
# checker, brief data, atlas, error model, prompts, budgets and scorer must be unchanged.
# A2 (2026-11-07, after phase 1 finished and before any job was scored): phase 3 (arm O) is also cut, to keep total
# compute within the approved 40-60 h; arm O was a descriptive reference only, never part of a pre-registered test.
AMENDMENTS = {"A1": dict(date="2026-11-07", primary_phases=(1,), run_phases=(1, 3), cut_phases=(2, 4, 5),
                         allowed_changes=("scripts/bench/e4.py", "plan/E4_PREREG.md"),
                         note="A1: Codex repeat 1 only, phases 2/4/5 cut before any confirmatory outcome was scored; "
                              "repeat-level reliability not estimable"),
              "A2": dict(date="2026-11-07", primary_phases=(1,), run_phases=(1,), cut_phases=(2, 3, 4, 5),
                         allowed_changes=("scripts/bench/e4.py", "plan/E4_PREREG.md"),
                         note="A2: Codex repeat 1 only, phases 2/3/4/5 cut before any confirmatory outcome was "
                              "scored (arm-O reference not run); repeat-level reliability not estimable")}
# provider usage-limit events (amendment A1): searched only in error channels (CLI stderr, error/failed events)
QUOTA_RE = r"usage limit|rate[ _-]?limit|too many requests|\b429\b|quota|limit reached|limit will reset"


def in_phase(j, k) -> bool:
    ph = PHASES[k]
    return (j["provider"] == ph["provider"] and j["arm"] in ph["arms"] and j["rep"] in ph["reps"]
            and (ph["partition"] is None or j["partition"] == ph["partition"]))


def full_source_hash() -> str:
    h = hashlib.sha256()
    for d in ("amm", "scripts/bench"):
        for f in sorted((ROOT / d).glob("*.py")):
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def brief_data_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(BRIEFS.glob("*.json")):
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def data_hash() -> str:
    """Atlas cells and the calibrated error model: tool results depend on them (final check 2026-11-06)."""
    h = hashlib.sha256()
    atlas = ROOT / "results" / "atlas"
    for f in sorted(atlas.glob("atlas_nu*.jsonl")) + [atlas / "error_model.json"]:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def prereg_hash() -> str:
    return hashlib.sha256((ROOT / "plan" / "E4_PREREG.md").read_bytes()).hexdigest()[:16]


def identity() -> dict:
    return dict(code=tools.code_hash(), checker=certify.checker_hash(), full_source=full_source_hash(),
                briefs=brief_data_hash(), data=data_hash(), prereg=prereg_hash())


def opt(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def load_briefs() -> dict:
    man = json.loads((ROOT / "bench" / "v1" / "manifest.json").read_text(encoding="utf-8"))
    return {i: json.loads((BRIEFS / f"{i}.json").read_text(encoding="utf-8")) for i in man["ids"]}


def partition(briefs: dict) -> dict:
    """development = specs of briefs run before E4 (pilot, near-miss) and every brief sharing such a spec."""
    run = set()
    for tag in DEV_RUNS:
        for arm in ("B", "C"):
            d = ROOT / "results" / "bench" / tag / arm
            if d.exists():
                run |= {p.name for p in d.iterdir() if (p / "session" / "session.jsonl").exists()}
    dev_keys = {scoring.spec_key(briefs[i]) for i in run if i in briefs}
    return {i: ("development" if scoring.spec_key(b) in dev_keys else "confirmatory") for i, b in briefs.items()}


def job_id(provider, arm, rep, bid) -> str:
    return f"{provider}-{arm}-r{rep}-{bid}"


def plan():
    out = ROOT / "results" / "bench" / opt("--tag", "e4")
    f = out / "jobs.json"
    if f.exists():
        raise SystemExit(f"{f} exists: the job manifest is immutable")
    briefs = load_briefs()
    part = partition(briefs)
    rng = random.Random(int(opt("--seed", "20261107")))
    jobs = []
    for provider, reps in (("codex", int(opt("--reps", "3"))), ("claude", int(opt("--claude-reps", "1")))):
        for rep in range(1, reps + 1):
            ids = sorted(briefs)
            rng.shuffle(ids)
            for bid in ids:
                arms = list("DBC")
                rng.shuffle(arms)
                for arm in arms:
                    jobs.append(dict(job=job_id(provider, arm, rep, bid), provider=provider, arm=arm, rep=rep,
                                     brief=bid, partition=part[bid]))
    for bid in sorted(briefs):  # deterministic reference, oracle spec: once per non-ambiguous brief
        if not briefs[bid]["cls"].startswith("ambiguous"):
            jobs.append(dict(job=job_id("none", "O", 1, bid), provider="none", arm="O", rep=1, brief=bid,
                             partition=part[bid]))
    for i, j in enumerate(jobs):
        j["order"] = i
        j["workspace"] = hashlib.sha256(f"{opt('--tag', 'e4')}/{j['job']}".encode()).hexdigest()[:12]
    out.mkdir(parents=True, exist_ok=True)
    snapshot(out / "snapshot")
    meta = dict(created=time.strftime("%Y-%m-%d %H:%M:%S"), seed=int(opt("--seed", "20261107")),
                **identity(), n_jobs=len(jobs),
                partition_counts={p: sum(v == p for v in part.values()) for p in ("development", "confirmatory")},
                prereg_file="plan/E4_PREREG.md")
    f.write_text(json.dumps(dict(meta=meta, jobs=jobs), indent=1), encoding="utf-8")
    print(json.dumps(meta, indent=1))


def snapshot(dest: Path):
    """Source, data hashes and environment at plan time (audit F09): a zip of amm/ and scripts/, SHA-256 of the
    benchmark, atlas and error-model files, the package list and the CLI versions."""
    import zipfile
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest / "source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for d in ("amm", "scripts", "tests"):
            for f in sorted((ROOT / d).rglob("*.py")):
                z.write(f, f.relative_to(ROOT))
        z.write(ROOT / "pyproject.toml", "pyproject.toml")
    hashes = {}
    for pat in ("bench/v1/briefs/*.json", "bench/v1/manifest.json", "bench/v1/plan.json", "results/atlas/*.jsonl",
                "results/atlas/*error*.json"):
        for f in sorted(ROOT.glob(pat)):
            hashes[str(f.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(f.read_bytes()).hexdigest()
    (dest / "data_hashes.json").write_text(json.dumps(hashes, indent=1), encoding="utf-8")
    env = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
    vers = {}
    for exe in ("codex", "claude", "nvidia-smi"):
        try:
            vers[exe] = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()[:300]
        except Exception as e:  # noqa: BLE001
            vers[exe] = f"unavailable: {e}"
    (dest / "environment.txt").write_text(f"python {sys.version}\n{json.dumps(vers, indent=1)}\n\n{env}",
                                          encoding="utf-8")


def load_jobs(tag) -> list[dict]:
    return json.loads((ROOT / "results" / "bench" / tag / "jobs.json").read_text(encoding="utf-8"))["jobs"]


def gpu_busy() -> list[str] | None:
    """Compute processes on the GPU, or None when the state cannot be read (treated as busy: fail closed)."""
    try:
        p = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    if p.returncode != 0:
        return None
    # On Windows (WDDM) every desktop app with a GPU context is listed; the work that matters is Python solver
    # processes (MCP servers, certificate and search workers of this or any other project).
    # The runner itself is excluded: arm O runs the solver in-process, so after an O job this process holds a CUDA
    # context and would otherwise wait on itself forever (smoke run, 2026-11-06).
    import os
    own = str(os.getpid())
    return [l.strip() for l in p.stdout.splitlines()
            if l.strip() and "python" in l.lower() and l.split(",")[0].strip() != own]


def wait_gpu(log, max_unknown=600):
    """Block until the GPU is idle. Busy: wait indefinitely (logged every 10 min). Unreadable for max_unknown s:
    stop the run."""
    t0, last, t_unknown = time.time(), 0.0, None
    while True:
        busy = gpu_busy()
        if busy == []:
            return round(time.time() - t0, 1)
        if busy is None:
            t_unknown = t_unknown or time.time()
            if time.time() - t_unknown > max_unknown:
                raise SystemExit("GPU state unreadable (nvidia-smi) for 10 min: stopping (fail closed)")
        else:
            t_unknown = None
        if time.time() - last > 600:
            log(f"waiting for the GPU: {busy if busy is not None else 'state unreadable'}")
            last = time.time()
        time.sleep(30)


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return True


class GpuLock:
    """Exclusive lock for GPU/solver work shared by every runner of this project (WS_ROOT/gpu.lock). A lock left
    by a dead process is removed."""

    def __init__(self, who: str, name: str = "gpu.lock", wait: bool = True):
        self.path, self.who, self.wait = WS_ROOT / name, who, wait

    def __enter__(self):
        import os
        WS_ROOT.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps(dict(pid=os.getpid(), who=self.who, t=time.time())).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    info = {}
                if info.get("pid") and not _pid_alive(int(info["pid"])):
                    self.path.unlink(missing_ok=True)
                    continue
                if not self.wait:
                    raise SystemExit(f"{self.path.name} is held by {info}: refusing to start a second runner")
                time.sleep(15)

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


def deidentified(brief: dict) -> dict:
    return dict(text=brief["text"], intended=brief["intended"], oracle=brief.get("oracle", {}))


def k_phase():
    return int(opt("--phase")) if opt("--phase") else None


def select(jobs):
    """--phase K (E4), or explicit filters with --smoke (development briefs only)."""
    if opt("--phase"):
        k = int(opt("--phase"))
        return [j for j in jobs if in_phase(j, k)]
    if "--smoke" not in sys.argv:
        raise SystemExit("give --phase K (or --smoke with filters)")
    prov, arms, reps, ids = opt("--provider"), opt("--arms"), opt("--reps"), opt("--ids")
    out = [j for j in jobs if (not prov or j["provider"] == prov) and (not arms or j["arm"] in arms.split(","))
           and (not reps or j["rep"] in {int(r) for r in reps.split(",")}) and (not ids or j["brief"] in ids.split(","))]
    if any(j["partition"] != "development" for j in out):
        raise SystemExit("--smoke runs development briefs only")
    return out


def harness_hash() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()[:16]


def changed_source_files(tag) -> list[str]:
    """Files of amm/*.py and scripts/bench/*.py (the full_source set) that differ from the plan-time source zip,
    plus files added or removed."""
    import zipfile
    z = zipfile.ZipFile(ROOT / "results" / "bench" / tag / "snapshot" / "source.zip")
    def in_set(n):
        return n.endswith(".py") and ((n.startswith("amm/") and n.count("/") == 1)
                                      or (n.startswith("scripts/bench/") and n.count("/") == 2))
    old = {n.replace("\\", "/"): z.read(n) for n in z.namelist() if in_set(n.replace("\\", "/"))}
    new = {}
    for d in ("amm", "scripts/bench"):
        for f in sorted((ROOT / d).glob("*.py")):
            new[str(f.relative_to(ROOT)).replace("\\", "/")] = f.read_bytes()
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def check_amendment(tag, name, meta, now, drift, log) -> dict:
    """Narrow override for a logged protocol amendment: only the files the amendment names may differ."""
    am = AMENDMENTS.get(name)
    if am is None:
        raise SystemExit(f"unknown amendment {name}")
    bad_keys = sorted(k for k in drift if k not in ("full_source", "prereg"))
    changed = changed_source_files(tag) if "full_source" in drift else []
    bad_files = [f for f in changed if f not in am["allowed_changes"]]
    if bad_keys or bad_files:
        raise SystemExit(f"amendment {name} refuses: identity fields {bad_keys} or files {bad_files} changed "
                         f"(only {am['allowed_changes']} may differ)")
    rec = dict(amendment=name, **am, plan_identity={k: meta.get(k) for k in now}, amended_identity=now,
               harness=harness_hash(), changed_files=changed, t=time.strftime("%Y-%m-%d %H:%M:%S"))
    d = ROOT / "results" / "bench" / tag / "amendments"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.json"
    hist = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    if not hist or hist[-1]["amended_identity"] != now or hist[-1]["harness"] != rec["harness"]:
        hist.append(rec)
        f.write_text(json.dumps(hist, indent=1, default=list), encoding="utf-8")
    log(f"AMENDMENT {name}: drift {sorted(drift)} accepted; changed files {changed}; harness {rec['harness']}")
    return rec


def check_frozen(tag, log):
    meta = json.loads((ROOT / "results" / "bench" / tag / "jobs.json").read_text(encoding="utf-8"))["meta"]
    now = identity()
    drift = {k: (meta.get(k), v) for k, v in now.items() if meta.get(k) != v}
    if opt("--amendment"):
        check_amendment(tag, opt("--amendment"), meta, now, drift, log)
        return now
    if drift:
        msg = f"identity differs from the plan-time snapshot: {drift}"
        if "--allow-drift" not in sys.argv:
            raise SystemExit(msg + " (refusing; --allow-drift to override, logged)")
        log("ALLOWED DRIFT: " + msg)
    return now


def quota_event(ws: Path, rec: dict) -> str | None:
    """A provider usage-limit stop (amendment A1): an error-channel message matching QUOTA_RE in a session that did
    not end normally (non-zero exit, not done, or no final answer). Transient retries inside a session that finished
    with an answer are not interruptions."""
    import re
    ended_normally = rec.get("status") == "done" and rec.get("returncode") in (0, None) and bool(rec.get("final"))
    if ended_normally and not rec.get("error"):
        return None
    texts = [str(rec.get("error") or ""), str(rec.get("stderr_tail") or "")]
    for sub in ("codex", "claude"):
        d = ws / sub
        if (d / "stderr.txt").exists():
            texts.append((d / "stderr.txt").read_text(encoding="utf-8", errors="replace")[-20000:])
        if (d / "events.jsonl").exists():
            for line in (d / "events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    ev = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if ev.get("type") in ("error", "turn.failed") or (ev.get("type") == "result" and ev.get("is_error")):
                    texts.append(json.dumps(ev))
    for t in texts:
        m = re.search(QUOTA_RE, t, re.IGNORECASE)
        if m:
            return t[max(0, m.start() - 200): m.end() + 200]
    return None


O_CHILD = ("import json, sys; sys.path.insert(0, sys.argv[1]); from amm import bench; "
           "bench.run_brief(sys.argv[2], sys.argv[3], profile='O', provider='none')")


def _run_O_child(req: Path, ws: Path) -> dict:
    """Arm O in a child process: the runner itself never opens a CUDA context, so the GPU-idle check cannot wait on
    a context the runner holds (final check 2026-11-06)."""
    p = subprocess.run([sys.executable, "-B", "-c", O_CHILD, str(ROOT), str(req), str(ws)], capture_output=True,
                       text=True)
    f = ws / "run.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return dict(status="error", error=f"arm O child exited {p.returncode} without run.json: {p.stderr[-1500:]}")


def run():
    tag = opt("--tag", "e4")
    with GpuLock(f"e4 runner {' '.join(sys.argv[1:])}", name="e4_runner.lock", wait=False):  # one runner at a time
        _run(tag)


def _run(tag):
    out_root = ROOT / "results" / "bench" / tag
    jobs = sorted(select(load_jobs(tag)), key=lambda j: j["order"])
    limit = int(opt("--limit", "0")) or None
    logf = out_root / "run_log.txt"

    def log(msg):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(logf, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    ident = check_frozen(tag, log)
    briefs = load_briefs()
    hidden = WS_ROOT / tag / "_hidden"
    n = 0
    log(f"run: {len(jobs)} jobs selected ({' '.join(sys.argv[1:])})")

    amendment = opt("--amendment")
    if amendment and k_phase() not in AMENDMENTS[amendment]["run_phases"]:
        raise SystemExit(f"phase {k_phase()} is cut by amendment {amendment}")

    def finalize(j, ws, rec, waited, recovered=False):
        rec.update(job=j["job"], brief=j["brief"], rep=j["rep"], partition=j["partition"], gpu_wait_s=waited,
                   harness=harness_hash(), amendment=amendment, **ident)
        if recovered:
            rec["recovered"] = True
        tmp = ws / "run.json.tmp"
        tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        tmp.replace(ws / "run.json")  # atomic

    for j in jobs:
        dest = out_root / "jobs" / j["job"]
        if (dest / "run.json").exists():
            continue
        if limit and n >= limit:
            break
        ws = WS_ROOT / tag / j["workspace"]
        if (ws / "run.json").exists():
            # finished (run_brief writes run.json only at the end), but interrupted before the move: recover, never
            # rerun -- also when the E4 fields were not yet added
            rec = json.loads((ws / "run.json").read_text(encoding="utf-8"))
            if not rec.get("job"):
                finalize(j, ws, rec, None, recovered=True)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ws), str(dest))
            log(f"recovered finished workspace of {j['job']}")
            continue
        for stale in (ws, dest):
            if stale.exists():  # a crashed attempt: kept, never overwritten
                att = out_root / "attempts" / f"{j['job']}_{stale.parent.name}_{time.strftime('%Y%m%d%H%M%S')}"
                att.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(stale), str(att))
                log(f"moved crashed attempt of {j['job']} to attempts/{att.name}")
        with GpuLock(f"e4 {tag} {j['job']}"):
            waited = wait_gpu(log)
            ws.mkdir(parents=True)
            hidden.mkdir(parents=True, exist_ok=True)
            req = hidden / f"{j['workspace']}.json"
            req.write_text(json.dumps(deidentified(briefs[j["brief"]]), indent=1, ensure_ascii=False),
                           encoding="utf-8")
            log(f"start {j['job']} (order {j['order']}, {j['partition']}, waited {waited} s for the GPU)")
            if j["arm"] == "O":
                rec = _run_O_child(req, ws)
            else:
                kw = dict(timeout=float(opt("--timeout"))) if opt("--timeout") else {}
                rec = bench.run_brief(req, ws, profile=j["arm"], provider=j["provider"], **kw)
            hit = quota_event(ws, rec) if j["provider"] in ("codex", "claude") else None
            if hit:
                # amendment A1: an infrastructure interruption, not an answer. Keep the attempt with its logs and
                # costs, never score it, and stop; the same manifest job runs again after the limit resets.
                att = out_root / "attempts" / f"{j['job']}_infra_{time.strftime('%Y%m%d%H%M%S')}"
                att.parent.mkdir(parents=True, exist_ok=True)
                (ws / "infra.json").write_text(json.dumps(dict(status="infra_interruption", match=hit, rec=rec,
                                                               harness=harness_hash(), amendment=amendment),
                                                          indent=1, default=str), encoding="utf-8")
                (ws / "run.json").unlink(missing_ok=True)
                shutil.move(str(ws), str(att))
                log(f"INFRA_INTERRUPTION {j['job']}: provider usage limit ({hit[:160]!r}); attempt kept in "
                    f"attempts/{att.name}; stopping, rerun after the reset")
                raise SystemExit(3)
            finalize(j, ws, rec, waited)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ws), str(dest))
        log(f"done  {j['job']} status={rec.get('status')} rc={rec.get('returncode')} wall={rec.get('wall_s')}s"
            + (f" error={rec['error']}" if rec.get("error") else ""))
        n += 1
    log(f"run finished: {n} jobs this call")


def score():
    """Scores every scheduled job (or finished ones with --done-only). Post-hoc certificates run under the shared
    solver lock, so they never overlap an E4 job (final check 2026-11-06). No GPU-idle wait here: the lock alone
    guarantees no job is running, and waiting on idle could deadlock against a runner's MCP children."""
    if "--no-certify" in sys.argv:
        return _score()
    with GpuLock(f"e4 score {' '.join(sys.argv[1:])}"):
        return _score()


def _score():
    tag = opt("--tag", "e4")
    out_root = ROOT / "results" / "bench" / tag
    briefs = load_briefs()
    recs = []
    for j in sorted(load_jobs(tag), key=lambda j: j["order"]):
        d = out_root / "jobs" / j["job"]
        if "--done-only" in sys.argv and not (d / "run.json").exists():
            continue
        if j["arm"] == "O" and briefs[j["brief"]]["cls"].startswith("ambiguous"):
            continue
        r = scoring.score_session(briefs[j["brief"]], d, certify_releases="--no-certify" not in sys.argv)
        r.update(job=j["job"], provider=j["provider"], arm=j["arm"], rep=j["rep"], partition=j["partition"])
        recs.append(r)
    (out_root / "scores.json").write_text(json.dumps(recs, indent=1, default=float), encoding="utf-8")
    (out_root / "scores_meta.json").write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%d %H:%M:%S"), t=time.time(), n=len(recs), done_only="--done-only" in sys.argv,
        certified="--no-certify" not in sys.argv, checker=certify.checker_hash(),
        scoring=hashlib.sha256((ROOT / "scripts" / "bench" / "scoring.py").read_bytes()).hexdigest()[:16],
        jobs=sorted(r["job"] for r in recs)), indent=1), encoding="utf-8")
    groups = sorted({(r["provider"], r["arm"], r["rep"]) for r in recs})
    summ = {}
    for g in groups:
        rs = [r for r in recs if (r["provider"], r["arm"], r["rep"]) == g]
        summ["/".join(map(str, g))] = {p: scoring.summarize([r for r in rs if r["partition"] == p])
                                       for p in ("confirmatory", "development")}
    (out_root / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: {p: dict(n=v[p].get("n"), correct=v[p].get("correct"), decided=v[p].get("decided"),
                                  unsupported=v[p].get("unsupported_releases"))
                          for p in v} for k, v in summ.items()}, indent=1))


def analyze():
    """Pre-registered analysis (plan/E4_PREREG.md)."""
    import numpy as np
    tag = opt("--tag", "e4")
    out_root = ROOT / "results" / "bench" / tag
    recs = json.loads((out_root / "scores.json").read_text(encoding="utf-8"))
    meta = json.loads((out_root / "scores_meta.json").read_text(encoding="utf-8"))
    plan_meta = json.loads((out_root / "jobs.json").read_text(encoding="utf-8"))["meta"]
    interim = "--interim" in sys.argv
    amended = opt("--amended")
    if amended and amended not in AMENDMENTS:
        raise SystemExit(f"unknown amendment {amended}")
    primary_phases = AMENDMENTS[amended]["primary_phases"] if amended else PRIMARY_PHASES
    need = [j for j in load_jobs(tag) if any(in_phase(j, k) for k in primary_phases)]
    need_ids = {j["job"] for j in need}
    missing = [j["job"] for j in need if not (out_root / "jobs" / j["job"] / "run.json").exists()]
    # completeness and freshness of the scores (final check 2026-11-06): every finished primary job scored, no run
    # record newer than the scores, scores made with the frozen checker and certifying releases
    scored = {r["job"] for r in recs}
    finished = [j["job"] for j in need if j["job"] not in missing]
    problems = []
    if any(j not in scored for j in finished):
        problems.append(f"{sum(j not in scored for j in finished)} finished primary jobs not scored")
    stale = [j for j in finished if (out_root / "jobs" / j / "run.json").stat().st_mtime > meta["t"]]
    if stale:
        problems.append(f"{len(stale)} run records newer than scores.json")
    if meta["checker"] != plan_meta["checker"] or not meta["certified"]:
        problems.append(f"scores not made with the frozen checker and certification ({meta['checker']}, "
                        f"certified={meta['certified']})")
    if (missing or problems) and not interim:
        raise SystemExit(f"confirmatory analysis refused: {len(missing)} of {len(need)} primary jobs not finished; "
                         f"{problems} (--interim for a labelled interim look; rescore with `e4.py score`)")
    conf = [r for r in recs if r["partition"] == "confirmatory" and r["provider"] in ("codex", "none")]
    if amended:  # A1/A2: only the primary jobs the amendment keeps (Codex repeat 1) plus the arm-O reference if run
        conf = [r for r in conf if r["job"] in need_ids or r["arm"] == "O"]

    def per_spec(arm, metric, level=None):
        out = {}
        for r in conf:
            if r["arm"] != arm or (level and r["truth_level"] not in level):
                continue
            v = metric(r)
            if v is None:
                continue
            out.setdefault(r["spec_key"], []).append(float(v))
        return {k: float(np.mean(v)) for k, v in out.items()}

    def paired(a, b, metric, level=None, n_boot=10000, seed=1):
        pa, pb = per_spec(a, metric, level), per_spec(b, metric, level)
        keys = sorted(set(pa) & set(pb))
        dropped = sorted(set(pa) ^ set(pb))  # a spec scored in one arm only: reported, never silently dropped
        if dropped and not interim:
            raise SystemExit(f"{a} vs {b}: {len(dropped)} specs scored in one arm only ({dropped[:5]}...)")
        if not keys:
            return dict(n_specs=0, dropped_specs=dropped)
        d = np.array([pa[k] - pb[k] for k in keys])
        rng = np.random.default_rng(seed)
        boots = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
        pos, neg = int((d > 0).sum()), int((d < 0).sum())
        # paired sign-flip permutation test of the MEAN difference (re-audit #1), two-sided, 100,000 draws
        flips = rng.choice([-1.0, 1.0], size=(100_000, len(d)))
        perm = np.abs((flips * d).mean(axis=1))
        p_perm = float((np.sum(perm >= abs(d.mean()) - 1e-12) + 1) / (len(perm) + 1))
        return dict(n_specs=len(keys), dropped_specs=dropped, mean_a=float(np.mean([pa[k] for k in keys])),
                    mean_b=float(np.mean([pb[k] for k in keys])), diff=float(d.mean()),
                    ci95=[float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
                    specs_a_better=pos, specs_b_better=neg, p=p_perm, test="paired sign-flip permutation, mean")
    correct = lambda r: r["correct"]  # noqa: E731
    unsupported = lambda r: r["outcome"] in ("silent_failure", "unverified_release")  # noqa: E731
    false_ref = lambda r: r["outcome"] == "false_refusal"  # noqa: E731
    overclaim = lambda r: r["outcome"] == "overclaim"  # noqa: E731
    resolved = lambda r: bool(r.get("asked_relevant")) if r["ambiguous"] else None  # noqa: E731
    primary = paired("C", "B", correct, ("witnessed", "proven"))
    sec = dict(unsupported_release_B_minus_C=paired("B", "C", unsupported),
               false_refusal_B_minus_C=paired("B", "C", false_ref, ("witnessed",)),
               overclaim_B_minus_C=paired("B", "C", overclaim, ("unresolved",)),
               correct_C_minus_D=paired("C", "D", correct, ("witnessed", "proven")),
               resolved_ambiguous_C_minus_B=paired("C", "B", resolved))
    ps = sorted((v.get("p", 1.0), k) for k, v in sec.items())
    holm, run_max = {}, 0.0
    for i, (p, k) in enumerate(ps):
        run_max = max(run_max, min(1.0, (len(ps) - i) * p))
        holm[k] = run_max
    for k in sec:
        sec[k]["p_holm"] = holm[k]
    ref_O = {lvl: dict(n=len(v), correct=sum(bool(r["correct"]) for r in v),
                       appropriate=sum(bool(r["appropriate"]) for r in v))
             for lvl in ("witnessed", "proven", "unresolved")
             for v in [[r for r in conf if r["arm"] == "O" and r["truth_level"] == lvl]]}
    res = dict(amendment=amended, primary_phases=list(primary_phases),
               interim=bool(missing or problems or interim), missing_primary_jobs=len(missing),
               score_problems=problems, scores_meta={k: meta[k] for k in ("created", "n", "checker", "scoring")},
               primary_C_minus_B_correct=primary, secondary=sec, reference_O=ref_O,
               note="confirmatory partition, Codex; per-spec means over repeats and presentations; cluster "
                    "bootstrap over specs; two-sided paired sign-flip permutation test of the mean spec-level "
                    "difference; Holm over secondaries"
                    + (f"; AMENDED ({AMENDMENTS[amended]['note']})" if amended else ""))
    name = f"analysis_{amended}.json" if amended else "analysis.json"
    (out_root / name).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def quota_check():
    """Amendment A1, applied symmetrically: list finished jobs whose logs show a provider usage-limit stop."""
    tag = opt("--tag", "e4")
    out_root = ROOT / "results" / "bench" / tag
    hits = {}
    for d in sorted((out_root / "jobs").iterdir()):
        f = d / "run.json"
        if f.exists():
            h = quota_event(d, json.loads(f.read_text(encoding="utf-8")))
            if h:
                hits[d.name] = h
    n = sum(1 for d in (out_root / "jobs").iterdir() if (d / "run.json").exists())
    res = dict(t=time.strftime("%Y-%m-%d %H:%M:%S"), checked=n, quota_events=hits, harness=harness_hash())
    (out_root / "amendments").mkdir(parents=True, exist_ok=True)
    (out_root / "amendments" / "quota_check.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"plan": plan, "run": run, "score": score, "analyze": analyze, "quota-check": quota_check}[sys.argv[1]]()
