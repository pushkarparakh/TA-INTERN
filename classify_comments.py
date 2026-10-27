#!/usr/bin/env python3
"""Classify forum comments with Cloudflare Workers AI's Clef decision model.

Live requests are deliberately opt-in: use --run-live only after configuring
cloud-flare.local.sh (or the corresponding environment variables).
"""

import argparse
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


LABELS = ("acceptable", "toxic", "spam")
MODEL = "clef"
QUESTION_NAME = "moderation"
DEFAULT_TIMEOUT = 60
MAX_ATTEMPTS = 4

INSTRUCTIONS = """Classify `comment`, a post in a college course forum. Pick exactly one label.
acceptable is a good-faith, course-relevant or ordinary community post, including criticism,
questions, disagreement, and constructive feedback that is not abusive. toxic is harassment,
insults, threats, hateful or discriminatory content, or demeaning attacks on a person or group.
spam is unsolicited promotion, advertising, scams, referral/engagement bait, or offers to sell
unrelated services, accounts, assignments, notes, or leaked material. Use toxic for an abusive
post even if it also promotes something; otherwise use spam for promotional posts."""

CRITERIA = {
    "acceptable": "A good-faith, non-abusive forum comment, question, discussion, or constructive feedback.",
    "toxic": "Harassment, insults, threats, hateful/discriminatory language, or a demeaning personal or group attack.",
    "spam": "Unsolicited promotion, advertising, scam, referral bait, or an offer to sell unrelated or improper services/material.",
}


class ValidationError(ValueError):
    """Raised when local input or a model response does not meet the expected schema."""


def load_comments(path: Path) -> tuple[dict, list[dict]]:
    """Load comments.json and validate the fields required for safe classification."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc.msg} at line {exc.lineno}") from exc

    if not isinstance(document, dict) or not isinstance(document.get("comments"), list):
        raise ValidationError("Input must be an object with a 'comments' array.")

    seen_ids = set()
    comments = []
    for index, item in enumerate(document["comments"]):
        if not isinstance(item, dict):
            raise ValidationError(f"comments[{index}] must be an object.")
        comment_id = item.get("id")
        text = item.get("comment")
        if isinstance(comment_id, bool) or not isinstance(comment_id, (int, str)) or str(comment_id).strip() == "":
            raise ValidationError(f"comments[{index}].id must be a non-empty string or integer.")
        if comment_id in seen_ids:
            raise ValidationError(f"Duplicate comment id: {comment_id!r}")
        if not isinstance(text, str) or not text.strip():
            raise ValidationError(f"comments[{index}].comment must be a non-empty string.")
        seen_ids.add(comment_id)
        comments.append(item.copy())
    return document, comments


def load_credentials(local_path: Path) -> tuple[str, str]:
    """Read environment credentials first, then the documented local shell file."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not (account and token) and local_path.exists():
        content = local_path.read_text(encoding="utf-8")
        values = dict(re.findall(r'^\s*export\s+(CLOUDFLARE_(?:ACCOUNT_ID|API_TOKEN))="([^"]*)"\s*$', content, re.M))
        account = account or values.get("CLOUDFLARE_ACCOUNT_ID")
        token = token or values.get("CLOUDFLARE_API_TOKEN")
    placeholders = {"", "your-cloudflare-api-token-goes-here", "0123456789abcdef0123456789abcdef"}
    if account in placeholders or token in placeholders or not account or not token:
        raise ValidationError(
            "Cloudflare credentials are not configured. Set CLOUDFLARE_ACCOUNT_ID and "
            "CLOUDFLARE_API_TOKEN, or create cloud-flare.local.sh from cloud-flare.sh."
        )
    return account, token


def build_payload(text: str) -> dict:
    return {
        "state": {"comment": text},
        "questions": {
            QUESTION_NAME: {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": CRITERIA,
            }
        },
    }


