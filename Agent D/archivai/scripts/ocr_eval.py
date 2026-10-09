#!/usr/bin/env python3
"""OCR quality benchmark: CER/WER of the running AI service vs ground truth.

Setup:  put page images + verified transcriptions into samples/eval/:
          samples/eval/doc1.png        (the scan)
          samples/eval/doc1.gt.txt     (its correct text, human-verified)
Run:    python3 scripts/ocr_eval.py            (AI service must be up, AI_STUB=0)
        AI_URL=http://localhost:8000 python3 scripts/ocr_eval.py

Use it to MEASURE every OCR change (preprocessing flags, wordlist, models):
run, flip a flag in .env, force-recreate ai-service, run again, compare means.
No third-party deps (stdlib urllib; Levenshtein implemented here).
"""
import base64
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(ROOT, "samples", "eval")
AI_URL = os.environ.get("AI_URL", "http://localhost:8000").rstrip("/")
IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm(s):
    return " ".join(s.split())


def cer(hyp, ref):
    ref_n, hyp_n = norm(ref), norm(hyp)
    return levenshtein(hyp_n, ref_n) / max(len(ref_n), 1)


def wer(hyp, ref):
    ref_w, hyp_w = norm(ref).split(), norm(hyp).split()
    return levenshtein(hyp_w, ref_w) / max(len(ref_w), 1)


def ocr_page(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    req = urllib.request.Request(
        AI_URL + "/ocr",
        data=json.dumps({"pages": [{"image_b64": b64}]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=1800) as r:
        data = json.loads(r.read())
    page = (data.get("pages") or [{}])[0]
    return page.get("text", ""), page.get("confidence"), data.get("backend")


def main():
    if not os.path.isdir(EVAL_DIR):
        print(f"no eval set: create {EVAL_DIR} with <name>.png + <name>.gt.txt pairs")
        sys.exit(1)
    pairs = []
    for fn in sorted(os.listdir(EVAL_DIR)):
        base_name, ext = os.path.splitext(fn)
        if ext.lower() in IMG_EXT:
            gt = os.path.join(EVAL_DIR, base_name + ".gt.txt")
            if os.path.exists(gt):
                pairs.append((os.path.join(EVAL_DIR, fn), gt))
    if not pairs:
        print(f"no <image>+<name>.gt.txt pairs found in {EVAL_DIR}")
        sys.exit(1)

    # capture the service's current OCR config for the report header
    # (waits for boot: `docker compose up -d` returns before uvicorn is ready)
    import time
    health = None
    last_err = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(AI_URL + "/health", timeout=5) as r:
                health = json.loads(r.read())
            break
        except Exception as e:
            last_err = e
            time.sleep(2)
    if health is None:
        print(f"AI service unreachable at {AI_URL} after 60s: {last_err}")
        sys.exit(1)
    if health.get("stub"):
        print("AI service is in STUB mode — set AI_STUB=0 for a real benchmark.")
        sys.exit(1)
    print(f"backend={health.get('ocr_backend')}  ({len(pairs)} page(s))\n")

    cers, wers = [], []
    print(f"{'page':<32} {'CER':>7} {'WER':>7} {'conf':>6}")
    for img, gt in pairs:
        ref = open(gt, encoding="utf-8").read()
        try:
            hyp, conf, _ = ocr_page(img)
        except Exception as e:
            print(f"{os.path.basename(img):<32} FAILED: {e}")
            continue
        c, w = cer(hyp, ref), wer(hyp, ref)
        cers.append(c)
        wers.append(w)
        print(f"{os.path.basename(img):<32} {c:>7.3f} {w:>7.3f} "
              f"{conf if conf is not None else '—':>6}")
    if cers:
        print("-" * 55)
        print(f"{'MEAN':<32} {sum(cers)/len(cers):>7.3f} {sum(wers)/len(wers):>7.3f}")
        print("\nLower is better. Re-run after each OCR config change to compare.")


if __name__ == "__main__":
    main()
