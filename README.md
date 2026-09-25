# Higgsfield Skill

Let your coding agent make videos and images with the [Higgsfield API](https://docs.higgsfield.ai/docs). Ask in plain words: the agent prices the request, generates it, waits, and saves the file into your project's `outputs/` folder.

Works with **Claude Code** and **Codex** (any agent that reads `SKILL.md`).

> Independent open-source project. Not made by or affiliated with Higgsfield. You pay Higgsfield directly for what you generate.

## What it does

- **Shows the price first.** Every request is priced with your account before anything is generated.
- **One command from prompt to file.** Submit, wait, download.
- **Never loses a paid job.** The request ID is saved the moment Higgsfield accepts it, so a finished video can always be found and downloaded.
- **Won't charge you twice by accident.** Re-running the same job does nothing; an identical request under a new name needs an explicit flag.
- **Optional spending limits,** per job or for a group of jobs.
- **Keeps your key private.** Read from the environment or a private file; never sent anywhere except `api.higgsfield.ai`, never to download servers.
- **No dependencies.** Plain Python 3.8+, standard library only.

## Install

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/Koushik890/higgsfield-skill/main/install.ps1 | iex
```

**macOS / Linux**

```sh
curl -fsSL https://raw.githubusercontent.com/Koushik890/higgsfield-skill/main/install.sh | sh
```

Add `--codex` (shell) or download `install.ps1` and run it with `-Codex` to install for Codex instead. Running the installer again updates the skill.

Manual install: `git clone https://github.com/Koushik890/higgsfield-skill ~/.claude/skills/higgsfield`

## Add your API key

1. Create a key at [console.higgsfield.ai](https://console.higgsfield.ai).
2. Open `~/.config/higgsfield/.env` (the installer creates it; on Windows that is `C:\Users\<you>\.config\higgsfield\.env`) and fill in:

   ```
   HF_API_KEY_ID=your-key-id
   HF_API_KEY_SECRET=your-key-secret
   ```

3. Check it (free, generates nothing):

   ```sh
   python ~/.claude/skills/higgsfield/scripts/hf.py check
   ```

Environment variables `HF_API_KEY_ID` / `HF_API_KEY_SECRET` also work and take priority. Never paste your key into a chat.

## Use it

Just ask your agent:

```text
Make a 5-second 720p video of waves hitting a lighthouse at sunset.
```

```text
How much would a 10-second vertical Seedance video cost? Don't generate yet.
```

```text
Make three 4-second clips for my intro. Keep the total under $6.
```

The agent tells you the estimated cost, generates, and gives you the file path.

## Models and prices

| Model file | Model | Settings | Example estimate |
|---|---|---|---|
| `seedance-2.5-t2v` | Seedance 2.5, text to video | 4-30 s, 480p/720p, 6 aspect ratios, optional audio | 4 s 720p 16:9: **$1.85**<br>5 s 720p 16:9: **$2.31**<br>10 s 480p 9:16: **$0.65** |

Estimates are before any account discount and may differ slightly from the final charge; your console usage page is the source of truth. More models can be added as small JSON files, see [Adding a model](#adding-a-model).

## Command reference

Run from your project folder. Results are JSON.

| Command | What it does | Costs money |
|---|---|---|
| `check` | Confirms the API key works | No |
| `models` | Lists available model files | No |
| `validate --model M --input F` | Checks a request offline | No |
| `estimate --model M --input F` | Prices a request | No |
| `run --model M --input F --job NAME` | Submit, wait, download | **Yes** |
| `submit --model M --input F --job NAME` | Submit only | **Yes** |
| `status --job NAME` / `wait --job NAME` | Check or wait for a job | No |
| `download --job NAME` | Saves finished files to `outputs/` | No |
| `list` | All jobs with request ID, status, estimate, files | No |
| `attach --job NAME --request-id ID [--model M]` | Link a known request ID to a job, e.g. to recover one | No |
| `cancel --job NAME` | Cancels a job that hasn't started | No |

Use `--json '{...}'` instead of `--input FILE` for short requests. Limits: `--max-usd 2` for one job, or `--budget intro --budget-usd 6` shared across jobs.

Example request file:

```json
{
  "prompt": "Slow tracking shot along a sunlit coastal road, ocean on the left, morning haze",
  "duration": 5,
  "resolution": "720p",
  "aspect_ratio": "16:9",
  "generate_audio": true
}
```

## Adding a model

1. Open the model's API reference on [console.higgsfield.ai](https://console.higgsfield.ai).
2. Copy `models/seedance-2.5-t2v.json` to `models/<name>.json` (or to your project's `work/higgsfield/models/`) and fill in the `endpoint` and each parameter (`type`, `required`, `enum`, `min`, `max`, `default`).
3. Run `hf.py estimate` with a sample request. If it returns a USD amount, you are done. If not, the model needs a `pricing` rule like Seedance's.

Pull requests with new, tested model files are welcome.

## Troubleshooting

| Message | Fix |
|---|---|
| `No Higgsfield credentials` | Fill in `~/.config/higgsfield/.env`, then run `check`. |
| `HTTP 401` | Key ID or secret is wrong. Re-copy both from the console. |
| `HTTP 402` | Add credits in the console. |
| `HTTP 422` | A parameter isn't allowed for that model; run `validate`. |
| `pricing text no longer matches` | Higgsfield changed its pricing wording; update the model file's `pricing` before generating. |
| Job status `unknown` | The request may have been charged. Don't resubmit. Find its request ID, then run `attach`. |
| `run` timed out | Nothing is lost. Run `wait --job NAME`, then `download --job NAME`. |

## Your files and data

- `work/higgsfield/jobs.db` stores prompts, request IDs and output links. Keep it; it's what prevents duplicate charges. Add `work/` to your `.gitignore`.
- Higgsfield keeps outputs for at least 7 days, so download promptly.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests fake every API call and never spend money. Checked live against the real API on 2026-09-26: key check (valid and invalid keys) and Seedance 2.5 price estimate. The first paid generation with this release is still to be run.

## License

[MIT](LICENSE) © 2026 Koushik Dey
