"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { liveApi } from "@/lib/api";
import { initialDiarization, reduceDiarization, diarizationDigest, type DiarizationState } from "./live-diarization";
import type { UploadLocation, TranscriptSegment } from "@/types/api";

export type CaptureState = "idle" | "starting" | "listening" | "finishing" | "completed" | "interrupted" | "cancelled";

type Resources = {
  socket?: WebSocket; stream?: MediaStream; context?: AudioContext; node?: AudioWorkletNode;
  seq: number; samples: number; eventSeq: number; jobId?: string; state: CaptureState;
  stopCapture?: () => Promise<void>; partialRevision: number;
  timer?: number; diarization?: DiarizationState; protocol?: 1 | 2;
};

export function useLiveCapture() {
  const [state, setState] = useState<CaptureState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [diarization, setDiarization] = useState<DiarizationState | null>(null);
  const [partial, setPartial] = useState("");
  const resources = useRef<Resources>({ seq: 0, samples: 0, eventSeq: 0, state: "idle", partialRevision: 0 });

  const update = useCallback((value: CaptureState) => {
    resources.current.state = value;
    setState(value);
  }, []);

  const releaseCapture = useCallback(async (r: Resources) => {
    window.clearTimeout(r.timer);
    r.node?.disconnect();
    r.stream?.getTracks().forEach((track) => { track.onended = null; track.stop(); });
    await r.context?.close().catch(() => {});
    r.node = undefined; r.stream = undefined; r.context = undefined;
  }, []);

  const cancel = useCallback(async () => {
    const r = resources.current;
    update("cancelled");
    if (r.socket?.readyState === WebSocket.OPEN) r.socket.send(JSON.stringify({ type: "cancel" }));
    await releaseCapture(r);
    r.socket?.close();
    if (r.jobId) await liveApi.cancel(r.jobId).catch(() => {});
    if (resources.current === r) setPartial("");
  }, [releaseCapture, update]);

  const finish = useCallback(async () => {
    const r = resources.current;
    if (r.state !== "listening") return;
    r.state = "finishing";
    update("finishing");
    // Flush the sub-200ms tail before finish; the worklet port preserves order.
    try {
      await r.stopCapture?.();
      await releaseCapture(r);
      if (resources.current !== r || r.state !== "finishing") return;
      if (r.socket?.readyState !== WebSocket.OPEN) throw new Error("Conexão interrompida durante a finalização.");
      r.socket.send(JSON.stringify({ type: "finish", last_seq: r.seq - 1 }));
    } catch (err) {
      if (resources.current !== r || r.state !== "finishing") return;
      update("interrupted");
      setError(err instanceof Error ? err.message : "Não foi possível finalizar a captura.");
      await releaseCapture(r); r.socket?.close();
      if (r.jobId) await liveApi.cancel(r.jobId).catch(() => {});
    }
  }, [releaseCapture, update]);

  const start = useCallback(async (location: UploadLocation, name: string, diarize = false) => {
    setDiarization(null); setError(null); setSegments([]); setPartial(""); setDuration(0); setJobId(null);
    const r: Resources = { seq: 0, samples: 0, eventSeq: 0, state: "starting", partialRevision: 0 };
    r.protocol = diarize ? 2 : 1;
    resources.current = r;
    update("starting");
    const interrupt = (message: string) => {
      if (resources.current !== r || ["completed", "cancelled", "interrupted"].includes(r.state)) return;
      setError(message); update("interrupted");
      void releaseCapture(r); r.socket?.close();
      if (r.jobId) void liveApi.cancel(r.jobId).catch(() => {});
    };
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) throw new Error("O microfone exige HTTPS ou localhost.");
      // Request permission first; never consume a GPU reservation while a user
      // is deciding whether to permit microphone access.
      r.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true }, video: false });
      if (resources.current !== r || r.state !== "starting") {
        r.stream.getTracks().forEach((track) => track.stop()); return;
      }
      r.context = new AudioContext();
      await r.context.audioWorklet.addModule("/audio/live-pcm-worklet.js");
      if (resources.current !== r || r.state !== "starting") { await releaseCapture(r); return; }
      const session = await liveApi.create({ ...location, name, language: "pt", protocol: r.protocol, diarize });
      r.jobId = session.job_id;
      if (resources.current !== r || r.state !== "starting") {
        await liveApi.cancel(session.job_id).catch(() => {}); await releaseCapture(r); return;
      }
      setJobId(session.job_id);
      const socket = new WebSocket(session.ws_url); r.socket = socket;
      const timer = window.setTimeout(() => interrupt("O serviço não ficou pronto a tempo."), 10000);
      r.timer = timer;
      socket.onopen = () => {
        if (resources.current === r && r.state === "starting") socket.send(JSON.stringify({ type: "authenticate", protocol: r.protocol, ticket: session.ticket }));
        else socket.close();
      };
      let eventQueue: Promise<void> = Promise.resolve();
      socket.onerror = () => interrupt("Não foi possível conectar ao serviço de transcrição.");
      socket.onclose = () => {
        window.clearTimeout(timer);
        void eventQueue.then(() => {
          if (!["completed", "cancelled", "interrupted"].includes(r.state)) interrupt("A captura foi interrompida. Inicie uma nova sessão.");
        });
      };
      socket.onmessage = ({ data }) => {
        eventQueue = eventQueue.then(async () => {
        if (resources.current !== r || ["completed", "cancelled", "interrupted"].includes(r.state)) return;
        try {
          const event = JSON.parse(data);
          if (event.event_seq !== r.eventSeq + 1) throw new Error("Sequência de eventos inválida.");
          r.eventSeq = event.event_seq;
          if (event.type === "session.ready") {
            if ((event.protocol ?? 1) !== r.protocol) throw new Error("Versão de sessão incompatível.");
            if (r.protocol === 2) { r.diarization = initialDiarization(event.generation); setDiarization(r.diarization); }
            window.clearTimeout(timer);
            const source = r.context!.createMediaStreamSource(r.stream!);
            const node = new AudioWorkletNode(r.context!, "live-pcm"); r.node = node;
            const mute = r.context!.createGain(); mute.gain.value = 0;
            source.connect(node); node.connect(mute); mute.connect(r.context!.destination);
            let flushed: (() => void) | undefined;
            node.port.onmessage = ({ data: pcm }) => {
              if (pcm === "flushed") { flushed?.(); return; }
              if (!["listening", "finishing"].includes(r.state)) return;
              if (socket.readyState !== WebSocket.OPEN || socket.bufferedAmount + pcm.byteLength > 64000) {
                interrupt("A conexão ficou lenta demais para áudio ao vivo."); return;
              }
              const frame = new ArrayBuffer(12 + pcm.byteLength);
              const view = new DataView(frame);
              view.setUint32(0, r.seq++, true); view.setBigUint64(4, BigInt(r.samples), true);
              new Uint8Array(frame, 12).set(new Uint8Array(pcm));
              r.samples += pcm.byteLength / 2;
              socket.send(frame); setDuration(r.samples / 16000);
              if (r.samples >= session.max_duration_seconds * 16000) void finish();
            };
            r.stopCapture = () => new Promise<void>((resolve, reject) => {
              const timeout = setTimeout(() => reject(new Error("A captura não conseguiu finalizar o áudio.")), 2000);
              flushed = () => { clearTimeout(timeout); resolve(); };
              node.port.postMessage("finish");
            });
            r.stream!.getAudioTracks().forEach((track) => { track.onended = () => interrupt("O microfone foi desconectado."); });
            await r.context!.resume();
            if (resources.current !== r || r.state !== "starting") { await releaseCapture(r); return; }
            update("listening");
          } else if (event.type === "transcript.partial") {
            if (event.revision > r.partialRevision) { r.partialRevision = event.revision; setPartial(event.text); }
          } else if (event.type === "transcript.final") {
            setSegments((previous) => {
              if (event.segment_id !== previous.length) { interrupt("Segmento de legenda fora de ordem."); return previous; }
              return [...previous, { start: event.start, end: event.end, text: event.text }];
            }); setPartial("");
          } else if (event.type === "diarization.update") {
            if (!r.diarization) throw new Error("Falantes não foram negociados nesta sessão.");
            r.diarization = reduceDiarization(r.diarization, event, r.samples);
            setDiarization(r.diarization);
          } else if (event.type === "session.completed") {
            if (r.diarization && (r.diarization.stable_until_samples !== r.samples ||
                await diarizationDigest(r.diarization) !== event.diarization_digest)) throw new Error("O resultado salvo não coincide com os falantes da captura.");
            if (resources.current !== r || ["cancelled", "interrupted"].includes(r.state)) return;
            update("completed"); setPartial(""); await releaseCapture(r); socket.close();
          } else if (event.type === "session.error") {
            interrupt(`A sessão terminou: ${event.code}`);
          } else if (event.type === "session.limit" && event.remaining_seconds <= 1) {
            void finish();
          }
        } catch (err) { interrupt(err instanceof Error ? err.message : "Resposta inválida do servidor."); }
        });
      };
    } catch (err) {
      interrupt(err instanceof Error ? err.message : "Não foi possível iniciar a captura.");
    }
  }, [finish, releaseCapture, update]);

  useEffect(() => () => {
    const r = resources.current;
    r.state = "cancelled";
    r.socket?.close();
    void releaseCapture(r);
    if (r.jobId) void liveApi.cancel(r.jobId).catch(() => {});
  }, [releaseCapture]);

  return { state, error, jobId, duration, segments, partial, diarization, start, finish, cancel };
}
