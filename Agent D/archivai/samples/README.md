# Sample scans

Drop test scans here (`.png`, `.jpg`, `.pdf`) to exercise the pipeline. Any historical
document images work — Soviet-era Kazakh/Russian archival pages (typed or handwritten)
are the target domain.

Upload them to MinIO (bucket `scans`) via the console at http://localhost:9001 or with
`mc`, then trigger the ingest webhook (see `../n8n/README.md`).

To validate wiring without real models first, set `AI_STUB=1` in `.env`.
