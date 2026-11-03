// Small inline icons for the nori pages. One family: 24px grid, 1.75px stroke, round ends,
// drawn in the current text colour. Decorative by default (aria-hidden).

const c = (x: number, y: number, r: number) =>
  `M${x - r} ${y}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;

const PATHS = {
  arrow: "M5 12h14M13 6l6 6-6 6",
  check: "m5 12.5 4.5 4.5L19 7.5",
  checkCircle: `${c(12, 12, 9)}M8 12.5l2.8 2.8 5.2-5.3`,
  chevron: "m6 9 6 6 6-6",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6 6 18",
  clock: `${c(12, 12, 9)}M12 7v5l3 2`,
  calendar: "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM3 10h18M8 3v4M16 3v4",
  info: `${c(12, 12, 9)}M12 11v5M12 8h.01`,
  play: "M8 5v14l11-7L8 5Z",
  chat: "M4 5h16v11H9l-5 4V5Z",
  shirt: "M8 3 3.5 6l2 4L8 8.8V21h8V8.8l2.5 1.2 2-4L16 3c-.6 1.4-2 2.2-4 2.2S8.6 4.4 8 3Z",
  shoe: "M3 17V8.5c0-.8.9-1.2 1.5-.7L8 10.5l3.5-1.5 1 2.5c1.2 1 3.2 1.6 5.3 2.1 1.9.4 3.2 1.5 3.2 3V17H3ZM3 14.5h18M9.5 11l1 1.5M12 10l1 1.5",
  bag: "M5 8h14l1 12H4L5 8ZM9 8V6.5a3 3 0 0 1 6 0V8",
  kids: `${c(12, 12, 9)}M9 10h.01M15 10h.01M8.5 14.5c.9 1.4 2 2 3.5 2s2.6-.6 3.5-2`,
  bed: "M3 19V6M3 14h18v5M21 14v-2.5A2.5 2.5 0 0 0 18.5 9H11v5M7 11.5h.01",
  store: "M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5c0 1.4 1.1 2.5 2.5 2.5S9 10.9 9 9.5c0 1.4 1.1 2.5 3 2.5s3-1.1 3-2.5c0 1.4 1.1 2.5 2.5 2.5S20 10.9 20 9.5M10 20v-4.5h4V20",
  coins: `${c(12, 12, 9)}M14.6 9.3c-.5-.8-1.4-1.3-2.6-1.3-1.4 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.2 0-2.1-.5-2.6-1.3M12 6.5V8M12 16v1.5`,
  box: "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9ZM3 7.5l9 4.5 9-4.5M12 12v9",
  people: `${c(9, 8, 3.5)}M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M17 5.7a3 3 0 0 1 0 5.6M17 14.2c2.6.2 4.5 2 4.5 4.8`,
  user: `${c(12, 8, 4)}M4 20c0-4 3.6-6 8-6s8 2 8 6`,
  megaphone: "M3 11v3l12 5V6L3 11ZM7 15.5V19a2 2 0 0 0 4 .6M18.5 9a4.5 4.5 0 0 1 0 7",
  eye: `M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z${c(12, 12, 3)}`,
  plus: `${c(12, 12, 9)}M12 8v8M8 12h8`,
  phone: "M9 2.5h6a2 2 0 0 1 2 2v15a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-15a2 2 0 0 1 2-2ZM11 18.5h2",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5ZM14 3v5h5M9 13h6M9 17h4",
  page: "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM3 9h18M7.5 14h3M7.5 17h8",
  globe: `${c(12, 12, 9)}M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18`,
  translate: "M4 5h9M8.5 3v2M6 5c.5 3 2.5 5.5 5.5 7M12 5c-.5 3-3 6-7.5 8M13 20l4-9 4 9M14.5 17h5",
  plug: "M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0V8ZM12 17v4",
  palette: `M12 3a9 9 0 1 0 0 18c1.2 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8ZM7.5 11h.01M10 7.5h.01M14.5 7.5h.01`,
  image: "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM8.5 9.5h.01M21 16l-5-5-9 9",
  type: "M4 7V5h16v2M12 5v14M9 19h6",
  server: "M5 4h14a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM5 14h14a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2ZM7 7h.01M7 17h.01",
  database: "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3ZM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  clipboard: "M9 4h6v3H9V4ZM15 5.5h2a2 2 0 0 1 2 2V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7.5a2 2 0 0 1 2-2h2M9 14l2 2 4-4",
  till: "M7 3h10a1 1 0 0 1 1 1v6H6V4a1 1 0 0 1 1-1ZM4 21v-6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v6H4ZM8 17h.01M12 17h.01M16 17h.01",
  book: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4ZM5 17a3 3 0 0 1 3-3h11",
  grid: "M4.5 3h4a1.5 1.5 0 0 1 1.5 1.5v4A1.5 1.5 0 0 1 8.5 10h-4A1.5 1.5 0 0 1 3 8.5v-4A1.5 1.5 0 0 1 4.5 3ZM15.5 3h4A1.5 1.5 0 0 1 21 4.5v4a1.5 1.5 0 0 1-1.5 1.5h-4A1.5 1.5 0 0 1 14 8.5v-4A1.5 1.5 0 0 1 15.5 3ZM4.5 14h4A1.5 1.5 0 0 1 10 15.5v4A1.5 1.5 0 0 1 8.5 21h-4A1.5 1.5 0 0 1 3 19.5v-4A1.5 1.5 0 0 1 4.5 14ZM15.5 14h4a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5v-4a1.5 1.5 0 0 1 1.5-1.5Z",
  warehouse: "M3 10 12 4l9 6v10H3V10ZM8 20v-6h8v6",
  tie: "M7 8 3 12l4 4M3 12h18M17 8l4 4-4 4",
  swap: "M4 8h13l-3-3M20 16H7l3 3",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 24,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

// An icon in a soft mint tile: the standard marker for a card or a row.
export function Badge({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <span className="nv-badge">
      <Icon name={name} size={size} />
    </span>
  );
}
