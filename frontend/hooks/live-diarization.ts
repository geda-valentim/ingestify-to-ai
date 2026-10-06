/** Protocol 2 reference reducer. Offsets remain PCM samples until presentation. */
export type Speaker = { id: string; label: string };
export type SpeakerTurn = { start_samples: number; end_samples: number; speaker_id: string };
export type DiarizationUpdate = {
  generation: number; revision: number; horizon_samples: number; stable_until_samples: number;
  replace_from_samples: number; replace_to_samples: number; speakers: Speaker[]; turns: SpeakerTurn[];
};
export type DiarizationState = {
  generation: number; revision: number; horizon_samples: number; stable_until_samples: number;
  speakers: Speaker[]; frozen: SpeakerTurn[]; mutable: SpeakerTurn[]; replays: Map<number, string>;
};
const validInt = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const fail = (): never => { throw new Error("Atualização de falantes inválida."); };
export function initialDiarization(generation: number): DiarizationState {
  if (!validInt(generation)) fail();
  return { generation, revision: 0, horizon_samples: 0, stable_until_samples: 0,
    speakers: [], frozen: [], mutable: [], replays: new Map() };
}
export function canonicalTurns(turns: SpeakerTurn[]): SpeakerTurn[] {
  const merged: SpeakerTurn[] = [];
  for (const source of [...turns].sort((a, b) => a.speaker_id.localeCompare(b.speaker_id) || a.start_samples - b.start_samples || a.end_samples - b.end_samples)) {
    const turn = { start_samples: source.start_samples, end_samples: source.end_samples, speaker_id: source.speaker_id };
    const last = merged[merged.length - 1];
    if (last && last.speaker_id === turn.speaker_id && turn.start_samples <= last.end_samples) last.end_samples = Math.max(last.end_samples, turn.end_samples);
    else merged.push(turn);
  }
  return merged.sort((a, b) => a.start_samples - b.start_samples || a.end_samples - b.end_samples || a.speaker_id.localeCompare(b.speaker_id));
}
export function reduceDiarization(state: DiarizationState, event: DiarizationUpdate, received: number): DiarizationState {
  const { generation, revision, horizon_samples: h, replace_from_samples: lo, replace_to_samples: hi, stable_until_samples: stable, speakers, turns } = event;
  if (![generation, revision, h, lo, hi, stable].every(validInt) || generation !== state.generation) fail();
  const fingerprint = JSON.stringify({ generation, revision, horizon_samples: h, replace_from_samples: lo, replace_to_samples: hi, stable_until_samples: stable, speakers, turns });
  if (new TextEncoder().encode(JSON.stringify(event)).length > 65536) fail();
  if (revision <= state.revision) {
    if (state.replays.get(revision) !== fingerprint) fail();
    return state;
  }
  const floor = Math.max(state.stable_until_samples, h - 80000, 0);
  if (revision !== state.revision + 1 || h < state.horizon_samples || h > received || !(floor <= lo && lo <= hi && hi <= h && floor <= stable && stable <= h)) fail();
  if (!Array.isArray(speakers) || speakers.length > 20 || speakers.length < state.speakers.length) fail();
  speakers.forEach((s, i) => {
    if (Object.keys(s).sort().join() !== "id,label" || s.id !== `SPEAKER_${String(i).padStart(2, "0")}` || s.label !== `Falante ${i + 1}`) fail();
    if (i < state.speakers.length && (s.id !== state.speakers[i].id || s.label !== state.speakers[i].label)) fail();
  });
  const ids = new Set(speakers.map(s => s.id));
  if (!Array.isArray(turns) || turns.length > 64) fail();
  turns.forEach(t => {
    if (Object.keys(t).sort().join() !== "end_samples,speaker_id,start_samples" || !validInt(t.start_samples) || !validInt(t.end_samples)
      || !(lo <= t.start_samples && t.start_samples < t.end_samples && t.end_samples <= hi) || !ids.has(t.speaker_id)) fail();
  });
  const tail: SpeakerTurn[] = [];
  for (const t of state.mutable) {
    if (t.start_samples < lo) tail.push({ ...t, end_samples: Math.min(t.end_samples, lo) });
    if (t.end_samples > hi) tail.push({ ...t, start_samples: Math.max(t.start_samples, hi) });
  }
  const frozen = [...state.frozen], mutable: SpeakerTurn[] = [];
  for (const t of canonicalTurns([...tail, ...turns])) {
    if (t.start_samples < stable) frozen.push({ ...t, end_samples: Math.min(t.end_samples, stable) });
    if (t.end_samples > stable) mutable.push({ ...t, start_samples: Math.max(t.start_samples, stable) });
  }
  if (frozen.length + mutable.length > 200000) fail();
  const replays = new Map(state.replays); replays.set(revision, fingerprint);
  return { generation, revision, horizon_samples: h, stable_until_samples: stable, speakers, frozen, mutable, replays };
}
export function canonicalDiarization(state: DiarizationState) {
  return { generation: state.generation, revision: state.revision, horizon_samples: state.horizon_samples,
    stable_until_samples: state.stable_until_samples, speakers: state.speakers.map(s => ({ id: s.id, label: s.label })),
    turns: canonicalTurns([...state.frozen, ...state.mutable]) };
}
export async function diarizationDigest(state: DiarizationState): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(canonicalDiarization(state)));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
}
type TurnNode = { turn: SpeakerTurn; maxEnd: number; left: TurnNode | null; right: TurnNode | null };
const intervalIndexes = new WeakMap<DiarizationState, TurnNode | null>();
function intervalIndex(state: DiarizationState): TurnNode | null {
  if (intervalIndexes.has(state)) return intervalIndexes.get(state)!;
  const turns = [...state.frozen, ...state.mutable].sort((a, b) => a.start_samples - b.start_samples);
  function build(lo: number, hi: number): TurnNode | null {
    if (lo >= hi) return null;
    const mid = (lo + hi) >> 1, left = build(lo, mid), right = build(mid + 1, hi);
    return { turn: turns[mid], left, right, maxEnd: Math.max(turns[mid].end_samples, left?.maxEnd ?? 0, right?.maxEnd ?? 0) };
  }
  const index = build(0, turns.length); intervalIndexes.set(state, index); return index;
}
export function labelsForInterval(state: DiarizationState, start: number, end: number): { labels: string[]; provisional: boolean; unknown: boolean } {
  const lo = start * 16000, hi = end * 16000, overlaps: SpeakerTurn[] = [];
  function query(node: TurnNode | null) {
    if (!node || node.maxEnd <= lo) return;
    query(node.left);
    if (node.turn.start_samples >= hi) return;
    if (node.turn.end_samples > lo) overlaps.push(node.turn);
    query(node.right);
  }
  query(intervalIndex(state));
  const ids = new Set(overlaps.map(t => t.speaker_id));
  let covered = lo, unknown = hi <= lo;
  for (const turn of overlaps) {
    if (turn.start_samples > covered) unknown = true;
    covered = Math.max(covered, turn.end_samples);
  }
  unknown ||= covered < hi;
  return { labels: state.speakers.filter(s => ids.has(s.id)).map(s => s.label),
    provisional: hi > state.stable_until_samples, unknown };
}
