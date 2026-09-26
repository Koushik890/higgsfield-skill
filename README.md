# Higgsfield API Skill

Let your coding agent make videos and images with the [Higgsfield API](https://docs.higgsfield.ai/docs). Ask in plain words; the agent picks a model, shows the price, generates, and saves the file into your project's `outputs/` folder.

**79 models** — Seedance, Kling, Wan, Minimax Hailuo, LTX, Grok Imagine, Happy Horse, Higgsfield Soul, Cinema Studio, Genjutsu, Ideogram, Recraft, Qwen Image, Z-Image and Marketing Studio. Full list with example prices: [MODELS.md](MODELS.md).

Works with **every coding agent that supports skills**: Claude Code, Codex, Gemini CLI, GitHub Copilot, Windsurf, Trae, Cline, Roo Code, Kiro, OpenCode, Goose, Qwen Code and many more. One command installs it for all of them.

> Independent open-source project. Not made by or affiliated with Higgsfield. You pay Higgsfield directly for what you generate.

## What it does

- **Every model on the Higgsfield catalog**, each with its official parameter rules, so bad requests are caught before you pay.
- **Shows the price first.** Most models get an exact USD estimate from your account; a few are computed from Higgsfield's live rates. If Higgsfield gives no price, the agent asks you first.
- **Uses your own images, video and audio.** `upload` turns a local file into a link the model can use (image-to-video, edits, references).
- **One command from prompt to file.** Submit, wait, download.
- **Never loses a paid job.** The request ID is saved the moment Higgsfield accepts it.
- **Won't charge you twice by accident.** Same job name never re-runs; an identical request under a new name needs an explicit flag.
- **Optional spending limits,** per job or for a group of jobs.
- **Keeps your key private.** Read from the environment or a private file; sent only to `api.higgsfield.ai`, never to upload or download servers.
- **Stays up to date.** One command re-reads every model's docs from Higgsfield.
- **No dependencies.** Plain Python 3.8+.

## Install

One command, any OS (needs [Node.js](https://nodejs.org)):

```sh
npx skills add Koushik890/higgsfield-api-skill -g
```

It finds the coding agents on your computer and installs the skill for all of them, listing them first so you can untick any. The files go into one shared folder, `~/.agents/skills/higgsfield`, and each agent gets a link to it.

- Every supported agent, no questions: add `--all`
- Only some agents: `-a claude-code -a codex -a gemini-cli`
- Only the current project instead of your whole user: leave out `-g`
- Update later: `npx skills update higgsfield`
- Remove: `npx skills remove higgsfield`

This uses the open-source [`skills`](https://github.com/vercel-labs/skills) installer.

**No Node.js?** These scripts install for Claude Code (or Codex with `-Codex` / `--codex`):

```powershell
irm https://raw.githubusercontent.com/Koushik890/higgsfield-api-skill/main/install.ps1 | iex
```

```sh
curl -fsSL https://raw.githubusercontent.com/Koushik890/higgsfield-api-skill/main/install.sh | sh
```

## Add your API key

1. Create a key at [console.higgsfield.ai](https://console.higgsfield.ai).
2. Create the file `~/.config/higgsfield/.env` (on Windows `C:\Users\<you>\.config\higgsfield\.env`) containing:

   ```
   HF_API_KEY_ID=your-key-id
   HF_API_KEY_SECRET=your-key-secret
   ```

3. Check it (free):

   ```sh
   python ~/.agents/skills/higgsfield/scripts/hf.py check
   ```

One key file works for every agent. Environment variables with the same names also work and take priority. Never paste your key into a chat.

If you used the script installers, the skill lives in `~/.claude/skills/higgsfield` (or `~/.codex/skills/higgsfield`) instead.

## Use it

Just ask your agent:

```text
Make a 5-second 720p video of waves hitting a lighthouse at sunset.
```

```text
Animate photo.jpg into a 5-second clip with Kling 3.0 Pro.
```

```text
Which video models cost under $0.50 for 5 seconds? Don't generate yet.
```

```text
Make a product shot of bottle.png with a Marketing Studio preset.
```

```text
Make three 4-second Seedance clips for my intro. Keep the total under $6.
```

## Models at a glance

| Family | Examples | Typical example price* |
|---|---|---|
| Seedance 2.5 / 2.0 (ByteDance) | text, image, reference to video; video edit and extend | $2.31 (5 s 720p) |
| Kling 2.5 Turbo, 2.6, 3.0, 3.0 Turbo, 4K, O3, Omni | text/image to video, first-last frame, motion control, video edit | $0.19 – $1.16 |
| Wan 2.6, 2.7, 3.0, 3.0 Prime (Alibaba) | text, image, reference to video | $0.25 – $0.98 |
| Minimax Hailuo 2.3, H3 | text, image, reference to video | $0.07 – $0.46 |
| LTX 2.5 Fast / Pro (Lightricks) | text, image to video | $0.54 – $0.72 |
| Happy Horse 1.0 / 1.1 | text, image, reference to video | $0.49 – $0.63 |
| Grok Imagine (xAI) | image 2.0, video reference | $0.06 image, $0.40 video |
| Higgsfield Soul, Cinema Studio, Genjutsu | images, cinematic video, motion transfer, object swap | $0.004 – $0.09 image |
| Ideogram 4.0, Recraft 4.1, Qwen Image 3, Z-Image Turbo | text to image, image edit | $0.015 – $0.21 |
| Marketing Studio | product shots, ads, presets | $0.44 |

\*What Higgsfield's `estimate` returned for each model's default settings on 2026-09-26. Your settings and discounts change the price; the agent always shows the real estimate before generating. See [MODELS.md](MODELS.md) for every model.

**Price notes**
- 56 models return an exact USD estimate from your account.
- 5 are computed from Higgsfield's live published rate (Seedance 2.5 text/image-to-video, Wan 3.0). Image-to-video uses the largest frame size, so it's an upper bound.
- 12 publish only a pricing formula the skill can't compute without more information (e.g. input video length). The agent shows you the formula and asks before generating.
- 6 Kling motion-control / video-edit models currently return a server error from Higgsfield's estimate endpoint. The agent tells you and asks first.
- Soul ID publishes no inputs, so it's console-only.

## Command reference

Run from your project folder. Results are JSON.

| Command | What it does | Costs money |
|---|---|---|
| `check` | Confirms the API key works | No |
| `models [words]` | Lists/searches models | No |
| `info MODEL` | All parameters, defaults, pricing, example | No |
| `upload FILE` | Uploads a local image/video/audio, returns a URL | No |
| `presets` | Marketing Studio presets | No |
| `validate --model M --input F` | Checks a request offline | No |
| `estimate --model M --input F` | Prices a request | No |
| `run --model M --input F --job NAME` | Submit, wait, download | **Yes** |
| `submit --model M --input F --job NAME` | Submit only | **Yes** |
| `status` / `wait --job NAME` | Check or wait for a job | No |
| `download --job NAME` | Saves finished files to `outputs/` | No |
| `list` | All jobs with request ID, status, estimate, files | No |
| `attach --job NAME --request-id ID --model M` | Links a known request ID to a job (recovery) | No |
| `cancel --job NAME` | Cancels a job that hasn't started | No |

`--model` takes a model id (`kling-video-v3.0-pro-text-to-video`) or endpoint (`kling-video/v3.0/pro/text-to-video`). Use `--json '{...}'` instead of `--input FILE` for short requests. Limits: `--max-usd 2` for one job, or `--budget intro --budget-usd 6` across jobs. `--allow-unpriced` only after you accept an unknown price.

Example: image to video with a local photo

```sh
python hf.py upload photo.jpg            # -> "public_url": "https://..."
python hf.py info kling-video-v3.0-pro-image-to-video
python hf.py run --model kling-video-v3.0-pro-image-to-video --job photo-anim-v1 \
  --json '{"prompt": "Slow push-in, hair moving in the wind", "image_url": "https://..."}'
```

## Keeping models up to date

Higgsfield adds models often. Refresh everything from their live docs:

```sh
python tools/sync_models.py            # all models + MODELS.md
python tools/sync_models.py wan/v2.7/text-to-video   # just one
```

Your own model files in the project's `work/higgsfield/models/` override the bundled ones.

## Troubleshooting

| Message | Fix |
|---|---|
| `No Higgsfield credentials` | Fill in `~/.config/higgsfield/.env`, then run `check`. |
| `HTTP 401` | Key ID or secret is wrong; re-copy both from the console. |
| `HTTP 402` | Add credits in the console. |
| `Invalid request ...` / `HTTP 422` | A parameter isn't allowed; run `info MODEL`. |
| `must be a public URL` | Run `upload FILE` and use the returned `public_url`. |
| `returned no USD estimate` | Higgsfield doesn't price this model via API. Accept an unknown price with `--allow-unpriced`, or pick another model. |
| `pricing text no longer matches` | Higgsfield changed its pricing; run `tools/sync_models.py` and re-check. |
| Job status `unknown` | May have been charged. Don't resubmit. Find the request ID, then `attach`. |
| `run` timed out | Nothing is lost. `wait --job NAME`, then `download --job NAME`. |

## Your files and data

- `work/higgsfield/jobs.db` stores prompts, request IDs and output links; it prevents duplicate charges. Add `work/` to your `.gitignore`.
- Uploaded files and outputs are kept by Higgsfield for a limited time (at least 7 days for outputs), so download promptly.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests fake every API call and never spend money. Checked live against the real API on 2026-09-26: key check, uploads (image, video, audio), Marketing Studio presets, and a price estimate for every model. A real paid generation was also run end to end (Minimax Hailuo 2.3 text-to-video, about $0.07 estimated): submit, wait and download all worked, and the result was a 1366x768 MP4.

## License

[MIT](LICENSE) © 2026 Koushik Dey
