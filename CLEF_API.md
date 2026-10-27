# The Clef API, in brief

**What Clef is.** Clef is a *decision model* from Cloudflare, run on Cloudflare's Workers
AI service. Unlike a chatbot, it does not write text. You give it some input (a comment,
a review, an email) and one or more multiple-choice questions about that input. For each
question it returns the choice it picks, and a probability for every option.

**What it is meant for.** Fast, cheap, repeatable yes/no or pick-one decisions over lots
of text: moderation (is this post toxic?), routing (which team should handle this
ticket?), tagging (what language is this in?). You describe each option in plain
English; there is no training step.

There are two models, called the same way:

| Model | Use |
| --- | --- |
| `clef-flash` | Faster and cheaper. Try this first. |
| `clef` | Larger and usually more accurate, especially on borderline inputs. |

## Credentials

You need a Cloudflare **account ID** and an **API token** with the permissions
*Workers AI - Read* and *Workers AI - Edit*. Both come from the Cloudflare dashboard.
Keep them in `cloud-flare.local.sh` (see the README), never in your code.

## The request

```
POST https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/cloudflare/<MODEL>
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

The body has two parts:

- **`state`**: the input, as named text fields. Your instructions refer to a field by
  its name in backticks, for example `` `review` ``.
- **`questions`**: one entry per question. Each has `"type": "choice"`, `instructions`
  (what to decide, and any context that helps), and `criteria` (each option's name,
  with a plain-English description of when to pick it).

```json
{
  "state": {
    "review": "Delivery took three weeks and the box was crushed, but the headphones sound great."
  },
  "questions": {
    "sentiment": {
      "type": "choice",
      "instructions": "Classify `review`, a customer review of a product bought online.",
      "criteria": {
        "positive": "Mostly happy with the product.",
        "negative": "Mostly unhappy with the product or the purchase.",
        "mixed": "Clearly both happy and unhappy about different things."
      }
    }
  }
}
```

## The response

This is a real response from `clef-flash` to the request above:

```json
{
  "result": {
    "model": "clef-flash",
    "answers": {
      "sentiment": {
        "type": "choice",
        "choice": "positive",
        "probabilities": {"positive": 0.5421, "negative": 0.0745, "mixed": 0.3834},
        "confidence": 0.1696
      }
    },
    "usage": {"input_tokens": 189, "output_tokens": 0}
  },
  "success": true,
  "errors": [],
  "messages": []
}
```

- `choice` is the option Clef picked; `probabilities` add up to about 1.
- `confidence` (0 to 1) is low when Clef is unsure. Low-confidence answers are the ones
  most worth a human look.
- Clef can be wrong. Here `clef-flash` said *positive*. The larger `clef` model said
  *mixed* (0.85), which most people would agree with.
- Check `success`; if it is false, `errors` says why. HTTP 401 or 403 means a bad
  account ID or token. HTTP 429 means too many requests: wait and retry.

You can ask several questions in one request; each gets its own entry under `answers`.
The answers to one question can shift slightly when other questions are in the same
request.

## Sample code

Python standard library only. It reads the credentials from `cloud-flare.local.sh` and
asks the question above.

```python
import json
import re
import urllib.request

creds = dict(re.findall(r'export (\w+)="([^"]*)"', open("cloud-flare.local.sh").read()))
account = creds["CLOUDFLARE_ACCOUNT_ID"]
token = creds["CLOUDFLARE_API_TOKEN"]
model = "clef-flash"  # or "clef"

payload = {
    "state": {"review": "Delivery took three weeks and the box was crushed, "
                        "but the headphones sound great."},
    "questions": {
        "sentiment": {
            "type": "choice",
            "instructions": "Classify `review`, a customer review of a product bought online.",
            "criteria": {
                "positive": "Mostly happy with the product.",
                "negative": "Mostly unhappy with the product or the purchase.",
                "mixed": "Clearly both happy and unhappy about different things.",
            },
        }
    },
}

request = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}",
    data=json.dumps(payload).encode("utf-8"),
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=60) as response:
    data = json.load(response)

answer = data["result"]["answers"]["sentiment"]
print(answer["choice"], answer["probabilities"], answer["confidence"])
```

For this task, you write the `instructions` and `criteria` for acceptable, toxic and
spam yourself. How well you describe them affects how many mistakes Clef makes.
