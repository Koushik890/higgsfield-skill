---
name: higgsfield
description: Generate videos and images with the pay-as-you-go Higgsfield API (api.higgsfield.ai) from inside a project - 79 models including Seedance, Kling, Wan, Minimax Hailuo, LTX, Grok Imagine, Soul, Ideogram, Recraft, Qwen Image and Marketing Studio. Price a request, upload reference media, submit, wait, and download to outputs/. Use when the user asks to create or edit a video or image with Higgsfield or any of these models.
---

# Higgsfield generation

Helper: `python <skill-dir>/scripts/hf.py` (Python 3.8+, standard library only). JSON on stdout, progress on stderr. Run it from the user's project folder; jobs are recorded in `work/higgsfield/jobs.db`, files go to `outputs/`.

## 1. Pick the model

- `hf.py models [words]` searches all models, e.g. `hf.py models kling image`. `MODELS.md` in the skill folder lists them all with example prices.
- If the user names a model, use it exactly (model id like `kling-video-v3.0-pro-text-to-video` or its endpoint `kling-video/v3.0/pro/text-to-video`). Never swap to a different model or variant without asking.
- If they don't, suggest one that fits the task (text-to-video, image-to-video, reference-to-video, video-edit, text-to-image, image edit) and mention its example price. Default for video: `bytedance-seedance-2.5-text-to-video`, 5 s, 720p.
- `hf.py info <model>` shows every parameter (type, allowed values, default, required), outputs, pricing note, and an example. Read it before writing a request; parameters differ between models, even between variants of one model. For full details open the model's `agent_prompt` URL from `info`.

## 2. Build the request

- Write JSON to `work/higgsfield/<job>.json` with only parameters from `info`. `hf.py validate --model M --input F` checks it offline.
- Local images/video/audio: `hf.py upload <file>` returns a `public_url`; put that URL in the model's field (`image_url`, `image_urls`, `video_url`, `start_image_url`, ...). Only upload files the user asked you to use. Supported: jpg, png, webp, gif, wav, mp4.
- Marketing Studio product shots / ads with a preset: `hf.py presets` lists preset ids; ask the user to choose; set `enhance_prompt: true`, `preset_id`, and the product image in `image_urls`. Never invent preset ids.
- `hf.py check` verifies the key for free. If credentials are missing, tell the user to fill `~/.config/higgsfield/.env` (`HF_API_KEY_ID`, `HF_API_KEY_SECRET`). Never ask for or print the key, and never put it in commands or project files.

## 3. Price it

`hf.py estimate --model M --input F` is free. Tell the user the number and whether it is exact from Higgsfield, computed, or an upper bound.
- If it reports no USD price (some Seedance 2.0, Seedance 2.5 reference/edit/extend, Cinema Studio, Genjutsu, Marketing Studio flare/sunburst, Minimax H3 reference): show the pricing text and ask whether they accept an unknown price. Only then add `--allow-unpriced`.
- If the estimate itself fails with HTTP 500 (some Kling motion-control and video-edit models), say so; ask before submitting without a price.

## 4. Generate

- A clear request to generate ("make a 5 s video of ...") authorizes that one generation at the quoted price. Asking for advice, prices, or installing the skill does not.
- `hf.py run --model M --input F --job <name>` submits, waits, downloads. Use a short descriptive job name (`beach-intro-v1`). Add `--max-usd N` or `--budget NAME --budget-usd N` only when the user sets a limit.
- If `run` times out: `hf.py wait --job <name>`, then `hf.py download --job <name>`. Never resubmit to retry.

## Protecting the user's money

- Same `--job` name is never charged twice. An identical request under a new name is refused unless the user wants another copy (`--allow-duplicate`).
- Status `unknown` after submit means it may have been charged. Do not submit again. Get the request ID from the user (console or Higgsfield support) and run `hf.py attach --job <name> --request-id <id> --model <m>`.
- `hf.py list` shows all jobs with request IDs, status, estimates, files. `hf.py cancel --job <name>` works only while queued.
- Call estimates estimates. The real charge is on the console usage page.

## 5. Check and report

Confirm the files exist and look at them (for video, extract a frame with ffmpeg) before describing the result. Report paths, model, settings, and estimated cost.

## Keeping models current

`python <skill-dir>/tools/sync_models.py` re-downloads every model's agent prompt from Higgsfield and rebuilds `models/` and `MODELS.md`. For one model: `python tools/sync_models.py <endpoint>`. Project-specific model files in `work/higgsfield/models/` override bundled ones.
