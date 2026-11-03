import type { Film } from "./videos-data";

// A plain video player: the poster shows first, nothing downloads until play.
export function VideoCard({ film }: { film: Film }) {
  return (
    <figure className="nv-video">
      <video
        controls
        preload="metadata"
        playsInline
        poster={film.poster}
        aria-label={`${film.title}. Film with captions.`}
      >
        <source src={film.file} type="video/mp4" />
      </video>
    </figure>
  );
}
