---
name: higgsfield
description: Generate videos and images with the pay-as-you-go Higgsfield API (api.higgsfield.ai) from inside a project - price a request, submit it, wait, and download the result to outputs/. Use when the user asks to create a video or image with Higgsfield, Seedance, or this skill.
---

# Higgsfield generation

Helper: `python <skill-dir>/scripts/hf.py` (Python 3.8+, standard library only). It prints JSON on stdout and progress on stderr. Run it from the user's project folder; job records live in `work/higgsfield/jobs.db` and files go to `outputs/`.

## Before anything paid

1. `hf.py check` confirms the API key works (free). If it fails, tell the user to put `HF_API_KEY_ID` and `HF_API_KEY_SECRET` in `~/.config/higgsfield/.env` (or the environment). Never ask for the key in chat, never print it, never put it in a command line or a file inside the project.
2. `hf.py models` lists model files. Use the one that fits. If the user wants a model with no file yet, see "Adding a model" below - do not guess parameters.
3. Write the request to a JSON file (e.g. `work/higgsfield/<job>.json`) using only the parameters in the model file, then run `hf.py estimate --model <m> --input <file>` (free) and tell the user the estimated cost.

## Generating

- A clear request to generate ("make a 5s video of ...") is permission for that generation at the estimated price. Asking for advice, a price, or installing the skill is not.
- One command does everything: `hf.py run --model <m> --input <file> --job <name>`. It submits, waits, and downloads. Use a short descriptive job name, e.g. `beach-intro-v1`.
- Pass `--max-usd N` or `--budget NAME --budget-usd N` only when the user sets a limit.
- If `run` times out, use `hf.py wait --job <name>` then `hf.py download --job <name>`. Never resubmit to "retry" a job that may already be running.

## Rules that protect the user's money

- The same `--job` name is never charged twice; an identical request under a new name is refused unless the user asks for another copy (`--allow-duplicate`).
- If submission ends with status `unknown`, the request may have been accepted and charged. Do not submit again. Ask the user to find the request ID (console or Higgsfield support) and run `hf.py attach --job <name> --request-id <id>`.
- `hf.py list` shows every job, its request ID, status, estimate and files.
- Report estimates as estimates. The real charge is on the user's console usage page.

## After it finishes

Check the downloaded file exists and look at it (for video, e.g. extract a frame with ffmpeg) before describing the result. Report the file path, settings, and estimated cost.

## Adding a model

Model files live in `<skill-dir>/models/` or the project's `work/higgsfield/models/` (project copies win). Read the model's page on https://console.higgsfield.ai (API reference) and write a file like `models/seedance-2.5-t2v.json`: `endpoint`, each parameter's `type`, `required`, `enum`, `min`, `max`, `default`, plus `docs` and `checked` date. Then run `hf.py estimate` with a sample request. If the estimate returns USD, no `pricing` block is needed. If it returns only a text description, add a `pricing` rule and confirm the math against the console before any paid run.
