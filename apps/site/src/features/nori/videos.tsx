import { Closing, PageHead, Shell } from "./chrome";
import { VideoCard } from "./video-card";
import { FILMS } from "./videos-data";

export function NoriVideos() {
  return (
    <Shell current="/nori/videos">
      <PageHead
        label="Videos"
        title="nori in short films."
        lead="Recorded from the real screens of a demo workspace. No sound needed."
      />
      <section className="nx-section">
        <div className="nx-wrap">
          <ul className="nv-films">
            {FILMS.map((f) => (
              <li key={f.slug}>
                <VideoCard film={f} />
                {f.transcript.length ? (
                  <details className="nv-transcript">
                    <summary>Read the captions</summary>
                    <ol>
                      {f.transcript.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ol>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </section>
      <Closing />
    </Shell>
  );
}
