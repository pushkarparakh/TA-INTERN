# AI Comment Moderator Notes

## Prerequisites and setup

- Python 3.10+ (standard library only; no packages to install).
- A Cloudflare account ID and a Workers AI API token with **Workers AI - Read** and **Workers AI - Edit** permissions.
- Copy `cloud-flare.sh` to the ignored local file `cloud-flare.local.sh`, then replace its placeholder values. Alternatively, export `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in the shell. Do not commit either credential file or print the token.

## Commands

Run mocked tests first (these make no network calls):

```bash
python3 -m unittest -v test_classify_comments.py
```

After configuring credentials and explicitly approving a real run, run the classifier from the repository root:

```bash
python3 classify_comments.py --run-live
```

This writes `classifications.json` and the self-contained `comments.html`. Failed API requests remain visibly marked as failures; they are never assigned an acceptable label. To use alternate paths:

```bash
python3 classify_comments.py --run-live --input comments.json --output classifications.json --report comments.html
```

Open the generated local report on Ubuntu:

```bash
xdg-open comments.html
```

## Model and tools used

- Cloudflare Workers AI decision model: `@cf/cloudflare/clef` (Clef, not `clef-flash`).
- Python standard library (`urllib`, `json`, `html`, and `unittest`).
- Codex was used to implement and test the local program; Cloudflare Clef produced the stored classifications.
- The report provides category filters, text search, confidence/probability display when returned by Clef, and failed-request cards.

## Reflection (complete after your own audit)

_Add your brief reflection on the workflow, Clef's results, and the manual review here._
