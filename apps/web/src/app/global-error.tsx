"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", display: "grid", placeItems: "center", minHeight: "100vh", margin: 0 }}>
        <div style={{ textAlign: "center", maxWidth: 360, padding: 24 }}>
          <h1 style={{ fontSize: 18 }}>Something went wrong</h1>
          <p style={{ color: "#66736d", fontSize: 14 }}>The application could not load. Please try again.</p>
          <button onClick={reset} style={{ marginTop: 12, padding: "8px 14px", borderRadius: 6, border: "1px solid #cbd2cc", background: "#fff" }}>
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
