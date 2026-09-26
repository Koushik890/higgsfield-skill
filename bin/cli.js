#!/usr/bin/env node
// npx higgsfield-api-skill — install the Higgsfield API skill into every coding agent on this machine.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, chmodSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline";
import { detectAgents } from "./agents.js";

const REPO = "Koushik890/higgsfield-api-skill";
const SKILL = "higgsfield";
const require = createRequire(import.meta.url);
const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));

const green = (s) => (process.stdout.isTTY ? `\x1b[32m${s}\x1b[0m` : s);
const bold = (s) => (process.stdout.isTTY ? `\x1b[1m${s}\x1b[0m` : s);
const dim = (s) => (process.stdout.isTTY ? `\x1b[2m${s}\x1b[0m` : s);

const HELP = `${bold("higgsfield-api-skill")} ${pkg.version}
Install the Higgsfield API skill (79 video/image models) into your coding agents.

${bold("Usage")}
  npx higgsfield-api-skill              find agents on this computer, ask where, install
  npx higgsfield-api-skill --all        install for every supported agent, no questions
  npx higgsfield-api-skill -a codex -a claude-code   only these agents
  npx higgsfield-api-skill --project    install into the current project only
  npx higgsfield-api-skill update       update to the latest version
  npx higgsfield-api-skill remove       uninstall from all agents
  npx higgsfield-api-skill key          create/show the API key file

Other options are passed to the "skills" installer (e.g. --copy, -y).
`;

function skillsBin() {
  const pkgJson = require.resolve("skills/package.json");
  const meta = JSON.parse(readFileSync(pkgJson, "utf8"));
  const rel = typeof meta.bin === "string" ? meta.bin : meta.bin.skills;
  return join(dirname(pkgJson), rel);
}

function runSkills(args) {
  const result = spawnSync(process.execPath, [skillsBin(), ...args], { stdio: "inherit" });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

function keyFile() {
  return process.env.HIGGSFIELD_ENV_FILE || join(homedir(), ".config", "higgsfield", ".env");
}

function ensureKeyFile() {
  const file = keyFile();
  if (existsSync(file)) return { file, created: false };
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, "# Higgsfield API key from https://console.higgsfield.ai\nHF_API_KEY_ID=\nHF_API_KEY_SECRET=\n", { mode: 0o600 });
  try { chmodSync(file, 0o600); } catch { /* Windows */ }
  return { file, created: true };
}

function keyFilled(file) {
  try {
    const text = readFileSync(file, "utf8");
    return /^HF_API_KEY_ID=\S+/m.test(text) && /^HF_API_KEY_SECRET=\S+/m.test(text);
  } catch {
    return false;
  }
}

function nextSteps(project) {
  const { file, created } = ensureKeyFile();
  const skillDir = project ? join(".agents", "skills", SKILL) : join(homedir(), ".agents", "skills", SKILL);
  console.log("");
  console.log(green("✓ Higgsfield API skill installed."));
  if (created) console.log(`  Created key file: ${file}`);
  if (keyFilled(file) || (process.env.HF_API_KEY_ID && process.env.HF_API_KEY_SECRET)) {
    console.log("  API key: found.");
  } else {
    console.log(`\n${bold("Next:")} add your API key (from https://console.higgsfield.ai) to`);
    console.log(`  ${file}`);
    console.log(dim("  HF_API_KEY_ID=...\n  HF_API_KEY_SECRET=..."));
  }
  console.log(`\nCheck it (free):  python "${join(skillDir, "scripts", "hf.py")}" check`);
  console.log(`Then ask your agent: ${bold('"Make a 5-second video of waves at sunset with Higgsfield."')}`);
  console.log(dim("Restart open agent sessions so they pick up the new skill."));
}

