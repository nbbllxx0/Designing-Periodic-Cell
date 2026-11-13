import { create } from "zustand";
import { get, post, subscribe } from "./api";
import { defaultDesign } from "./physics";
import type { Design, Details, Families, Job, Material, Preview, RecordedSession, Summary, ToolSpec } from "./types";

interface ToolOut { ok: boolean; seq?: number; result?: any; error?: string; job?: Job }

interface Store {
  connected: boolean;
  mode: string;
  summary: Summary | null;
  tools: ToolSpec[];
  materials: Record<string, Material>;
  families: Families | null;
  recorded: RecordedSession[];
  design: Design | null;
  designEdited: boolean;
  details: Details | null;
  detailsBusy: boolean;
  preview: Preview | null;
  jobs: Record<string, Job>;
  tiled: boolean;
  message: { text: string; error: boolean } | null;
  lastExport: { name: string; url: string; files: string[] } | null;
  init: () => Promise<void>;
  refresh: () => Promise<void>;
  call: (name: string, args?: Record<string, unknown>) => Promise<ToolOut | null>;
  loadRecorded: (id: string) => Promise<void>;
  newSession: () => Promise<void>;
  setDesign: (d: Design, edited?: boolean) => void;
  setTiled: (t: boolean) => void;
  exportBundle: () => Promise<void>;
  cancelJob: (id: string) => Promise<void>;
  say: (text: string, error?: boolean) => void;
}

let previewTimer: number | undefined;
let detailsTimer: number | undefined;

export const useStore = create<Store>((set, getS) => ({
  connected: false,
  mode: "?",
  summary: null,
  tools: [],
  materials: {},
  families: null,
  recorded: [],
  design: null,
  designEdited: false,
  details: null,
  detailsBusy: false,
  preview: null,
  jobs: {},
  tiled: false,
  message: null,
  lastExport: null,

  init: async () => {
    const [t, m, f, r] = await Promise.all([
      get<{ mode: string; tools: ToolSpec[] }>("/api/tools"),
      get<{ materials: Record<string, Material> }>("/api/materials"),
      get<Families>("/api/families"),
      get<{ sessions: RecordedSession[] }>("/api/recorded"),
    ]);
    set({ tools: t.tools, mode: t.mode, materials: m.materials, families: f, recorded: r.sessions });
    const params = new URLSearchParams(window.location.search);
    // ?static=1: no event stream (headless screenshots; a page with an open stream never finishes loading)
    if (params.get("static") !== "1") subscribe((ev) => {
      if (ev.type === "job") {
        set({ jobs: mergeJob(getS().jobs, ev.job) });
        if (ev.job.status === "failed" && ev.job.output?.error) getS().say(`${ev.job.tool}: ${ev.job.output.error}`, true);
        if (ev.job.status === "cancelled") getS().say(ev.job.output?.error ?? `${ev.job.tool} cancelled`);
        if (["done", "failed", "cancelled"].includes(ev.job.status)) scheduleDetails();
      } else if (ev.type === "progress") {
        const old = getS().jobs[ev.job_id];
        if (old && old.status === "running") set({ jobs: { ...getS().jobs, [ev.job_id]: { ...old, progress: ev.progress } } });
      } else if (ev.type === "session" || ev.type === "record") {
        void getS().refresh();
      }
    }, (open) => set({ connected: open }));
    const load = params.get("load");
    if (load) await getS().loadRecorded(load);
    else await getS().refresh();
    if (params.get("tiled") === "1") set({ tiled: true });
  },

  refresh: async () => {
    const s = await get<Summary>("/api/session");
    const st = getS();
    set({ summary: s });
    if ((!st.designEdited || !st.design) && s.focus) st.setDesign(s.focus, false);
    else if (!st.design && st.families) st.setDesign(defaultDesign(st.families, "gyroid"), false);
    else if (st.design) scheduleDetails();
  },

  call: async (name, args = {}) => {
    try {
      const out = await post<ToolOut>(`/api/tools/${name}`, { args, actor: "user" });
      if (out.job) {
        set({ jobs: mergeJob(getS().jobs, out.job) });
      } else if (!out.ok) {
        getS().say(`${name}: ${out.error}`, true);
      }
      await getS().refresh();
      return out;
    } catch (e) {
      getS().say(String(e), true);
      return null;
    }
  },

  loadRecorded: async (id) => {
    try {
      const s = await post<Summary>("/api/recorded/load", { id });
      set({ summary: s, designEdited: false, details: null, lastExport: null });
      if (s.focus) getS().setDesign(s.focus, false);
      else if (getS().families) getS().setDesign(defaultDesign(getS().families!, "gyroid"), false);
      getS().say(`loaded recorded session ${id}`);
    } catch (e) {
      getS().say(String(e), true);
    }
  },

  newSession: async () => {
    const s = await post<Summary>("/api/session/new", { profile: "C" });
    set({ summary: s, designEdited: false, details: null, lastExport: null });
    if (getS().families) getS().setDesign(defaultDesign(getS().families!, "gyroid"), false);
  },

  setDesign: (d, edited = true) => {
    set({ design: d, designEdited: edited || getS().designEdited });
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(async () => {
      const q = new URLSearchParams({ kind: d.kind, params: JSON.stringify(d.params), n: "32" });
      try {
        set({ preview: await get<Preview>(`/api/preview?${q}`) });
      } catch (e) {
        getS().say(String(e), true);
      }
    }, 120);
    scheduleDetails();
  },

  setTiled: (t) => set({ tiled: t }),

  exportBundle: async () => {
    if (getS().mode === "live") {
      // live: the amm export tool (certified-geometry STL + report.json), queued on the worker
      const d = getS().design;
      if (d) await getS().call("export", { design: d, tiles: 3 });
      return;
    }
    try {
      const out = await post<{ name: string; url: string; files: string[] }>("/api/export",
        { design: getS().design, tiles: 3, n: 40 });
      set({ lastExport: out });
      getS().say(`export ready: ${out.name}`);
      const a = document.createElement("a");
      a.href = out.url;
      a.download = out.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      getS().say(String(e), true);
    }
  },

  cancelJob: async (id) => {
    try {
      const r = await post<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, {});
      if (!r.cancelled) getS().say("this job cannot be cancelled now (finished, or not interruptible)", true);
    } catch (e) {
      getS().say(String(e), true);
    }
  },

  say: (text, error = false) => {
    set({ message: { text, error } });
    window.setTimeout(() => {
      if (getS().message?.text === text) set({ message: null });
    }, error ? 8000 : 4000);
  },
}));

// Job updates can arrive out of order (the POST reply may come after the stream's "done" event): never step back.
const RANK: Record<string, number> = { queued: 0, running: 1, done: 2, failed: 2, cancelled: 2 };
function mergeJob(jobs: Record<string, Job>, j: Job): Record<string, Job> {
  const old = jobs[j.id];
  if (old && RANK[old.status] > RANK[j.status]) return jobs;
  return { ...jobs, [j.id]: j };
}

function scheduleDetails() {
  window.clearTimeout(detailsTimer);
  detailsTimer = window.setTimeout(async () => {
    const d = useStore.getState().design;
    if (!d) return;
    useStore.setState({ detailsBusy: true });
    try {
      useStore.setState({ details: await post<Details>("/api/details", { design: d }) });
    } catch {
      useStore.setState({ details: null });
    } finally {
      useStore.setState({ detailsBusy: false });
    }
  }, 200);
}
