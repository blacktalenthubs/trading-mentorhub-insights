"""Staff SWE Interview Prep Tracker.

Standalone Streamlit app. Run from anywhere:

    python3 -m streamlit run interview_prep/app.py

Progress is stored in interview_prep/progress.json.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import store  # noqa: E402
from curriculum import TRACKS, all_items  # noqa: E402

st.set_page_config(page_title="Staff SWE Prep", page_icon="🎯", layout="wide")

CONFIDENCE = {0: "—", 1: "1 · shaky", 2: "2 · ok", 3: "3 · can teach it"}
PRIORITY_BADGE = {"high": "🔴", "medium": "🟠", "low": "⚪"}

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .item-row { padding: 2px 0; }
    .muted { color: #888; font-size: 0.85rem; }
    code { font-size: 0.82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def data() -> dict:
    if "progress" not in st.session_state:
        st.session_state.progress = store.load()
    return st.session_state.progress


def persist() -> None:
    store.save(data())


def topic_progress(topic: dict) -> tuple[int, int]:
    done = sum(1 for it in topic["items"] if store.is_done(data(), it["id"]))
    return done, len(topic["items"])


def track_progress(track: dict) -> tuple[int, int]:
    done = total = 0
    for topic in track["topics"]:
        d, t = topic_progress(topic)
        done += d
        total += t
    return done, total


def next_open_topic(track: dict) -> dict | None:
    """First topic with unfinished items, high priority first, then curriculum order."""
    order = {"high": 0, "medium": 1, "low": 2}
    candidates = [t for t in track["topics"] if topic_progress(t)[0] < len(t["items"])]
    if not candidates:
        return None
    candidates.sort(key=lambda t: order.get(t["priority"], 9))
    return candidates[0]


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
def render_item(item: dict, key_prefix: str = "") -> None:
    prog = data()
    current = store.get_item(prog, item["id"])
    c0, c1, c2, c3 = st.columns([0.06, 0.52, 0.25, 0.17])
    with c0:
        checked = st.checkbox(
            item["title"],
            value=current["done"],
            key=f"{key_prefix}done_{item['id']}",
            label_visibility="collapsed",
        )
        if checked != current["done"]:
            store.set_done(prog, item["id"], checked)
            persist()
            st.rerun()
    with c1:
        label = f"[{item['title']}]({item['url']})" if item["url"] else item["title"]
        if item.get("tag"):
            label += f"  <span class='muted'>{item['tag']}</span>"
        st.markdown(label, unsafe_allow_html=True)
    with c2:
        conf = st.selectbox(
            "confidence",
            options=list(CONFIDENCE),
            format_func=lambda v: CONFIDENCE[v],
            index=list(CONFIDENCE).index(current["confidence"]),
            key=f"{key_prefix}conf_{item['id']}",
            label_visibility="collapsed",
        )
        if conf != current["confidence"]:
            store.set_confidence(prog, item["id"], conf)
            persist()
    with c3:
        st.markdown(
            f"<span class='muted'>{current['done_at'] or ''}</span>", unsafe_allow_html=True
        )


def render_topic(topic: dict, track_id: str, expanded: bool = False, key_prefix: str = "") -> None:
    done, total = topic_progress(topic)
    badge = PRIORITY_BADGE.get(topic["priority"], "")
    status = "✅" if done == total else f"{done}/{total}"
    with st.expander(f"{badge} {topic['name']}  ·  {status}", expanded=expanded):
        left, right = st.columns([0.5, 0.5])
        with left:
            st.markdown("**Teleprompter**")
            st.markdown(topic["teleprompter"])
        with right:
            st.markdown("**Template / key points**")
            if track_id in ("system_design", "behavioral"):
                st.markdown(topic["template"])
            else:
                st.code(topic["template"], language="python")

        st.markdown("**Definition of done**")
        for item in topic["items"]:
            render_item(item, key_prefix=key_prefix)

        notes_key = f"{track_id}.{topic['id']}.notes"
        current_notes = store.get_item(data(), notes_key)["notes"]
        notes = st.text_area(
            "My notes / story draft",
            value=current_notes,
            key=f"{key_prefix}notes_{notes_key}",
            height=120,
            placeholder="Your own words: the trick you keep forgetting, the STAR draft, the diagram you drew...",
        )
        if notes != current_notes:
            store.set_notes(data(), notes_key, notes)
            persist()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_today() -> None:
    prog = data()
    all_done = sum(1 for it in all_items() if store.is_done(prog, it["id"]))
    total = len(all_items())
    streak = store.streak(prog)
    today = date.today().isoformat()
    done_today = sum(1 for e in prog["log"] if e["date"] == today and e["action"] == "done")

    st.title("🎯 Today")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overall", f"{all_done}/{total}", f"{100 * all_done // max(total, 1)}%")
    m2.metric("Streak", f"{streak} day{'s' if streak != 1 else ''}")
    m3.metric("Done today", done_today)
    m4.metric("Remaining", total - all_done)
    st.progress(all_done / max(total, 1))

    if all_done == total:
        st.success("Everything in the curriculum is done. You are interview-ready. Go rest.")
        return

    st.markdown("### Today's plan")
    st.caption(
        "One topic per track, highest priority first. System design alternates days. "
        "Finish the checks below and the day is done."
    )

    day_index = date.today().toordinal()
    for track_id, track in TRACKS.items():
        if track_id == "system_design" and day_index % 2 == 1:
            # Alternate-day cadence; still show if it is the only thing left.
            others_open = any(
                next_open_topic(t) for tid, t in TRACKS.items() if tid != "system_design"
            )
            if others_open:
                continue
        topic = next_open_topic(track)
        if topic is None:
            continue
        st.markdown(f"#### {track['icon']} {track['name']}  ·  {track['cadence']}")
        render_topic(topic, track_id, expanded=True, key_prefix="today_")


def page_track(track_id: str) -> None:
    track = TRACKS[track_id]
    done, total = track_progress(track)
    st.title(f"{track['icon']} {track['name']}")
    st.caption(track["goal"])
    st.progress(done / max(total, 1), text=f"{done}/{total} checks done · {track['cadence']}")

    show = st.radio(
        "Show", ["Open", "All", "Done"], horizontal=True, label_visibility="collapsed", key=f"filter_{track_id}"
    )
    for topic in track["topics"]:
        d, t = topic_progress(topic)
        if show == "Open" and d == t:
            continue
        if show == "Done" and d != t:
            continue
        render_topic(topic, track_id)


def page_progress() -> None:
    prog = data()
    st.title("📊 Progress")

    rows = []
    for track_id, track in TRACKS.items():
        d, t = track_progress(track)
        conf = [
            store.get_item(prog, it["id"])["confidence"]
            for topic in track["topics"]
            for it in topic["items"]
            if store.is_done(prog, it["id"])
        ]
        avg_conf = sum(conf) / len(conf) if conf else 0.0
        rows.append(
            {
                "Track": f"{track['icon']} {track['name']}",
                "Done": f"{d}/{t}",
                "Percent": round(100 * d / max(t, 1)),
                "Avg confidence": round(avg_conf, 1),
                "Definition of done": track["goal"],
            }
        )
    st.dataframe(rows, hide_index=True)

    st.markdown("### Weak spots (done but confidence ≤ 1)")
    weak = [
        it for it in all_items()
        if store.is_done(prog, it["id"]) and store.get_item(prog, it["id"])["confidence"] <= 1
    ]
    if weak:
        for it in weak:
            st.markdown(f"- **{it['topic_name']}** — {it['title']}")
    else:
        st.caption("None. Nice.")

    st.markdown("### Activity")
    dates = store.done_dates(prog)
    if dates:
        counts = {}
        for e in prog["log"]:
            if e["action"] == "done":
                counts[e["date"]] = counts.get(e["date"], 0) + 1
        st.bar_chart({"completed": counts})
    else:
        st.caption("No activity yet. Check off your first item on the Today page.")

    st.markdown("### Backup")
    st.download_button(
        "Download progress.json",
        data=Path(store.PROGRESS_PATH).read_text() if Path(store.PROGRESS_PATH).exists() else "{}",
        file_name="progress.json",
        mime="application/json",
    )
    if st.button("Reset all progress", type="secondary"):
        st.session_state.confirm_reset = True
    if st.session_state.get("confirm_reset"):
        st.warning("This wipes every check and note.")
        if st.button("Yes, reset everything", type="primary"):
            st.session_state.progress = {"items": {}, "log": []}
            persist()
            st.session_state.confirm_reset = False
            st.rerun()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
NAV = {"Today": None, **{f"{t['icon']} {t['name']}": tid for tid, t in TRACKS.items()}, "📊 Progress": "progress"}

with st.sidebar:
    st.markdown("## Staff SWE Prep")
    all_done = sum(1 for it in all_items() if store.is_done(data(), it["id"]))
    st.progress(all_done / max(len(all_items()), 1), text=f"{all_done}/{len(all_items())} overall")
    choice = st.radio("Go to", list(NAV), label_visibility="collapsed")
    st.markdown("---")
    for tid, track in TRACKS.items():
        d, t = track_progress(track)
        st.markdown(f"<span class='muted'>{track['icon']} {track['name']}: {d}/{t}</span>", unsafe_allow_html=True)

target = NAV[choice]
if target is None:
    page_today()
elif target == "progress":
    page_progress()
else:
    page_track(target)
