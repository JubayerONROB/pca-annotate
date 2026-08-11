"""Streamlit annotation UI for the Task 1.5 validation sample (DATASET2_SPEC §5).

    streamlit run analysis/annotate_ui.py

One marker per card: the five preceding turns as a transcript, the wearer's next
utterance called out, and the wearer's memory profile as chips. Label 1/0, optionally
add a note, move on.

BLIND BY CONSTRUCTION. This module never reads `dataset2_annotation_key.json` and has
no code path that could -- the proxy labels have to stay hidden for Cohen's kappa to
mean anything. It also never writes to the source sheet: each annotator's work goes to
`dataset2_annotation_sheet_{annotator}.csv`, so several people can label the same 200
markers independently and inter-annotator agreement stays computable.

Every label and note is flushed to disk the moment it changes, via a temp-file rename,
so a crash or a browser refresh costs nothing.
"""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:                                    # deploy repo: modules sit side by side
    from annotation_store import SyncState, store_from_secrets, write_local
except ImportError:                     # thesis repo: analysis/ is a subdirectory
    from analysis.annotation_store import SyncState, store_from_secrets, write_local

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SHEET_NAME = "dataset2_annotation_sheet.csv"
INSTRUCTIONS_NAME = "dataset2_annotation_instructions.md"
OUT_TEMPLATE = "dataset2_annotation_sheet_{annotator}.csv"
# Where annotator CSVs live inside the GitHub repo.
REMOTE_DIR = "annotations"


def _find(name: str) -> Path:
    """Locate a data file in the thesis repo or in the generated deploy repo."""
    for candidate in (REPO_ROOT / "results" / name, REPO_ROOT / "data" / name,
                      HERE / "data" / name, HERE / name, Path("data") / name,
                      Path(name)):
        if candidate.exists():
            return candidate
    return REPO_ROOT / "results" / name


SHEET = _find(SHEET_NAME)
INSTRUCTIONS = _find(INSTRUCTIONS_NAME)
# Streamlit Cloud mounts the repo read-only in some configurations.
OUT_DIR = SHEET.parent if os.access(SHEET.parent, os.W_OK) else Path(".")

LABEL_ONE = "1 · Trigger"
LABEL_ZERO = "0 · Not a trigger"
LABEL_CLEAR = "Clear"
NEXT = "Next ▶"
PREV = "◀ Prev"

_TERM_RE = re.compile(r"^(?P<term>.+?)\((?P<count>\d+)\)$")


# --------------------------------------------------------------------------- io


@st.cache_data(show_spinner=False)
def load_sheet(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str).fillna("")
    for column in ("label", "notes"):
        if column not in frame.columns:
            frame[column] = ""
    return frame


