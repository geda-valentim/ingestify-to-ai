/** One reversible mapping drives both video time and HTML chapter state. */
export function timelineAt(progress: number) {
  const p = Math.max(0, Math.min(1, progress));
  const segment = Math.min(14, Math.floor(p * 15));
  const local = p === 1 ? 1 : p * 15 - segment;
  const bridge = segment % 2 === 1;
  const filmProgress = bridge
    ? local
    : Math.max(0, Math.min(1, (local - 0.08) / 0.76));
  return {
    segment,
    chapter: Math.ceil(segment / 2),
    bridge,
    future: segment >= 11 && segment <= 13,
    time: Math.min(44.96, (segment + filmProgress) * 3),
    result: !bridge && local > 0.65,
  };
}
export function chapterProgress(chapter: number) {
  return (Math.max(0, Math.min(7, chapter)) * 2 + 0.25) / 15;
}
