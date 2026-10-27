# YOUR_AGENT_NAME — your Answer Agent

This is a tiny AI agent: one page with a question box, plus a small server that
answers using the **Lightchain AIVM** and pays per answer. It costs nothing while
nobody is asking — one question, one paid answer (about **0.02 LCAI** each).

You don't need to understand the code. Follow the five steps below.

## What's in this folder

- `index.html` — the page people see (a question box and the answer).
- `server.py` — the small server that answers and pays per question.
- `aivm_client.py` — the Lightchain connection (handles paying for each answer).
- `requirements.txt`, `Procfile` — tell the host how to run it.
- `manifest.json`, icons — make it installable like an app.

## Deploy it (about 10 minutes)

1. **Make a new GitHub repo** and upload every file in this folder to it.
2. Go to **railway.app**, create a new project, and choose **Deploy from GitHub repo** → pick your repo.
3. In Railway, open **Variables** and add one variable:
   - `LIGHTCHAIN_PRIVATE_KEY` = the private key of the wallet that will pay for answers.
   - Keep a little LCAI in that wallet. Each answer costs about 0.02 LCAI.
4. Railway gives you a public link (something like `your-agent.up.railway.app`). That's your live agent — share it.
5. Open the link, type a question, and get an answer.

Your private key lives only in Railway's Variables. It is never on the page and
was never saved into this download.

## Make it yours (optional)

All optional, set in Railway → Variables:

- `AGENT_SYSTEM` — one line describing your agent's job or personality
  (e.g. "You are a helpful Lightchain support agent. Answer briefly.").
- `DAILY_LCAI_CAP` — most LCAI it may spend in a day (default 25). A safety brake.
- `RATE_PER_MIN` / `RATE_PER_DAY` — how many questions one visitor can ask (defaults 4 / 40).

## Run it on your own computer first (optional)

```
pip install -r requirements.txt
LIGHTCHAIN_PRIVATE_KEY=your_key python3 server.py
```

Then open `http://localhost:8000`.