def output_path(annotator: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", annotator).strip("_") or "anonymous"
    return OUT_DIR / OUT_TEMPLATE.format(annotator=safe)


def load_progress(path: Path) -> dict[str, dict[str, str]]:
    """Existing labels keyed by marker_id, so a refresh resumes where you stopped."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["marker_id"]: {"label": row.get("label", ""),
                               "notes": row.get("notes", "")}
            for row in csv.DictReader(handle)
            if row.get("marker_id")
        }


def to_csv_text(frame: pd.DataFrame, annotator: str) -> str:
    out = frame.copy()
    out["annotator"] = annotator
    out["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out.to_csv(index=False, lineterminator="\n")


def save(frame: pd.DataFrame, path: Path, annotator: str,
         store=None, sync: SyncState | None = None) -> None:
    """Write locally, then mirror to GitHub when a token is configured.

    Local first and always: it is the source of truth within a session and does not
    depend on the network. The GitHub write is what survives a Streamlit Cloud
    restart, but a failure there must never cost the annotator their local progress,
    so it is caught and surfaced in the sidebar rather than raised.
    """
    text = to_csv_text(frame, annotator)
    write_local(path, text)
    if store is None or sync is None:
        return
    done = int((frame["label"].astype(str).str.strip() != "").sum())
    try:
        commit = store.write_text(
            f"{REMOTE_DIR}/{path.name}", text,
            f"annotations: {annotator} ({done}/{len(frame)})")
        sync.ok, sync.detail, sync.last_commit = True, "synced to GitHub", commit
    except Exception as exc:                       # noqa: BLE001
        sync.ok = False
        sync.detail = (f"GitHub sync failed ({type(exc).__name__}) -- "
                       "your work is still saved locally")


# ------------------------------------------------------------------------ style


CSS = """
<style>
/* Colours are semi-transparent so the card reads correctly in light and dark. */
.turn { padding:.45rem .7rem; margin:.22rem 0; border-radius:.5rem;
        border:1px solid rgba(128,128,128,.28); line-height:1.45; }
.turn-user  { background:rgba(56,139,253,.16); border-color:rgba(56,139,253,.45); }
.turn-other { background:rgba(128,128,128,.10); }
.who { font-weight:700; opacity:.85; margin-right:.35rem; }
.callout { padding:.85rem 1rem; border-radius:.6rem; margin:.25rem 0 .5rem 0;
           background:rgba(210,153,34,.16); border:2px solid rgba(210,153,34,.65);
           font-size:1.06rem; line-height:1.5; }
.chip { display:inline-block; padding:.16rem .55rem; margin:.14rem .2rem .14rem 0;
        border-radius:1rem; font-size:.84rem;
        background:rgba(63,185,80,.15); border:1px solid rgba(63,185,80,.45); }
.chip b { opacity:.65; font-weight:600; font-size:.78rem; }
.meta { opacity:.7; font-size:.86rem; }
.done { padding:.3rem .6rem; border-radius:.4rem; font-weight:700;
        background:rgba(63,185,80,.18); border:1px solid rgba(63,185,80,.5); }
.todo { padding:.3rem .6rem; border-radius:.4rem; opacity:.75;
        border:1px dashed rgba(128,128,128,.5); }
</style>
"""


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_turns(block: str) -> str:
    if not block.strip():
        return "<div class='meta'>(no preceding turns)</div>"
    html = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        who, _, said = line.partition(":")
        is_user = who.strip() == "User"
        css = "turn turn-user" if is_user else "turn turn-other"
        who_label = "WEARER (User)" if is_user else esc(who.strip())
        html.append(f"<div class='{css}'><span class='who'>{who_label}:</span>"
                    f"{esc(said.strip())}</div>")
    return "".join(html)


def render_chips(block: str) -> str:
    if not block.strip():
        return "<div class='meta'>(no profile terms)</div>"
    chips = []
    for raw in block.split(","):
        raw = raw.strip()
        if not raw:
            continue
        match = _TERM_RE.match(raw)
        term, count = (match.group("term"), match.group("count")) if match else (raw, "")
        chips.append(f"<span class='chip'>{esc(term.strip())}"
                     + (f" <b>×{count}</b>" if count else "") + "</span>")
    return "".join(chips)


def bind_keyboard() -> None:
    """Keyboard shortcuts, by clicking the real buttons.

    Streamlit has no native key bindings, so this listens on the parent document and
    clicks the matching button. It is a convenience layer only -- if the browser blocks
    the bridge, every action is still reachable by mouse.
    """
    components.html(
        """
        <script>
        const doc = window.parent.document;
        if (!doc.__pcaKeysBound) {
            doc.__pcaKeysBound = true;
            const click = (prefix) => {
                for (const b of doc.querySelectorAll('button')) {
                    if ((b.innerText || '').trim().startsWith(prefix)) { b.click(); return true; }
                }
                return false;
            };
            doc.addEventListener('keydown', (e) => {
                const tag = (e.target.tagName || '').toUpperCase();
                const typing = tag === 'TEXTAREA' || tag === 'INPUT' ||
                               e.target.isContentEditable;
                if (typing) return;                    // never hijack the notes box
                let hit = false;
                if (e.key === '1') hit = click('1 ·');
                else if (e.key === '0') hit = click('0 ·');
                else if (e.key === 'ArrowRight' || e.key === 'Enter') hit = click('Next');
                else if (e.key === 'ArrowLeft') hit = click('◀');
                if (hit) e.preventDefault();
            });
        }
        </script>
        """,
        height=0,
    )


# ------------------------------------------------------------------------- app


def main() -> None:
    st.set_page_config(page_title="DATASET2 annotation", page_icon="🏷️",
                       layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    if not SHEET.exists():
        st.error(f"Annotation sheet not found: `{SHEET}`\n\n"
                 "Generate it first:\n\n"
                 "```\npython analysis/build_annotation_sheet.py\n```")
        st.stop()

    # ---- annotator gate ---------------------------------------------------
    if "annotator" not in st.session_state:
        st.title("🏷️ DATASET2 — marker annotation")
        st.caption("Task 1.5 · validating the behavioural proxy against human judgement")
        st.write("Enter an annotator ID. Your work is saved under this name, so several "
                 "people can label the same 200 markers independently.")
        who = st.text_input("Annotator ID", placeholder="e.g. Annotator_1, or your name")
        if st.button("Start labeling", type="primary", disabled=not who.strip()):
            st.session_state.annotator = who.strip()
            st.rerun()
        st.stop()

    annotator = st.session_state.annotator
    out_path = output_path(annotator)

    # ---- durable store ----------------------------------------------------
    if "store" not in st.session_state:
        st.session_state.store = store_from_secrets(st.secrets)
        st.session_state.sync = SyncState(
            enabled=st.session_state.store is not None,
            detail="synced to GitHub" if st.session_state.store else
                   "local only -- no GitHub token configured")
    store = st.session_state.store
    sync: SyncState = st.session_state.sync

    # ---- load + resume ----------------------------------------------------
    if "frame" not in st.session_state:
        frame = load_sheet(str(SHEET)).copy()
        saved = load_progress(out_path)
        if store is not None and not saved:
            # Cold container on Streamlit Cloud: local disk is empty but the repo
            # remembers. Without this, a restart silently restarts the annotator too.
            try:
                remote = store.read_text(f"{REMOTE_DIR}/{out_path.name}")
                if remote:
                    write_local(out_path, remote)
                    saved = load_progress(out_path)
                    sync.detail = f"restored {len(saved)} labels from GitHub"
            except Exception as exc:                    # noqa: BLE001
                sync.ok = False
                sync.detail = f"could not read GitHub ({type(exc).__name__})"
        for i, marker_id in enumerate(frame["marker_id"]):
            if marker_id in saved:
                frame.at[i, "label"] = saved[marker_id]["label"]
                frame.at[i, "notes"] = saved[marker_id]["notes"]
        st.session_state.frame = frame
        unlabeled = frame.index[frame["label"].astype(str).str.strip() == ""]
        st.session_state.idx = int(unlabeled[0]) if len(unlabeled) else 0

    frame: pd.DataFrame = st.session_state.frame
    total = len(frame)
    idx = int(st.session_state.idx) % total
    row = frame.iloc[idx]

    labeled_mask = frame["label"].astype(str).str.strip() != ""
    n_done = int(labeled_mask.sum())
    n_one = int((frame["label"].astype(str).str.strip() == "1").sum())
    n_zero = int((frame["label"].astype(str).str.strip() == "0").sum())

    def persist() -> None:
        save(st.session_state.frame, out_path, annotator, store, sync)

    def set_label(value: str) -> None:
        st.session_state.frame.at[idx, "label"] = value
        persist()
        if value and st.session_state.get("auto_advance", True) and idx < total - 1:
            st.session_state.idx = idx + 1

    def save_notes() -> None:
        st.session_state.frame.at[idx, "notes"] = st.session_state.get(
            f"notes_{idx}", "")
        persist()

    # ---- sidebar ----------------------------------------------------------
    with st.sidebar:
        st.subheader(f"👤 {annotator}")
        st.progress(n_done / total, text=f"{n_done} / {total} labeled "
                                         f"({n_done / total:.0%})")
        col_a, col_b = st.columns(2)
        col_a.metric("Label 1", n_one)
        col_b.metric("Label 0", n_zero)
        if n_done:
            st.caption(f"Your split so far: {n_one / n_done:.0%} trigger / "
                       f"{n_zero / n_done:.0%} non-trigger")
            st.caption("Don't aim for 50/50 — label each card on its merits. "
                       "A skew is itself a finding.")

        st.divider()
        st.checkbox("Auto-advance after labeling", value=True, key="auto_advance")
        jump = st.number_input("Jump to card", min_value=1, max_value=total,
                               value=idx + 1, step=1)
        if int(jump) - 1 != idx:
            st.session_state.idx = int(jump) - 1
            st.rerun()
        if st.button("Go to first unlabeled"):
            remaining = frame.index[frame["label"].astype(str).str.strip() == ""]
            if len(remaining):
                st.session_state.idx = int(remaining[0])
                st.rerun()
            else:
                st.success("Everything is labeled.")

        st.divider()
        if sync.enabled:
            if sync.ok:
                st.success(f"☁ {sync.detail}"
                           + (f" · `{sync.last_commit}`" if sync.last_commit else ""))
            else:
                st.error(f"⚠ {sync.detail}")
            if st.button("Sync now", use_container_width=True):
                persist()
                st.rerun()
        else:
            st.warning("☁ Not syncing to GitHub. Your work is saved on this machine "
                       "only -- download your CSV before closing the tab.")

        st.caption("Saved to")
        st.code(str(out_path.relative_to(REPO_ROOT)), language=None)
        st.download_button("⬇ Download my CSV",
                           data=out_path.read_bytes() if out_path.exists()
                           else frame.to_csv(index=False).encode("utf-8"),
                           file_name=out_path.name, mime="text/csv")
        st.caption("⌨ 1 · 0 · ← → · Enter")

    # ---- header -----------------------------------------------------------
    st.markdown(f"### Card {idx + 1} / {total}")
    st.progress((idx + 1) / total)
    st.markdown(
        f"<div class='meta'>marker <code>{esc(row['marker_id'])}</code> · "
        f"wearer <b>{esc(row['wearer'])}</b> · meeting <b>{esc(row['meeting_id'])}</b> "
        f"· split {esc(row['split'])}</div>",
        unsafe_allow_html=True)

    with st.expander("📖 Labeling rules (read me first)", expanded=n_done == 0):
        if INSTRUCTIONS.exists():
            st.markdown(INSTRUCTIONS.read_text(encoding="utf-8"))
        else:
            st.info(f"Instructions file not found at {INSTRUCTIONS}")

    st.divider()
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### Preceding turns")
        st.markdown(render_turns(row["preceding_turns"]), unsafe_allow_html=True)
        st.markdown("#### 🤫 …silence here — would a 1–3 word hint have helped?")
        st.markdown("#### Wearer's next utterance")
        st.markdown(f"<div class='callout'>{esc(row['wearer_next_utterance'])}</div>",
                    unsafe_allow_html=True)

    with right:
        st.markdown("#### Wearer's memory profile")
        st.caption("Their most frequent terms from EARLIER meetings, with counts. "
                   "Same view for every card — it does not indicate the answer.")
        st.markdown(render_chips(row["wearer_profile_terms"]), unsafe_allow_html=True)

    st.divider()

    # ---- controls ---------------------------------------------------------
    current = str(row["label"]).strip()
    c1, c2, c3, c4, c5 = st.columns([1.3, 1.6, 1, 1, 1])
    if c1.button(LABEL_ONE, type="primary" if current != "1" else "secondary",
                 use_container_width=True):
        set_label("1")
        st.rerun()
    if c2.button(LABEL_ZERO, type="primary" if current != "0" else "secondary",
                 use_container_width=True):
        set_label("0")
        st.rerun()
    if c3.button(LABEL_CLEAR, use_container_width=True, disabled=current == ""):
        set_label("")
        st.rerun()
    if c4.button(PREV, use_container_width=True, disabled=idx == 0):
        st.session_state.idx = max(0, idx - 1)
        st.rerun()
    if c5.button(NEXT, use_container_width=True, disabled=idx >= total - 1):
        st.session_state.idx = min(total - 1, idx + 1)
        st.rerun()

    st.markdown(
        f"<span class='{'done' if current else 'todo'}'>"
        f"{'Your label: ' + current if current else 'not labeled yet'}</span>",
        unsafe_allow_html=True)

    st.text_area("Notes (borderline cases — these drive the disagreement analysis)",
                 value=str(row["notes"]), key=f"notes_{idx}", on_change=save_notes,
                 height=90, placeholder="e.g. mentioned two turns earlier; "
                                        "or: retrieves something, but the useful hint "
                                        "would be a different phrase")

    # ---- completion -------------------------------------------------------
    if n_done == total:
        st.success(f"All {total} cards labeled — {n_one} trigger, {n_zero} non-trigger "
                   f"({n_one / total:.0%} / {n_zero / total:.0%}).")
        st.markdown(
            "Hand the CSV back, or score it directly:\n\n"
            f"```\npython analysis/compute_kappa.py "
            f"--sheet {out_path.relative_to(REPO_ROOT).as_posix()}\n```")
    elif n_done:
        st.caption(f"{total - n_done} cards left.")

    bind_keyboard()


if __name__ == "__main__":
    main()
