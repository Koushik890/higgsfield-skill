#!/usr/bin/env python3
"""Higgsfield API helper for coding agents.

Standard library only. Prints JSON results on stdout and progress on stderr.
Run `python hf.py --help` for commands.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

API = "https://api.higgsfield.ai"
API_HOST = "api.higgsfield.ai"
USER_AGENT = "higgsfield-api-skill/1.0 (+https://github.com/Koushik890/higgsfield-api-skill)"
SKILL_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = SKILL_DIR / "models"
ACTIVE = {"queued", "in_progress"}
TERMINAL = {"completed", "failed", "nsfw", "canceled"}
# Jobs in these states never reached a billable generation.
NOT_BILLED = {"rejected", "failed", "nsfw", "canceled"}


class HFError(Exception):
    def __init__(self, message, http_status=None):
        super().__init__(message)
        self.http_status = http_status


def log(message):
    print(message, file=sys.stderr, flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def usd(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise HFError(f"Not a valid USD amount: {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise HFError(f"Not a valid USD amount: {value!r}")
    return amount


# ---------------------------------------------------------------- credentials

def read_env_file(path):
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def env_files():
    custom = os.environ.get("HIGGSFIELD_ENV_FILE")
    if custom:
        return [Path(custom)]
    return [Path.cwd() / ".env", Path.home() / ".config" / "higgsfield" / ".env"]


def credentials():
    """Return (key_id, secret) from the environment, else the first .env file holding both."""
    sources = [("environment", os.environ)] + [(str(p), read_env_file(p)) for p in env_files()]
    for _, values in sources:
        key_id = (values.get("HF_API_KEY_ID") or "").strip()
        secret = (values.get("HF_API_KEY_SECRET") or "").strip()
        if key_id and secret:
            if any(c.isspace() or c == ":" for c in key_id) or any(c.isspace() for c in secret):
                raise HFError("HF_API_KEY_ID/HF_API_KEY_SECRET contain spaces or ':'; re-copy them from the console")
            return key_id, secret
    places = ", ".join(str(p) for p in env_files())
    raise HFError(f"No Higgsfield credentials. Set HF_API_KEY_ID and HF_API_KEY_SECRET in the environment or in one of: {places}")


# ----------------------------------------------------------------------- HTTP

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # never forward the Authorization header to another location


_api_opener = build_opener(_NoRedirect)
_media_opener = build_opener()


def http(method, path, body=None, timeout=60):
    """Authenticated JSON call to the production API. `path` starts with '/'."""
    if not path.startswith("/"):
        raise HFError(f"Refusing to call a non-API path: {path}")
    key_id, secret = credentials()
    headers = {
        "Authorization": f"Key {key_id}:{secret}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body, allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    request = Request(API + path, data=data, headers=headers, method=method)
    try:
        with _api_opener.open(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024)
    except HTTPError as exc:
        detail = ""
        try:
            parsed = json.loads(exc.read(64 * 1024) or b"{}")
            detail = parsed.get("detail") or parsed.get("error") or parsed.get("message") or ""
        except (ValueError, AttributeError, OSError):
            pass
        hint = {401: "check the API key", 402: "add credits in the console", 403: "key lacks access or request was blocked",
                404: "unknown model endpoint", 422: "invalid parameters", 429: "rate limited; wait and retry"}.get(exc.code, "")
        message = f"HTTP {exc.code} on {method} {path}"
        if hint:
            message += f" ({hint})"
        if detail:
            message += f": {str(detail)[:300]}"
        raise HFError(message, http_status=exc.code) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise HFError(f"Network error on {method} {path}: {getattr(exc, 'reason', exc)}") from None
    try:
        result = json.loads(raw)
    except ValueError:
        raise HFError(f"Non-JSON response from {path}") from None
    if not isinstance(result, dict):
        raise HFError(f"Unexpected response shape from {path}")
    return result


# --------------------------------------------------------------------- models

def model_dirs():
    return [Path.cwd() / "work" / "higgsfield" / "models", MODELS_DIR]


def model_files():
    """Map model id -> file, project models first so they override bundled ones."""
    files = {}
    for d in reversed(model_dirs()):
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            files[p.stem] = p
    return files


def load_model(name):
    path = Path(name)
    if path.suffix != ".json":
        files = model_files()
        path = files.get(name) or files.get(name.strip("/").replace("/", "-"))
        if path is None:
            close = [m for m in files if all(part in m for part in re.split(r"[\s/_-]+", name.lower()) if part)]
            hint = f" Did you mean: {', '.join(close[:8])}?" if close else " Run `models` to list them."
            raise HFError(f"Unknown model '{name}'.{hint}")
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HFError(f"Cannot read model file {path}: {exc}") from None
    for key in ("id", "endpoint", "input_schema"):
        if key not in spec:
            raise HFError(f"Model file {path} is missing '{key}'")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._\-/]*", spec["endpoint"]) or ".." in spec["endpoint"]:
        raise HFError(f"Model file {path} has an invalid endpoint")
    return spec


def list_models(search=None):
    rows = []
    for stem, path in sorted(model_files().items()):
        spec = json.loads(path.read_text(encoding="utf-8"))
        row = {"model": stem, "name": spec.get("name", ""), "category": spec.get("category", ""),
               "price": spec.get("price_check", "unchecked")}
        if spec.get("sample_usd"):
            row["example_usd"] = spec["sample_usd"]
        if not search or all(w in json.dumps(row).lower() for w in search.lower().split()):
            rows.append(row)
    return rows


def model_info(spec):
    props = spec["input_schema"].get("properties", {})
    required = set(spec["input_schema"].get("required", []))
    params = {}
    for name, rule in props.items():
        brief = {k: rule[k] for k in ("type", "enum", "default", "minimum", "maximum", "minItems", "maxItems",
                                     "maxLength", "format") if k in rule}
        if rule.get("type") == "array" and isinstance(rule.get("items"), dict):
            brief["items"] = rule["items"].get("type") or "object"
        if rule.get("description"):
            brief["about"] = rule["description"][:200]
        if name in required:
            brief["required"] = True
        params[name] = brief
    return {"model": spec["id"], "name": spec.get("name"), "endpoint": spec["endpoint"],
            "price_check": spec.get("price_check"), "example_usd": spec.get("sample_usd"),
            "category": spec.get("category"), "summary": spec.get("summary"), "pricing": spec.get("pricing_note") or
            "Not published; `estimate` asks your account for the price.", "outputs": spec.get("outputs"),
            "params": params, "example": spec.get("example"), "docs": spec.get("docs")}


# Subset of JSON Schema used by Higgsfield model schemas.
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict, "null": type(None)}


def _is_type(value, kind):
    if kind in ("integer", "number") and isinstance(value, bool):
        return False
    if kind == "integer" and isinstance(value, float) and value.is_integer():
        return True
    return isinstance(value, _TYPES.get(kind, object))


def schema_errors(schema, value, where="request"):
    """Yield human-readable problems; empty means valid."""
    if not isinstance(schema, dict):
        return
    kinds = schema.get("type")
    if kinds is not None:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if not any(_is_type(value, k) for k in kinds):
            yield f"{where} must be {' or '.join(kinds)}"
            return
    if "const" in schema and value != schema["const"]:
        yield f"{where} must be {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        yield f"{where} must be one of {schema['enum']}, got {value!r}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            yield f"{where} must be >= {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            yield f"{where} must be <= {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            yield f"{where} must be > {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            yield f"{where} must be < {schema['exclusiveMaximum']}"
        step = schema.get("multipleOf")
        if step and abs(Decimal(str(value)) % Decimal(str(step))) != 0:
            yield f"{where} must be a multiple of {step}"
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or (schema.get("minLength") and not value.strip()):
            yield f"{where} must not be empty" if schema.get("minLength") == 1 else f"{where} is too short"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            yield f"{where} must be at most {schema['maxLength']} characters"
        if "pattern" in schema and not re.search(schema["pattern"], value):
            yield f"{where} has the wrong format"
        if schema.get("format") == "uri" and not re.match(r"https?://[^\s/]+", value):
            yield f"{where} must be a public URL (use `upload` for local files)"
        if schema.get("format") == "uuid":
            try:
                UUID(value)
            except ValueError:
                yield f"{where} must be a UUID"
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            yield f"{where} needs at least {schema['minItems']} item(s)"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            yield f"{where} allows at most {schema['maxItems']} item(s)"
        for i, item in enumerate(value):
            yield from schema_errors(schema.get("items"), item, f"{where}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                yield f"missing required '{name}'" if where == "request" else f"{where}.{name} is required"
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            path = name if where == "request" else f"{where}.{name}"
            if name in props:
                yield from schema_errors(props[name], item, path)
            elif extra is False:
                yield f"unknown parameter '{path}' (allowed: {', '.join(props)})"
            elif isinstance(extra, dict):
                yield from schema_errors(extra, item, path)
    for sub in schema.get("allOf", []):
        yield from schema_errors(sub, value, where)
    if "anyOf" in schema and all(list(schema_errors(s, value, where)) for s in schema["anyOf"]):
        yield f"{where} does not match any allowed form"
    if "oneOf" in schema and sum(not list(schema_errors(s, value, where)) for s in schema["oneOf"]) != 1:
        yield f"{where} must match exactly one allowed form"
    if "if" in schema:
        branch = "then" if not list(schema_errors(schema["if"], value, where)) else "else"
        yield from schema_errors(schema.get(branch), value, where)


def validate(spec, inputs):
    if not isinstance(inputs, dict):
        raise HFError("Request must be a JSON object")
    if "properties" not in spec["input_schema"]:
        raise HFError(f"Higgsfield publishes no input parameters for {spec['id']}; use it from the console instead")
    problems = list(dict.fromkeys(schema_errors(spec["input_schema"], inputs)))
    if problems:
        raise HFError(f"Invalid request for {spec['id']}: " + "; ".join(problems[:6]))
    return inputs


def effective(spec, payload, key):
    return payload.get(key, spec["input_schema"].get("properties", {}).get(key, {}).get("default"))


# -------------------------------------------------------------------- pricing

def video_token_price(spec, payload, description):
    """Seedance-style pricing: ceil(seconds * width * height * fps / divisor) tokens at a live per-token rate."""
    rule = spec["pricing"]
    match = re.search(rule["rate_regex"], description)
    if not match:
        raise HFError("Higgsfield's pricing text no longer matches this model file; re-check the model page before generating")
    rate = usd(match.group(1))
    by_aspect = rule["sizes"].get(str(effective(spec, payload, "resolution")))
    if not by_aspect:
        raise HFError("No known output size for this resolution; cannot price it")
    size = by_aspect.get(str(effective(spec, payload, "aspect_ratio")))
    # When the output shape follows an input image, price the largest shape as an upper bound.
    upper_bound = size is None
    width, height = size or max(by_aspect.values(), key=lambda wh: wh[0] * wh[1])
    seconds = int(effective(spec, payload, "duration"))
    divisor = int(rule["divisor"])
    tokens = (seconds * width * height * int(rule["fps"]) + divisor - 1) // divisor
    price = (Decimal(tokens) * rate / Decimal(rule["per_tokens"])).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    return price, "computed from live rate" + (" (upper bound)" if upper_bound else "")


def per_second_price(spec, payload, description):
    """Wan-style pricing: a live per-second rate for the chosen resolution times the duration."""
    rates = {res: usd(amount) for res, amount in re.findall(spec["pricing"]["rates_regex"], description)}
    resolution = str(effective(spec, payload, "resolution"))
    if resolution not in rates:
        raise HFError("Higgsfield's pricing text no longer lists this resolution; re-check before generating")
    seconds = Decimal(str(effective(spec, payload, "duration")))
    return (rates[resolution] * seconds).quantize(Decimal("0.0001"), ROUND_HALF_UP), "computed from live rate"


def estimate(spec, payload):
    """Return (usd, source). Uses the API's USD figure when given, else the model's pricing rule."""
    result = http("POST", f"/estimate/{spec['endpoint']}", payload)
    if result.get("usd") is not None:
        return usd(result["usd"]), "api"
    description = str(result.get("pricing_description") or "")
    method = spec.get("pricing", {}).get("method")
    if description and method == "video_tokens":
        return video_token_price(spec, payload, description)
    if description and method == "per_second":
        return per_second_price(spec, payload, description)
    raise UnpricedError("Higgsfield returned no USD estimate for this model. Pricing text: "
                        + (description[:400] or spec.get("pricing_note") or "none published")
                        + ". Tell the user, then pass --allow-unpriced only if they accept an unknown price.")


class UnpricedError(HFError):
    pass


# ---------------------------------------------------------------------- state

class Store:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "jobs.db", timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                name TEXT PRIMARY KEY, model TEXT, endpoint TEXT, payload TEXT, fingerprint TEXT,
                estimate_usd TEXT, price_source TEXT, budget TEXT, status TEXT, request_id TEXT,
                response TEXT, files TEXT, created TEXT, updated TEXT);
            CREATE TABLE IF NOT EXISTS budgets (name TEXT PRIMARY KEY, limit_usd TEXT);
        """)

    def get(self, name):
        row = self.db.execute("SELECT * FROM jobs WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def require(self, name):
        job = self.get(name)
        if not job:
            raise HFError(f"No job named '{name}'. Run `list` to see jobs.")
        return job

    def update(self, name, **fields):
        fields["updated"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE jobs SET {cols} WHERE name=?", (*fields.values(), name))

    def all(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM jobs ORDER BY created")]


def fingerprint(endpoint, payload):
    return hashlib.sha256(json.dumps([endpoint, payload], sort_keys=True).encode()).hexdigest()


def summary(job):
    keys = ("name", "model", "status", "request_id", "estimate_usd", "price_source", "budget", "created")
    out = {k: job.get(k) for k in keys if job.get(k)}
    if job.get("files"):
        out["files"] = json.loads(job["files"])
    return out


# ----------------------------------------------------------------------- jobs

def submit(store, spec, payload, name, max_usd=None, budget=None, budget_usd=None, allow_duplicate=False,
           allow_unpriced=False):
    validate(spec, payload)
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", name):
        raise HFError("Job name must be letters, digits, '.', '_' or '-' (max 81 chars)")
    fp = fingerprint(spec["endpoint"], payload)
    existing = store.get(name)
    if existing:
        if existing["fingerprint"] != fp:
            raise HFError(f"Job '{name}' already exists with a different request; choose a new job name")
        log(f"Job '{name}' was already submitted; not charging again.")
        return existing
    if not allow_duplicate:
        twin = store.db.execute("SELECT name FROM jobs WHERE fingerprint=? AND status NOT IN (?,?,?,?)",
                                (fp, *sorted(NOT_BILLED))).fetchone()
        if twin:
            raise HFError(f"Identical request already submitted as job '{twin[0]}'. Pass --allow-duplicate to pay for it again.")
    if (budget is None) != (budget_usd is None):
        raise HFError("Use --budget and --budget-usd together")

    try:
        price, source = estimate(spec, payload)
        log(f"Estimated cost: ${price} ({source})")
    except UnpricedError:
        if not allow_unpriced or max_usd is not None or budget is not None:
            raise
        price, source = None, "unknown (user accepted)"
        log("Price unknown; submitting because --allow-unpriced was given.")
    if max_usd is not None and price > usd(max_usd):
        raise HFError(f"Estimate ${price} is over --max-usd ${usd(max_usd)}; nothing submitted")

    store.db.execute("BEGIN IMMEDIATE")
    try:
        if budget is not None:
            limit = usd(budget_usd)
            row = store.db.execute("SELECT limit_usd FROM budgets WHERE name=?", (budget,)).fetchone()
            if row and usd(row[0]) != limit:
                raise HFError(f"Budget '{budget}' already has limit ${row[0]}; reuse that value")
            if not row:
                store.db.execute("INSERT INTO budgets VALUES (?,?)", (budget, str(limit)))
            spent = sum((usd(r[0]) for r in store.db.execute(
                "SELECT estimate_usd, status FROM jobs WHERE budget=?", (budget,)) if r[1] not in NOT_BILLED), Decimal(0))
            if spent + price > limit:
                raise HFError(f"Budget '{budget}': ${spent} used of ${limit}; this job (${price}) would exceed it")
        store.db.execute(
            "INSERT INTO jobs (name, model, endpoint, payload, fingerprint, estimate_usd, price_source, budget, status, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, spec["id"], spec["endpoint"], json.dumps(payload), fp, None if price is None else str(price), source, budget, "submitting", now(), now()))
        store.db.execute("COMMIT")
    except BaseException:
        store.db.execute("ROLLBACK")
        raise

    try:
        result = http("POST", f"/{spec['endpoint']}", payload, timeout=120)
    except HFError as exc:
        definite = exc.http_status is not None and 400 <= exc.http_status < 500
        store.update(name, status="rejected" if definite else "unknown")
        if not definite:
            log("Submission outcome unknown. Do NOT resubmit; check the console, then use `attach` if it was accepted.")
        raise
    # Save the request ID before anything else can fail, so a paid job is never lost.
    request_id = str(result.get("request_id") or "")
    store.update(name, request_id=request_id, response=json.dumps(result),
                 status=result.get("status") if result.get("status") in ACTIVE | TERMINAL else "queued")
    try:
        UUID(request_id)
    except ValueError:
        store.update(name, status="unknown")
        raise HFError("Accepted, but the response had no valid request_id; check the console and use `attach`") from None
    log(f"Submitted '{name}' as request {request_id}")
    return store.get(name)


def refresh(store, name):
    job = store.require(name)
    if not job["request_id"]:
        raise HFError(f"Job '{name}' has no request ID. If it was charged, get the ID from Higgsfield and run `attach`.")
    # Always poll the documented production endpoint rather than trusting a URL from a response.
    result = http("GET", f"/requests/{job['request_id']}/status")
    if result.get("request_id") not in (None, job["request_id"]):
        raise HFError("Status response belongs to a different request")
    status = result.get("status")
    if status not in ACTIVE | TERMINAL:
        raise HFError(f"Unexpected status {status!r}; check current Higgsfield docs")
    store.update(name, status=status, response=json.dumps(result))
    return store.get(name)


def wait(store, name, timeout=900):
    deadline, delay, last = time.monotonic() + timeout, 4.0, None
    while True:
        job = refresh(store, name)
        if job["status"] != last:
            log(f"{name}: {job['status']}")
            last = job["status"]
        if job["status"] in TERMINAL:
            return job
        if time.monotonic() + delay > deadline:
            raise HFError(f"Still {job['status']} after {timeout}s. Nothing was cancelled; run `wait` again later.")
        time.sleep(delay)
        delay = min(delay * 1.5, 30.0)


def output_urls(response):
    urls = []
    for key, value in response.items():
        if key.endswith("_url"):
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                urls.append(item["url"])
    return list(dict.fromkeys(urls))


def download(store, name, output_dir="outputs"):
    job = store.require(name)
    if job["status"] != "completed":
        job = refresh(store, name)
    if job["status"] != "completed":
        raise HFError(f"Job '{name}' is {job['status']}, not completed")
    urls = output_urls(json.loads(job["response"] or "{}"))
    if not urls:
        raise HFError("Completed response has no output URLs")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for index, url in enumerate(urls, 1):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise HFError(f"Refusing non-HTTPS or credentialed media URL: {parts.hostname}")
        ext = Path(parts.path).suffix.lower()
        request = Request(url, headers={"User-Agent": USER_AGENT})  # no API key to media hosts
        try:
            with _media_opener.open(request, timeout=300) as response:
                if not re.fullmatch(r"\.[a-z0-9]{2,5}", ext):
                    ext = mimetypes.guess_extension((response.headers.get_content_type() or "")) or ".bin"
                target = out / f"{name}-{index}{ext}"
                if target.exists():
                    raise HFError(f"{target} already exists; not overwriting")
                partial = target.with_name(target.name + ".part")
                with open(partial, "wb") as fh:
                    while chunk := response.read(1024 * 1024):
                        fh.write(chunk)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise HFError(f"Download failed from {parts.hostname}: {exc}") from None
        partial.replace(target)
        files.append(str(target.resolve()))
        log(f"Saved {target}")
    store.update(name, files=json.dumps(files))
    return store.get(name)


UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif", ".wav": "audio/wav", ".mp4": "video/mp4"}


def upload(file_path):
    """Upload a local file and return its public URL for use in image_url/video_url/audio_url fields."""
    path = Path(file_path)
    if not path.is_file():
        raise HFError(f"No such file: {path}")
    content_type = UPLOAD_TYPES.get(path.suffix.lower())
    if not content_type:
        raise HFError(f"Unsupported file type {path.suffix}; Higgsfield accepts {', '.join(sorted(UPLOAD_TYPES))}")
    size = path.stat().st_size
    if size > 500 * 1024 * 1024:
        raise HFError("File is larger than 500 MB")
    slot = http("POST", "/files/generate-upload-url", {"content_type": content_type})
    upload_url, public_url = slot.get("upload_url"), slot.get("public_url")
    for url in (upload_url, public_url):
        parts = urlsplit(url or "")
        if parts.scheme != "https" or not parts.hostname:
            raise HFError("Upload slot response did not contain HTTPS URLs")
    headers = {str(k): str(v) for k, v in (slot.get("upload_headers") or {"Content-Type": content_type}).items()
               if k.lower() not in ("authorization", "cookie", "host")}
    headers["User-Agent"] = USER_AGENT
    # The presigned storage URL never gets the API key.
    request = Request(upload_url, data=path.read_bytes(), headers=headers, method="PUT")
    try:
        with _media_opener.open(request, timeout=600) as response:
            response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HFError(f"Upload to storage failed: {exc}") from None
    log(f"Uploaded {path.name} ({size} bytes)")
    return {"file": str(path), "public_url": public_url, "content_type": content_type}


def attach(store, name, request_id, model=None):
    try:
        request_id = str(UUID(request_id))
    except ValueError:
        raise HFError("--request-id must be a UUID like d7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff") from None
    job = store.get(name)
    if job:
        if job["request_id"] and job["request_id"] != request_id:
            raise HFError(f"Job '{name}' already has request {job['request_id']}")
        store.update(name, request_id=request_id)
    else:
        spec = load_model(model) if model else None
        store.db.execute("INSERT INTO jobs (name, model, endpoint, request_id, status, created, updated) VALUES (?,?,?,?,?,?,?)",
                         (name, spec["id"] if spec else model, spec["endpoint"] if spec else None, request_id, "attached", now(), now()))
    return refresh(store, name)


def cancel(store, name):
    job = store.require(name)
    if not job["request_id"]:
        raise HFError(f"Job '{name}' has no request ID")
    http("POST", f"/requests/{job['request_id']}/cancel")
    return refresh(store, name)


# ------------------------------------------------------------------------ CLI

def load_request(args):
    if args.input:
        try:
            return json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise HFError(f"Cannot read request file {args.input}: {exc}") from None
    if args.json:
        try:
            return json.loads(args.json)
        except ValueError as exc:
            raise HFError(f"--json is not valid JSON: {exc}") from None
    raise HFError("Give the request with --input FILE or --json '{...}'")


def build_parser():
    p = argparse.ArgumentParser(prog="hf.py", description="Higgsfield API helper (image/video generation).")
    p.add_argument("--state-dir", default="work/higgsfield", help="job ledger directory (default: work/higgsfield)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("models", help="list models").add_argument("search", nargs="*", help="filter words, e.g. kling image")
    sub.add_parser("info", help="show a model's parameters, example and pricing").add_argument("model")
    sub.add_parser("check", help="verify credentials reach the API (no charge)")
    sub.add_parser("upload", help="upload a local image/video/audio, print its public URL").add_argument("file")
    cmd = sub.add_parser("presets", help="list Marketing Studio presets (for product shots, ads)")
    cmd.add_argument("--cursor")

    def request_args(cmd):
        cmd.add_argument("--model", required=True, help="model file name (see `models`) or path to a .json model file")
        cmd.add_argument("--input", help="request JSON file")
        cmd.add_argument("--json", help="request JSON inline")

    for cmd_name, text in (("validate", "check a request offline"), ("estimate", "price a request (no charge)")):
        request_args(sub.add_parser(cmd_name, help=text))

    for cmd_name, text in (("submit", "submit one paid generation"), ("run", "submit, wait and download")):
        cmd = sub.add_parser(cmd_name, help=text)
        request_args(cmd)
        cmd.add_argument("--job", required=True, help="stable job name, e.g. intro-shot-v1")
        cmd.add_argument("--max-usd", help="refuse if this job's estimate is higher")
        cmd.add_argument("--budget", help="budget group name shared across jobs")
        cmd.add_argument("--budget-usd", help="total limit for the budget group")
        cmd.add_argument("--allow-duplicate", action="store_true", help="allow paying again for an identical request")
        cmd.add_argument("--allow-unpriced", action="store_true",
                         help="submit even if Higgsfield gives no USD estimate (user accepted unknown price)")
        if cmd_name == "run":
            cmd.add_argument("--timeout", type=int, default=900)
            cmd.add_argument("--output-dir", default="outputs")

    for cmd_name, text in (("status", "check a job once"), ("cancel", "cancel a queued job")):
        sub.add_parser(cmd_name, help=text).add_argument("--job", required=True)
    cmd = sub.add_parser("wait", help="poll a job until it finishes")
    cmd.add_argument("--job", required=True)
    cmd.add_argument("--timeout", type=int, default=900)
    cmd = sub.add_parser("download", help="save a completed job's files")
    cmd.add_argument("--job", required=True)
    cmd.add_argument("--output-dir", default="outputs")
    cmd = sub.add_parser("attach", help="link a known request ID to a job (recovery)")
    cmd.add_argument("--job", required=True)
    cmd.add_argument("--request-id", required=True)
    cmd.add_argument("--model", help="model name, when creating a new job record")
    sub.add_parser("list", help="show all jobs in the ledger")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "models":
            result = list_models(" ".join(args.search))
        elif args.command == "info":
            result = model_info(load_model(args.model))
        elif args.command == "upload":
            result = upload(args.file)
        elif args.command == "presets":
            query = "size=50" + (f"&cursor={quote(args.cursor, safe='')}" if args.cursor else "")
            reply = http("GET", f"/marketing-studio/image/presets?{query}")
            result = {"cursor": reply.get("cursor"), "total": reply.get("total"),
                      "presets": [{k: p.get(k) for k in ("id", "name", "type")} for p in reply.get("items", [])]}
        elif args.command == "check":
            # A 404 on a random request ID proves the key was accepted without generating anything.
            try:
                http("GET", "/requests/00000000-0000-4000-8000-000000000000/status")
                result = {"ok": True}
            except HFError as exc:
                if exc.http_status in (401, 403):
                    raise
                result = {"ok": True, "note": "credentials accepted"} if exc.http_status == 404 else {"ok": False, "error": str(exc)}
        elif args.command in ("validate", "estimate"):
            spec = load_model(args.model)
            payload = validate(spec, load_request(args))
            if args.command == "validate":
                result = {"valid": True, "model": spec["id"], "endpoint": spec["endpoint"]}
            else:
                price, source = estimate(spec, payload)
                result = {"model": spec["id"], "estimated_usd": str(price), "source": source}
        else:
            store = Store(args.state_dir)
            if args.command in ("submit", "run"):
                spec = load_model(args.model)
                job = submit(store, spec, load_request(args), args.job, args.max_usd, args.budget,
                             args.budget_usd, args.allow_duplicate, args.allow_unpriced)
                if args.command == "run":
                    job = wait(store, args.job, args.timeout)
                    if job["status"] == "completed":
                        job = download(store, args.job, args.output_dir)
                result = summary(job)
            elif args.command == "status":
                result = summary(refresh(store, args.job))
            elif args.command == "wait":
                result = summary(wait(store, args.job, args.timeout))
            elif args.command == "download":
                result = summary(download(store, args.job, args.output_dir))
            elif args.command == "attach":
                result = summary(attach(store, args.job, args.request_id, args.model))
            elif args.command == "cancel":
                result = summary(cancel(store, args.job))
            else:
                result = [summary(j) for j in store.all()]
    except HFError as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        return 2
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("status") in ("failed", "nsfw", "canceled"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
