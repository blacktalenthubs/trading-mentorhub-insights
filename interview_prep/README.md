# Staff SWE Interview Prep Tracker

A self-contained daily study app. Nothing here depends on the trading platform;
the folder can be copied anywhere and run on its own.

## Run

```bash
pip install streamlit          # only dependency
python3 -m streamlit run interview_prep/app.py
```

Open http://localhost:8501. Progress is saved to `interview_prep/progress.json`
on every click, so you can close the tab and come back tomorrow. Commit that file
if you want your progress on another machine.

## What "done" means

`curriculum.py` is the whole definition of done. Six tracks, 61 topics, 203 checks:

| Track | Done when | Cadence |
|-------|-----------|---------|
| Coding Patterns | 17 patterns × 3 LeetCode problems each | 1 pattern / day |
| Python Fluency | 8 course modules × 3 prove-it checks | 1 module / day |
| OOP | 6 pillars × 3 checks (includes the course exercises) | 1 pillar / day |
| Design Patterns | 10 patterns × implement + explain + map to real work | 1 pattern / day |
| System Design | 10 systems × your 5-step template | 1 system / 2 days |
| Behavioral | 10 STAR stories × write + rehearse + follow-ups | 1 story / day |

At one topic per track per day the whole plan is roughly three weeks.
High-priority topics are served first on the Today page.

## Pages

- **Today**: one open topic per track, highest priority first, with its teleprompter,
  code template, and checkboxes. Finish the checks and the day is done.
- **Track pages**: every topic in that track, filter Open / All / Done.
- **Progress**: per-track completion, average confidence, weak spots
  (done but confidence 1), activity chart, JSON backup, reset.

## Editing the curriculum

Everything lives in `curriculum.py`. Each topic has:

```python
{
  "id": "sliding_window",          # stable; progress keys on it
  "name": "Sliding Window",
  "priority": "high",              # high / medium / low
  "teleprompter": "...",           # what you say out loud, 2-3 short paragraphs
  "template": "...",               # code snippet or key points
  "items": [...]                   # the checks; 3 per topic by convention
}
```

Add a problem, a pattern, or a whole track and the app picks it up on refresh.
Renaming an `id` orphans its saved progress, so prefer adding over renaming.
