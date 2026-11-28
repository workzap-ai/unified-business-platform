"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  BackgroundFiltersProvider,
  NoiseCancellationProvider,
  useBackgroundFilters,
  useNoiseCancellation,
} from "@stream-io/video-react-sdk";
import { NoiseCancellation } from "@stream-io/audio-filters-web";
import { AudioLines, Blend } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Cleaner picture and sound for the person's own camera and microphone: a blurred background, and
 * noise cancellation (a quieter room also helps pi hear, above all in Urdu). Both run in the
 * browser on the person's own devices. Each button shows only where the browser can do it, and
 * noise cancellation only where the video service has it switched on for the call (the platform
 * owner does that in the video service's dashboard), so a call without them looks as it did.
 */

export function QualityProviders({ children }: { children: ReactNode }) {
  const noise = useMemo(() => new NoiseCancellation(), []);
  return (
    <NoiseCancellationProvider noiseCancellation={noise}>
      <BackgroundFiltersProvider onError={() => undefined}>
        {children}
      </BackgroundFiltersProvider>
    </NoiseCancellationProvider>
  );
}

export function BlurButton() {
  const filters = useBackgroundFilters();
  const [on, setOn] = useState(false);
  if (!filters.isSupported) return null;
  return (
    <Button
      variant="secondary"
      size="sm"
      aria-pressed={on}
      disabled={filters.isLoading}
      aria-label={on ? "Show my background" : "Blur my background"}
      onClick={() => {
        if (on) filters.disableBackgroundFilter();
        else filters.applyBackgroundBlurFilter("medium");
        setOn(!on);
      }}
    >
      <Blend /> {on ? "Blurred" : "Blur"}
    </Button>
  );
}

export function NoiseButton() {
  const noise = useNoiseCancellation();
  if (!noise.isSupported) return null;
  return (
    <Button
      variant="secondary"
      size="sm"
      aria-pressed={noise.isEnabled}
      disabled={!noise.isReady && noise.isEnabled}
      aria-label={
        noise.isEnabled
          ? "Turn noise cancellation off"
          : "Cancel background noise"
      }
      onClick={() => noise.setEnabled((enabled) => !enabled)}
    >
      <AudioLines /> {noise.isEnabled ? "Quiet on" : "Quiet"}
    </Button>
  );
}
