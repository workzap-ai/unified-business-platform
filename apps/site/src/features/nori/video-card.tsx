import type { Film } from "./videos-data";

// A plain video player: the poster shows first, nothing downloads until play.
export function VideoCard({ film }: { film: Film }) {
  return (
    <figure className="nv-video">
      <video
        controls
        preload="none"
        playsInline
        poster={film.poster}
        aria-label={`${film.title}. Silent film with captions.`}
      >
        <source src={film.file} type="video/mp4" />
      </video>
      <figcaption>
        <strong>{film.title}</strong>
        <span>
          {film.line} About {film.seconds} seconds, no sound needed. Demo workspace,
          dummy data.
        </span>
      </figcaption>
    </figure>
  );
}
