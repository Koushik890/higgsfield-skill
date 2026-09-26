// Detect which coding agents are installed, reusing the agent table from the
// "skills" installer (vercel-labs/skills, MIT) so ids and paths always match it.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);

function loadAgentTable() {
  const pkgDir = dirname(require.resolve("skills/package.json"));
  const source = readFileSync(join(pkgDir, "dist", "cli.mjs"), "utf8");
  const start = source.indexOf("const home = homedir();");
  const tableStart = source.indexOf("const agents = {", start);
  const tableEnd = source.indexOf("\n};", tableStart);
  if (start < 0 || tableStart < 0 || tableEnd < 0) throw new Error("agent table not found");
  const xdg = pathToFileURL(join(pkgDir, "dist", "_chunks", "libs", "xdg-basedir.mjs")).href;
  const module = [
    'import { existsSync, readFileSync, readdirSync } from "node:fs";',
    'import { join } from "node:path";',
    'import { homedir } from "node:os";',
    `import { xdgConfig } from ${JSON.stringify(xdg)};`,
    source.slice(start, tableEnd + 3),
    "export { agents };",
  ].join("\n");
  return import("data:text/javascript;base64," + Buffer.from(module).toString("base64")).then((m) => m.agents);
}

/** Returns [{ id, name }] for agents found on this computer, or null if detection is unavailable. */
export async function detectAgents() {
  let agents;
  try {
    agents = await loadAgentTable();
  } catch {
    return null;
  }
  const found = [];
  for (const [id, config] of Object.entries(agents)) {
    if (id === "eve" || !config.globalSkillsDir) continue;
    try {
      if (await config.detectInstalled()) found.push({ id, name: config.displayName });
    } catch {
      // one broken check shouldn't stop the rest
    }
  }
  return found.sort((a, b) => a.name.localeCompare(b.name));
}
