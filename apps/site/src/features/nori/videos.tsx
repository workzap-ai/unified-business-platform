import { Closing, PageHead, Shell } from "./chrome";
import { VideoCard } from "./video-card";
import { FILMS } from "./videos-data";

function Captions({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <details className="nv-transcript">
      <summary>Read the captions</summary>
      <ol>
        {lines.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ol>
    </details>
  );
}

export function NoriVideos() {
  const [first, ...rest] = FILMS;
  return (
    <Shell current="/nori/videos">
      <PageHead
        label="Videos"
        title="nori in short films."
        lead="Recorded from the real nori screens. Captions are on screen."
      />
      <section className="nx-section">
        <div className="nx-wrap">
          <div className="nv-feature">
            <VideoCard film={first} />
            <div className="nv-feature-text">
              <span className="nx-label">Start here</span>
              <h2>{first.title}</h2>
              <p className="nx-lead">{first.line}</p>
              <span className="nv-dur-pill">{first.seconds} seconds</span>
              <Captions lines={first.transcript} />
            </div>
          </div>
          <ul className="nv-films">
            {rest.map((f) => (
              <li key={f.slug} className="nv-card nv-film">
                <VideoCard film={f} />
                <div className="nv-card-body">
                  <h2>{f.title}</h2>
                  <p>{f.line}</p>
                  <span className="nv-dur-pill">{f.seconds} seconds</span>
                  <Captions lines={f.transcript} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <Closing />
    </Shell>
  );
}
