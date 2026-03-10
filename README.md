# LinkedIn Profile Optimizer

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

App runs at `http://127.0.0.1:5000`.

## Where to add Gemini API

Use `analyze_profile()` in `app.py` as the integration point.  
Current flow is heuristic-based placeholder logic.

Recommended pattern:

1. Read `GEMINI_API_KEY` from environment.
2. Send `headline/about/experience/skills` prompt to Gemini.
3. Merge Gemini output into:
   - `optimized.headline`
   - `optimized.about`
   - `optimized.experience`
   - `improvement_suggestions`

## Where to add PostgreSQL

Replace session-based placeholder auth/history in:

- `login()` route
- `dashboard()`/`history()` data loading
- `analyzer()` history save block

Suggested environment variable: `DATABASE_URL`.
