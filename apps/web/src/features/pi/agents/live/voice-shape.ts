"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * What the agent's voice sounds like right now, read from its audio, so the mouth can make the
 * right shape and not only open and close:
 *  - `level` is how loud (0 to 1), so how wide the jaw opens;
 *  - `tone` is how bright (0 to 1): a low, dark sound is the round "oo/oh", a bright one is the wide "ee".
 * It only listens to the stream it is given (the agent's own voice, already playing in the room). It
 * sends nothing anywhere and keeps nothing.
 */
export type VoiceShape = { level: number; tone: number; active: boolean };

export function useVoiceShape(
  stream: MediaStream | null | undefined,
): RefObject<VoiceShape> {
  const shape = useRef<VoiceShape>({ level: 0, tone: 0.5, active: false });
  useEffect(() => {
    const s = shape.current;
    if (!stream || stream.getAudioTracks().length === 0) {
      s.active = false;
      return;
    }
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.4;
    source.connect(analyser); // not connected onwards: it is heard once, by the room, never twice
    void ctx.resume().catch(() => undefined);
    const time = new Float32Array(analyser.fftSize);
    const freq = new Uint8Array(analyser.frequencyBinCount);
    const hz = ctx.sampleRate / analyser.fftSize;
    const lo = Math.max(1, Math.floor(150 / hz));
    const hi = Math.min(freq.length - 1, Math.floor(4000 / hz));
    s.active = true;
    const id = window.setInterval(() => {
      analyser.getFloatTimeDomainData(time);
      let sum = 0;
      for (const v of time) sum += v * v;
      const rms = Math.sqrt(sum / time.length);
      s.level = Math.min(1, rms * 9);
      analyser.getByteFrequencyData(freq);
      let weight = 0;
      let moment = 0;
      for (let i = lo; i <= hi; i++) {
        weight += freq[i];
        moment += freq[i] * i * hz;
      }
      if (weight > 0 && s.level > 0.05) {
        const centroid = moment / weight; // measured on speech: about 1200 Hz or less is "oo/oh", 1900 Hz or more is "ee" and hissing sounds
        const tone = Math.min(1, Math.max(0, 0.5 + (centroid - 1550) / 1200));
        s.tone += (tone - s.tone) * 0.5;
      }
    }, 25);
    return () => {
      window.clearInterval(id);
      s.active = false;
      s.level = 0;
      source.disconnect();
      void ctx.close().catch(() => undefined);
    };
  }, [stream]);
  return shape;
}