async function main(argv) {
  if (argv.includes("-h") || argv.includes("--help")) {
    console.log(HELP);
    return 0;
  }
  if (argv.includes("-v") || argv.includes("--version")) {
    console.log(pkg.version);
    return 0;
  }
  const [command, ...rest] = argv;
  if (command === "key") {
    const { file, created } = ensureKeyFile();
    console.log(`${created ? "Created" : "Key file"}: ${file}`);
    console.log(keyFilled(file) ? "API key: filled in." : "Add HF_API_KEY_ID and HF_API_KEY_SECRET to it.");
    return 0;
  }
  if (command === "update") return runSkills(["update", SKILL, ...(rest.length ? rest : ["-g", "-y"])]);
  if (command === "remove" || command === "uninstall") return runSkills(["remove", SKILL, ...(rest.length ? rest : ["-g", "-y"])]);
  if (command && !command.startsWith("-")) {
    console.error(`Unknown command "${command}".\n`);
    console.log(HELP);
    return 1;
  }

  const project = argv.includes("--project");
  const passthrough = argv.filter((a) => a !== "--project");
  const scope = project ? [] : ["-g"];
  console.log(`${bold("Higgsfield API skill")} ${dim(`v${pkg.version}`)}\n`);

  let targets = [];
  const chosenByFlag = passthrough.some((a) => a === "--all" || a === "-a" || a === "--agent" || a.startsWith("--agent="));
  if (!chosenByFlag) {
    const choice = await chooseAgents();
    closeReader(); // hand the keyboard back before the installer runs
    if (choice === "cancel") {
      console.log("Cancelled. Nothing installed.");
      return 0;
    }
    if (choice === "picker") {
      // Let the skills installer show its full searchable list of every supported agent.
      const code = runSkills(["add", REPO, "--skill", SKILL, ...scope, ...passthrough]);
      if (code === 0) nextSteps(project);
      return code;
    }
    targets = choice.flatMap((id) => ["-a", id]);
  }
  const extra = chosenByFlag || passthrough.includes("-y") ? [] : ["-y"];
  const code = runSkills(["add", REPO, "--skill", SKILL, ...scope, ...targets, ...extra, ...passthrough]);
  if (code === 0) nextSteps(project);
  return code;
}

let reader;
const pendingLines = [];
const waiting = [];

function ask(question) {
  if (!reader) {
    // One reader for the whole session so typed-ahead or piped answers aren't lost.
    reader = createInterface({ input: process.stdin, output: process.stdout });
    reader.on("line", (line) => (waiting.length ? waiting.shift()(line.trim()) : pendingLines.push(line.trim())));
    reader.on("close", () => waiting.splice(0).forEach((resolveAnswer) => resolveAnswer("q")));
  }
  process.stdout.write(question);
  if (pendingLines.length) return Promise.resolve(pendingLines.shift());
  return new Promise((resolveAnswer) => waiting.push(resolveAnswer));
}

function closeReader() {
  if (reader) reader.close();
}

/** Returns a list of agent ids, "picker" for the full list, or "cancel". */
async function chooseAgents() {
  const found = await detectAgents();
  if (found === null) {
    console.log("Couldn't detect agents automatically; showing the full list.\n");
    return "picker";
  }
  if (found.length === 0) {
    console.log("No coding agents found on this computer; showing the full list.\n");
    return "picker";
  }
  console.log(`Found ${found.length} coding agent${found.length === 1 ? "" : "s"} on this computer:`);
  found.forEach((a, i) => console.log(`  ${String(i + 1).padStart(2)}. ${a.name} ${dim(`(${a.id})`)}`));
  console.log("");

  // Without a terminal to ask in (e.g. run by an agent), install for the detected agents only.
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.log("No terminal to ask in; installing for all detected agents.\n");
    return found.map((a) => a.id);
  }
  console.log("Where should the skill be installed?");
  console.log(`  ${bold("a")}  All ${found.length} detected agents ${dim("(recommended)")}`);
  console.log(`  ${bold("s")}  Some of them (pick by number)`);
  console.log(`  ${bold("o")}  Other agents not listed (full list of 80+)`);
  console.log(`  ${bold("q")}  Cancel`);
  for (;;) {
    const answer = (await ask("\nChoose [a/s/o/q] (a): ")).toLowerCase() || "a";
    if (answer === "a" || answer === "all") return found.map((a) => a.id);
    if (answer === "q" || answer === "cancel") return "cancel";
    if (answer === "o") return "picker";
    if (answer === "s") {
      for (;;) {
        const picks = await ask(`Numbers separated by commas or spaces, e.g. 1,3,5 (Enter to go back): `);
        if (!picks) break;
        if (picks.toLowerCase() === "q") return "cancel";
        const nums = [...new Set(picks.split(/[\s,]+/).filter(Boolean).map(Number))];
        if (nums.length && nums.every((n) => Number.isInteger(n) && n >= 1 && n <= found.length)) {
          const chosen = nums.map((n) => found[n - 1]);
          console.log(`Installing for: ${chosen.map((a) => a.name).join(", ")}\n`);
          return chosen.map((a) => a.id);
        }
        console.log(`Please enter numbers between 1 and ${found.length}.`);
      }
      continue;
    }
    console.log("Please type a, s, o or q.");
  }
}

main(process.argv.slice(2)).then((code) => process.exit(code));