def parse_answer(response: object) -> dict:
    """Validate a successful documented Clef response and retain available scores."""
    if not isinstance(response, dict):
        raise ValidationError("Response is not a JSON object.")
    if response.get("success") is not True:
        errors = response.get("errors")
        detail = errors if isinstance(errors, list) else "API marked the request unsuccessful"
        raise ValidationError(f"Cloudflare API failure: {detail}")
    try:
        answer = response["result"]["answers"][QUESTION_NAME]
    except (KeyError, TypeError) as exc:
        raise ValidationError("Response is missing result.answers.moderation.") from exc
    if not isinstance(answer, dict):
        raise ValidationError("Response answer is not an object.")
    choice = answer.get("choice")
    if choice not in LABELS:
        raise ValidationError(f"Response label is invalid: {choice!r}")
    parsed = {"label": choice}
    if "confidence" in answer:
        confidence = answer["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValidationError("Response confidence must be a number from 0 to 1.")
        parsed["confidence"] = confidence
    if "probabilities" in answer:
        probabilities = answer["probabilities"]
        if not isinstance(probabilities, dict) or set(probabilities) != set(LABELS):
            raise ValidationError("Response probabilities must contain exactly the three allowed labels.")
        clean_probabilities = {}
        for label in LABELS:
            value = probabilities[label]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValidationError("Response probabilities must be finite numbers from 0 to 1.")
            clean_probabilities[label] = value
        if not 0.98 <= sum(clean_probabilities.values()) <= 1.02:
            raise ValidationError("Response probabilities do not sum to approximately 1.")
        parsed["probabilities"] = clean_probabilities
    return parsed


def error_message(exc: Exception) -> str:
    """Return a useful, non-secret diagnostic for the report."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"Network error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "Request timed out"
    return str(exc) or exc.__class__.__name__


def retry_delay(exc: Exception, attempt: int) -> float | None:
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        try:
            return max(0.0, float(retry_after)) if retry_after else min(30.0, 2 ** attempt)
        except ValueError:
            return min(30.0, 2 ** attempt)
    if isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return min(30.0, 2 ** attempt)
    return None


def request_one(text: str, account: str, token: str, opener=urllib.request.urlopen, sleep=time.sleep) -> dict:
    """Call Clef with bounded retries. Errors become failed records, never labels."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{MODEL}"
    request = urllib.request.Request(
        url,
        data=json.dumps(build_payload(text)).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with opener(request, timeout=DEFAULT_TIMEOUT) as response:
                return {"status": "classified", **parse_answer(json.load(response)), "attempts": attempt}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            delay = retry_delay(exc, attempt)
            if delay is None or attempt == MAX_ATTEMPTS:
                break
            sleep(delay)
    return {"status": "failed", "error": error_message(last_error), "attempts": attempt}


def classify_all(comments: list[dict], account: str, token: str, opener=urllib.request.urlopen, sleep=time.sleep) -> list[dict]:
    results = []
    for comment in comments:
        result = {"id": comment["id"], "text": comment["comment"], "source": comment.copy()}
        result.update(request_one(comment["comment"], account, token, opener=opener, sleep=sleep))
        results.append(result)
    return results


def write_json(path: Path, source: dict, results: list[dict]) -> dict:
    output = {
        "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {key: value for key, value in source.items() if key != "comments"},
        "results": results,
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def report_html(output: dict) -> str:
    """Return a standalone, safely rendered report; cards use textContent, not HTML."""
    # JSON is read as text, but encode HTML-significant characters so untrusted
    # comment text can never terminate or be interpreted outside this data node.
    data = (json.dumps(output, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))
    title = html.escape(str(output.get("source", {}).get("forum", "Comment moderation report")))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clef moderation report</title><style>
:root {{ color-scheme: light; --ink:#172033; --muted:#63708a; --surface:#fff; --line:#dce3ee; --accent:#4959d4; }}
* {{ box-sizing:border-box }} body {{ margin:0; font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; color:var(--ink); background:#f4f6fb }}
main {{ max-width:980px; margin:auto; padding:36px 20px 64px }} h1 {{ margin:0 0 4px }} .sub {{ color:var(--muted); margin:0 0 24px }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px }} input,button {{ font:inherit; border:1px solid var(--line); border-radius:9px; padding:9px 12px; background:white }} input {{ flex:1; min-width:220px }} button {{ cursor:pointer }} button.active {{ background:var(--accent); border-color:var(--accent); color:white }}
.summary {{ color:var(--muted); margin:0 0 12px }} .card {{ background:var(--surface); border:1px solid var(--line); border-left:5px solid #8490a5; border-radius:10px; margin:12px 0; padding:16px }}
.card.acceptable {{ border-left-color:#16835b }} .card.toxic,.card.failed {{ border-left-color:#c43d4f }} .card.spam {{ border-left-color:#bd7609 }} .meta {{ display:flex; gap:10px; flex-wrap:wrap; color:var(--muted); font-size:.9rem }} .label {{ font-weight:700; text-transform:capitalize }} .comment {{ white-space:pre-wrap; margin:10px 0 }} .scores {{ color:var(--muted); font-size:.9rem }} .error {{ color:#9e2635; font-weight:600 }} .empty {{ color:var(--muted); padding:24px; text-align:center }}
</style></head><body><main><h1>Clef comment moderation</h1><p class="sub">{title} · Model: {html.escape(str(output.get('model', MODEL)))}</p>
<div class="controls" id="filters"><button data-filter="all" class="active">All</button><button data-filter="acceptable">Acceptable</button><button data-filter="toxic">Toxic</button><button data-filter="spam">Spam</button><button data-filter="failed">Failed</button><input id="search" type="search" placeholder="Search comments, IDs, authors…" aria-label="Search comments"></div><p class="summary" id="summary"></p><section id="cards" aria-live="polite"></section></main>
<script id="report-data" type="application/json">{data}</script><script>
const report=JSON.parse(document.getElementById('report-data').textContent), cards=document.getElementById('cards'), search=document.getElementById('search'), summary=document.getElementById('summary'); let filter='all';
function add(el,tag,text,cls){{const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=text;el.append(n);return n}}
function render(){{const q=search.value.toLowerCase();const rows=report.results.filter(r=>{{const hay=[r.id,r.text,r.label,r.status,r.source&&r.source.author].join(' ').toLowerCase();return (filter==='all'||r.status===filter||r.label===filter)&&hay.includes(q)}});cards.replaceChildren();summary.textContent=`${{rows.length}} of ${{report.results.length}} comments shown`;if(!rows.length){{add(cards,'p','No matching comments.','empty');return}}for(const r of rows){{const c=document.createElement('article');c.className='card '+(r.status==='failed'?'failed':r.label);const h=document.createElement('div');h.className='meta';add(h,'span','ID: '+r.id);if(r.source&&r.source.author)add(h,'span',r.source.author);if(r.source&&r.source.thread)add(h,'span',r.source.thread);c.append(h);add(c,'p',r.text,'comment');if(r.status==='failed')add(c,'p','Request failed — '+(r.error||'Unknown error')+' (attempts: '+r.attempts+')','error');else{{add(c,'div',r.label,'label');let score=[];if(r.confidence!==undefined)score.push('Confidence: '+Number(r.confidence).toFixed(3));if(r.probabilities)score.push('Probabilities: '+Object.entries(r.probabilities).map(([k,v])=>k+' '+Number(v).toFixed(3)).join(' · '));if(score.length)add(c,'div',score.join(' | '),'scores')}}cards.append(c)}}}}
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));render()}}));search.addEventListener('input',render);render();
</script></body></html>"""


def write_report(path: Path, output: dict) -> None:
    path.write_text(report_html(output), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Classify comments with Cloudflare Clef.")
    parser.add_argument("--run-live", action="store_true", help="Make real, credentialed Cloudflare API requests.")
    parser.add_argument("--input", type=Path, default=Path("comments.json"))
    parser.add_argument("--output", type=Path, default=Path("classifications.json"))
    parser.add_argument("--report", type=Path, default=Path("comments.html"))
    parser.add_argument("--credentials", type=Path, default=Path("cloud-flare.local.sh"))
    args = parser.parse_args(argv)
    if not args.run_live:
        parser.error("Refusing to make API calls without --run-live. Run the mocked tests first, then explicitly opt in.")
    try:
        source, comments = load_comments(args.input)
        account, token = load_credentials(args.credentials)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    results = classify_all(comments, account, token)
    output = write_json(args.output, source, results)
    write_report(args.report, output)
    failed = sum(item["status"] == "failed" for item in results)
    print(f"Wrote {args.output} and {args.report}: {len(results) - failed} classified, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
