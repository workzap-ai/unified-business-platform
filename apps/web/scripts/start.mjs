import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Next's standalone output omits static assets; assemble them for local runs.
const standalone = resolve(".next/standalone");
cpSync(resolve(".next/static"), resolve(standalone, ".next/static"), {
  recursive: true,
});
if (existsSync("public")) {
  cpSync(resolve("public"), resolve(standalone, "public"), { recursive: true });
}
process.env.HOSTNAME ??= "0.0.0.0";
await import(pathToFileURL(resolve(standalone, "server.js")).href);
