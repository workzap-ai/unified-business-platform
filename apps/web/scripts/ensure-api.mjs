import { spawn } from "node:child_process";
import { resolve } from "node:path";
import nextEnv from "@next/env";

// npm run dev must not silently start a live UI without its local API.
nextEnv.loadEnvConfig(process.cwd(), true);
if (process.env.NEXT_PUBLIC_DATA_MODE !== "demo") {
  const target = new URL(
    process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
  );
  const health = new URL("/api/v1/health/live", target);
  const reachable = async () => {
    try {
      const response = await fetch(health, {
        signal: AbortSignal.timeout(3000),
      });
      return response.ok && (await response.json()).status === "ok";
    } catch {
      return false;
    }
  };
  if (!(await reachable())) {
    const local =
      ["localhost", "127.0.0.1"].includes(target.hostname) &&
      target.port === "8000";
    if (local && process.platform === "win32") {
      console.log(
        "Starting the local API and applying pending database migrations…",
      );
      const code = await new Promise((done, reject) => {
        const child = spawn(
          "powershell.exe",
          [
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolve("../../scripts/start-local.ps1"),
            "-ApiOnly",
          ],
          { stdio: "inherit", windowsHide: true },
        );
        child.on("error", reject);
        child.on("exit", done);
      });
      if (code !== 0)
        throw new Error(
          "Local API startup failed. Check apps/api/.env and .cache/local/api.stderr.log.",
        );
    }
    if (!(await reachable())) {
      throw new Error(
        `The API at ${target.origin} is unavailable. Start the API and PostgreSQL before starting the live website. For a UI preview, set NEXT_PUBLIC_DATA_MODE=demo.`,
      );
    }
  }
  const ready = await fetch(new URL("/api/v1/health/ready", target), {
    signal: AbortSignal.timeout(5000),
  });
  if (!ready.ok) {
    throw new Error(
      "The API is running, but its database or required queue is unavailable. Check apps/api/.env and start its dependencies.",
    );
  }
  console.log(`API connection and dependencies verified: ${target.origin}`);
}
