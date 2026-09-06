"""
Desk Buddy — a local, Ollama-powered study & emotional-support companion.
Fully offline: the chat model runs on your own machine through Ollama, the
emotion classifier and document parsing run on-device, and nothing is ever
sent to a cloud API.

Run:
    ollama serve                      # in one terminal
    streamlit run app.py              # in another
"""

import os

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

import streamlit as st

import document_utils as docs
import llm_client as llm
import memory as mem
import voice
import timer
from emotion_detector import EmotionEngine, EMOTION_EMOJI
from personas import PERSONAS, DEFAULT_PERSONA, SELECTABLE_PERSONAS, suggest_alternate_persona

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "desk_buddy_memory.json")
HISTORY_TRIM_AT = 24        # rewrite older turns into a rolling summary past this many messages
KEEP_RECENT_MESSAGES = 8    # how many raw turns stay verbatim after a summary rollup
STRESS_THRESHOLD = 0.55     # rolling average stress score that auto-triggers De-escalation
KEEP_ALIVE = "30m"          # keeps the Ollama model resident between messages — no reload lag
N_QUIZ_QUESTIONS = 4
N_FLASHCARDS = 8


@st.cache_resource(show_spinner="Loading emotion model (first run only)...")
def get_emotion_engine() -> EmotionEngine:
    """Loaded once per server process — the DistilRoBERTa model is not cheap to init."""
    return EmotionEngine(window=5)


@st.cache_resource(show_spinner=False)
def warm_model(base_url: str, model: str) -> bool:
    """Runs once per (server, model) combo for this process — loads the model into
    memory now instead of paying that cost on the user's first real message."""
    llm.warm_up(base_url, model, keep_alive=KEEP_ALIVE)
    return True


@st.cache_data(ttl=4, show_spinner=False)
def cached_ollama_status(base_url: str):
    """
    Streamlit reruns the whole script on nearly every interaction — a persona
    switch, a sidebar toggle, typing in the fact box — not just on a new chat
    message. Without caching, that means a network round-trip to Ollama's
    /api/tags on every single one of those, which is the biggest source of
    sluggish-feeling UI that has nothing to do with the model itself. A short
    TTL keeps the status fresh (reconnects show up within ~4s) without
    hammering the endpoint on every rerun.
    """
    return llm.check_ollama_status(base_url)


# ----------------------------------------------------------------------------
# Page setup & styling
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Desk Buddy", page_icon="🦉", layout="wide")

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }

        .block-container { padding-top: 1.6rem; max-width: 1100px; }

        .mode-indicator {
            font-size: 0.85rem; font-weight: 700; letter-spacing: 0.04em;
            text-transform: uppercase; padding: 7px 16px; border-radius: 20px;
            display: inline-block; margin-bottom: 4px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.15);
            animation: fade-badge-in 0.25s ease-out;
        }
        @keyframes fade-badge-in { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: translateY(0); } }

        .mode-casual     { background: linear-gradient(135deg, #ffeaa7, #fdcb6e); color: #7a3e00; }
        .mode-study      { background: linear-gradient(135deg, #dfe6e9, #b2bec3); color: #2d3436; }
        .mode-focus      { background: linear-gradient(135deg, #a29bfe, #6c5ce7); color: #ffffff; }
        .mode-brainstorm { background: linear-gradient(135deg, #ffd6a5, #ff9f43); color: #6b3600; }
        .mode-alert      { background: linear-gradient(135deg, #ff7675, #e84393); color: #ffffff;
                            animation: pulse-alert 1.6s ease-in-out infinite; }
        @keyframes pulse-alert {
            0%, 100% { box-shadow: 0 0 0 0 rgba(255,118,117,0.5); }
            50% { box-shadow: 0 0 0 8px rgba(255,118,117,0); }
        }

        .status-online  { color: #00b894; font-weight: 600; }
        .status-online::before {
            content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
            background: #00b894; margin-right: 6px; animation: pulse-dot 1.8s ease-in-out infinite;
        }
        @keyframes pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        .status-offline { color: #d63031; font-weight: 600; }

        .summary-card {
            background: linear-gradient(155deg, #1e272e, #2d3436); color: #f5f6fa;
            padding: 18px 20px; border-radius: 12px; margin-bottom: 14px; line-height: 1.6;
            box-shadow: 0 4px 14px rgba(0,0,0,0.2);
        }
        .flash-card {
            background: linear-gradient(155deg, #1e272e, #2d3436); color: #f5f6fa;
            padding: 34px 24px; border-radius: 14px; margin: 10px 0 16px 0; min-height: 90px;
            display: flex; align-items: center; justify-content: center;
            text-align: center; font-size: 1.05rem; line-height: 1.5;
            box-shadow: 0 4px 14px rgba(0,0,0,0.22);
            transition: transform 0.15s ease;
        }
        .flash-card:hover { transform: translateY(-2px); }

        .stat-pill {
            display: inline-block; background: linear-gradient(135deg, #f1f2f6, #dfe6e9);
            color: #2d3436; padding: 4px 13px; border-radius: 14px; font-size: 0.8rem;
            margin-right: 6px; margin-bottom: 6px; font-weight: 600;
        }
        .mood-readout { font-size: 0.85rem; opacity: 0.75; margin: -6px 0 10px 0; }

        div[data-testid="stExpander"] { border-radius: 12px; overflow: hidden; }
        section[data-testid="stSidebar"] .stRadio label { font-size: 0.93rem; }
        section[data-testid="stSidebar"] { border-right: 1px solid rgba(0,0,0,0.06); }

        .stButton button, .stChatInput { border-radius: 10px !important; }
        div[data-testid="stChatMessage"] {
            border-radius: 14px; padding: 2px 4px; transition: background 0.15s ease;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Session & persistent state
# ----------------------------------------------------------------------------
if "sessions" not in st.session_state:
    st.session_state.sessions = {}         # persona name -> list[{"role","content","persona"}]
if "doc_text" not in st.session_state:
    st.session_state.doc_text = ""
if "doc_fingerprint" not in st.session_state:
    st.session_state.doc_fingerprint = None
if "study_pack" not in st.session_state:
    st.session_state.study_pack = {}
if "pack_quiz_answered" not in st.session_state:
    st.session_state.pack_quiz_answered = {}
if "generic_quiz" not in st.session_state:
    st.session_state.generic_quiz = []
if "generic_quiz_answered" not in st.session_state:
    st.session_state.generic_quiz_answered = {}
if "flash_idx" not in st.session_state:
    st.session_state.flash_idx = 0
if "flash_show_answer" not in st.session_state:
    st.session_state.flash_show_answer = False
if "memory" not in st.session_state:
    st.session_state.memory = mem.touch_streak(mem.load_memory(MEMORY_PATH))
    mem.save_memory(MEMORY_PATH, st.session_state.memory)
if "showed_support_note" not in st.session_state:
    st.session_state.showed_support_note = False

emotion_engine = get_emotion_engine()

# ----------------------------------------------------------------------------
# Sidebar — persona picker up top, everything else tucked into collapsed
# expanders so the sidebar reads clean at a glance.
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("🦉 Desk Buddy")

    if "persona_radio" not in st.session_state:
        st.session_state.persona_radio = DEFAULT_PERSONA

    active_mode = st.radio(
        "Persona", SELECTABLE_PERSONAS, key="persona_radio",
        format_func=lambda name: PERSONAS[name].get("sidebar_label", name),
    )
    stress_spike = st.toggle("😮‍💨 I'm feeling overwhelmed right now", value=False)

    if active_mode in ("Study Mode", "Deep Focus Mode"):
        with st.expander("⏱️ Pomodoro & stopwatch", expanded=False):
            timer.render_pomodoro_and_stopwatch(work_minutes=25, break_minutes=5, key="deskbuddy_timer")

    st.divider()

    with st.expander("⚙️ Engine (local Ollama)", expanded=False):
        base_url = st.text_input("Ollama endpoint", value="http://localhost:11434/v1")
        is_online, installed_models, err = cached_ollama_status(base_url)

        if is_online:
            st.markdown('<span class="status-online">● Ollama online</span>', unsafe_allow_html=True)
            model_options = installed_models or ["llama3.2:3b"]
        else:
            st.markdown('<span class="status-offline">● Ollama unreachable</span>', unsafe_allow_html=True)
            st.caption(err)
            model_options = ["llama3.2:1b", "llama3.2:3b", "llama3.1:8b"]

        model_name = st.selectbox("Model", model_options, index=0)
        if is_online and not llm.model_is_available(model_name, installed_models):
            st.warning(f"`{model_name}` isn't pulled yet. Run `ollama pull {model_name}`.")
        st.caption("100% local — every request stays on this machine, no cloud API involved.")

    if is_online and llm.model_is_available(model_name, installed_models):
        warm_model(base_url, model_name)  # only actually fires once per model per server run

    with st.expander("🎭 Auto emotion detection", expanded=False):
        if emotion_engine.is_model_backed:
            st.caption("Local DistilRoBERTa emotion classifier — runs fully on-device.")
        else:
            st.caption(emotion_engine.status_message)

        auto_detect = st.toggle("Read my messages' tone automatically", value=True)

        rolling = emotion_engine.rolling_stress()
        st.progress(min(1.0, rolling), text=f"Rolling stress: {rolling:.0%}")

        latest = emotion_engine.latest()
        if latest:
            st.caption(
                f"Last read: {EMOTION_EMOJI.get(latest.dominant, '❔')} "
                f"{latest.dominant} ({latest.scores.get(latest.dominant, 0):.0%})"
            )
        if len(emotion_engine.history) >= 2:
            st.line_chart(emotion_engine.trend_series(), height=100)

    with st.expander("🔊 Voice", expanded=False):
        read_aloud = st.toggle("Read replies aloud", value=False)
        if voice.voice_input_available():
            st.caption("Mic input available (local Whisper — no cloud).")
        else:
            st.caption("Mic input off — `pip install streamlit-mic-recorder faster-whisper` to enable.")

    with st.expander("🧠 Long-term memory", expanded=False):
        m = st.session_state.memory
        if m["facts"]:
            for f in m["facts"]:
                st.caption(f"• {f}")
        else:
            st.caption("No saved facts yet.")
        new_fact = st.text_input("Remember something", placeholder="e.g. I have an exam on Friday")
        if st.button("Save fact", use_container_width=True) and new_fact.strip():
            st.session_state.memory = mem.add_fact(st.session_state.memory, new_fact)
            mem.save_memory(MEMORY_PATH, st.session_state.memory)
            st.rerun()
        if st.button("Clear all memory", use_container_width=True):
            st.session_state.memory = mem.load_memory("__nonexistent__")
            mem.save_memory(MEMORY_PATH, st.session_state.memory)
            st.rerun()

    st.divider()
    stats = st.session_state.memory["stats"]
    st.markdown(
        f'<span class="stat-pill">🔥 {stats["streak_days"]}-day streak</span>'
        f'<span class="stat-pill">💬 {stats["total_messages"]} msgs</span>'
        + (f'<span class="stat-pill">✅ {stats["quiz_correct"]}/{stats["quiz_total"]} quiz</span>'
           if stats["quiz_total"] else ""),
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# Resolve active persona. `active_mode` (from the sidebar) owns the chat
# thread — switching personas opens/returns to that persona's own chat.
# `resolved_persona_name` can temporarily be "De-escalation", which overrides
# voice/behavior for a reply WITHOUT moving the conversation to a new thread.
# ----------------------------------------------------------------------------
def resolve_persona() -> str:
    if stress_spike:
        return "De-escalation"
    if auto_detect and emotion_engine.should_escalate(threshold=STRESS_THRESHOLD):
        return "De-escalation"
    return active_mode


def render_badge(placeholder, name: str):
    p = PERSONAS[name]
    placeholder.markdown(
        f'<span class="mode-indicator {p["badge_class"]}">{p["label"]}'
        + (" · AUTO-DETECTED" if name == "De-escalation" and not stress_spike else "")
        + "</span>",
        unsafe_allow_html=True,
    )


history = st.session_state.sessions.setdefault(active_mode, [])

header_col, clear_col = st.columns([5, 1])
with header_col:
    badge_placeholder = st.empty()
with clear_col:
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.sessions[active_mode] = []
        st.rerun()

resolved_persona_name = resolve_persona()
resolved_persona = PERSONAS[resolved_persona_name]
render_badge(badge_placeholder, resolved_persona_name)


# ----------------------------------------------------------------------------
# Helper: build the outgoing message list (system prompt + memory + history)
# ----------------------------------------------------------------------------
def build_messages(persona: dict, thread: list, extra_context: str = "") -> list:
    system_prompt = persona["system_prompt"]
    ctx = mem.facts_as_context(st.session_state.memory)
    if ctx:
        system_prompt += "\n\n" + ctx
    if extra_context:
        system_prompt += "\n\n" + extra_context
    recent = thread[-KEEP_RECENT_MESSAGES:]
    return [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"]} for m in recent
    ]


def maybe_roll_up_memory(thread_key: str, thread: list) -> None:
    """Once a persona's history gets long, fold the older half into a persistent summary."""
    if len(thread) <= HISTORY_TRIM_AT or not is_online:
        return
    to_summarize = thread[:-KEEP_RECENT_MESSAGES]
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)
    prior = st.session_state.memory.get("long_term_summary", "")
    prompt = (
        "Update this rolling summary of an ongoing conversation with a user, in 2-4 sentences, "
        "keeping only durable facts/preferences/context (not small talk):\n\n"
        f"PRIOR SUMMARY: {prior or '(none yet)'}\n\nNEW MESSAGES:\n{transcript}"
    )
    try:
        new_summary = llm.complete(base_url, model_name, "You write terse factual summaries.",
                                    prompt, max_tokens=150, keep_alive=KEEP_ALIVE)
        st.session_state.memory["long_term_summary"] = new_summary
        st.session_state.sessions[thread_key] = thread[-KEEP_RECENT_MESSAGES:]
        mem.save_memory(MEMORY_PATH, st.session_state.memory)
    except llm.OllamaError:
        pass  # summarization is a nice-to-have; skip silently if the model call fails


def render_message(msg: dict, msg_key: str) -> None:
    role = msg["role"]
    avatar = PERSONAS.get(msg.get("persona", ""), resolved_persona)["avatar"] if role == "assistant" else "🧑"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])
        if role == "assistant" and read_aloud and msg["content"]:
            voice.speak_button(msg["content"], msg_key)


def render_quiz(quiz: list, answered: dict, key_prefix: str) -> None:
    for i, q in enumerate(quiz):
        st.write(f"**Q{i + 1}. {q['q']}**")
        choice = st.radio("Pick one", q["options"], key=f"{key_prefix}_choice_{i}", label_visibility="collapsed")
        if st.button(f"Submit Q{i + 1}", key=f"{key_prefix}_submit_{i}"):
            correct = choice.strip().upper().startswith(q["answer"].strip().upper())
            if answered.get(i) is None:
                st.session_state.memory["stats"]["quiz_total"] += 1
                if correct:
                    st.session_state.memory["stats"]["quiz_correct"] += 1
                answered[i] = correct
                mem.save_memory(MEMORY_PATH, st.session_state.memory)
            st.success("Correct! 🎉") if correct else st.error(f"Not quite — answer was {q['answer']}.")


def render_chat_panel(doc_context: str) -> None:
    if not is_online:
        st.error(
            "**Ollama isn't reachable right now.**\n\n"
            f"{err}\n\n"
            "Once it's running, this banner disappears automatically."
        )

    for i, msg in enumerate(history):
        render_message(msg, f"{active_mode}_{i}")

    mic_text, mic_err = (voice.try_transcribe_mic() if voice.voice_input_available() else (None, None))
    if mic_err:
        st.caption(mic_err)

    typed_prompt = st.chat_input(resolved_persona["placeholder"])
    user_prompt = typed_prompt or mic_text

    if not user_prompt:
        return

    if not is_online:
        st.warning("Can't send that — Ollama is offline. See the message above.")
        st.stop()

    history.append({"role": "user", "content": user_prompt, "persona": active_mode})
    render_message(history[-1], "live_user")

    live_persona_name = resolved_persona_name
    live_persona = resolved_persona

    if auto_detect:
        reading = emotion_engine.analyze(user_prompt)
        st.markdown(
            f'<div class="mood-readout">{EMOTION_EMOJI.get(reading.dominant, "❔")} '
            f'Read as <b>{reading.dominant}</b> ({reading.scores.get(reading.dominant, 0):.0%})</div>',
            unsafe_allow_html=True,
        )
        # Re-resolve now that this message has been scored, so the reply that
        # follows actually reflects the freshly detected tone.
        live_persona_name = resolve_persona()
        live_persona = PERSONAS[live_persona_name]
        render_badge(badge_placeholder, live_persona_name)

        if (live_persona_name == "De-escalation" and not stress_spike
                and emotion_engine.rolling_stress() >= 0.75
                and not st.session_state.showed_support_note):
            st.info(
                "Things sound heavy right now. If it would help, talking to someone you "
                "trust — or a counselor — can make a real difference. I'm still here too."
            )
            st.session_state.showed_support_note = True
        elif emotion_engine.rolling_stress() < 0.4:
            st.session_state.showed_support_note = False

    # Cheap keyword check (no model call) — if this message reads like a much
    # better fit for a different persona, offer a one-tap switch. Skipped
    # while De-escalation is active; that override always takes priority.
    if live_persona_name != "De-escalation":
        suggested = suggest_alternate_persona(user_prompt, active_mode)
        if suggested:
            sug_label = PERSONAS[suggested]["sidebar_label"]
            sug_col, btn_col = st.columns([5, 2])
            with sug_col:
                st.info(f"💡 This sounds like a good fit for **{sug_label}** — want to switch?")
            with btn_col:
                if st.button(f"Switch", use_container_width=True, key="switch_suggestion_btn"):
                    st.session_state.persona_radio = suggested
                    st.rerun()

    with st.chat_message("assistant", avatar=live_persona["avatar"]):
        box = st.empty()
        full_reply = ""
        try:
            for chunk in llm.stream_chat(
                base_url, model_name, build_messages(live_persona, history, doc_context),
                temperature=live_persona.get("temperature", 0.65),
                max_tokens=live_persona.get("max_tokens", 220),
                keep_alive=KEEP_ALIVE,
            ):
                full_reply += chunk
                box.markdown(full_reply + "▌")
            box.markdown(full_reply)
        except llm.OllamaError as e:
            full_reply = ""
            box.error(str(e))

    if full_reply:
        history.append({"role": "assistant", "content": full_reply, "persona": live_persona_name})
        if read_aloud:
            voice.speak_button(full_reply, "live_reply")

        st.session_state.memory["stats"]["total_messages"] += 1
        st.session_state.memory = mem.touch_streak(st.session_state.memory)
        mem.save_memory(MEMORY_PATH, st.session_state.memory)
        maybe_roll_up_memory(active_mode, history)


def render_study_pack_tab() -> None:
    st.subheader("📎 Course material")
    uploaded_file = st.file_uploader("Upload notes or slides", type=["pdf", "pptx", "ppt", "docx", "doc"])

    if uploaded_file:
        fingerprint = docs.file_fingerprint(uploaded_file)
        already_done = fingerprint == st.session_state.doc_fingerprint and st.session_state.study_pack
        if already_done:
            st.caption("✅ Already processed — see the tabs below.")
        elif st.button("⚙️ Build study pack", use_container_width=True):
            if not is_online:
                st.error("Ollama needs to be online to build the study pack. " + (err or ""))
            else:
                try:
                    with st.spinner("Extracting text..."):
                        text = docs.extract_text(uploaded_file)
                    with st.spinner("Building your study pack — summary, overview, keywords, "
                                     "flashcards, and a quiz, in one pass..."):
                        raw = llm.complete(
                            base_url, model_name, "You output only valid JSON, nothing else.",
                            docs.build_study_pack_prompt(text, n_quiz=N_QUIZ_QUESTIONS, n_flashcards=N_FLASHCARDS),
                            max_tokens=1400, keep_alive=KEEP_ALIVE,
                        )
                        pack = docs.parse_study_pack_json(raw)
                    if not pack or not (pack.get("summary") or pack.get("quiz")):
                        st.error("Couldn't parse a study pack from that response — try again, "
                                 "or try a shorter/simpler file.")
                    else:
                        st.session_state.doc_text = text
                        st.session_state.doc_fingerprint = fingerprint
                        st.session_state.study_pack = pack
                        st.session_state.pack_quiz_answered = {}
                        st.session_state.flash_idx = 0
                        st.session_state.flash_show_answer = False
                        st.toast("Study pack ready!", icon="✅")
                        st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except llm.OllamaError as e:
                    st.error(str(e))

    pack = st.session_state.study_pack
    tab_overview, tab_flash, tab_quiz = st.tabs(["🧭 Overview & summary", "🗂️ Flashcards", "❓ Quiz"])

    with tab_overview:
        if pack:
            if pack.get("overview"):
                st.markdown("#### 🧭 Overview")
                st.markdown(f'<div class="summary-card">{pack["overview"]}</div>', unsafe_allow_html=True)
            if pack.get("summary"):
                st.markdown("#### 📝 High-yield summary")
                for b in pack["summary"]:
                    st.markdown(f"- {b}")
            if pack.get("section_pointers"):
                st.markdown("#### 🧷 Section pointers")
                for p in pack["section_pointers"]:
                    st.markdown(f"- {p}")
            if pack.get("keywords"):
                st.markdown("#### 🔑 Key terms")
                st.markdown(
                    " ".join(f'<span class="stat-pill">{k}</span>' for k in pack["keywords"]),
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Upload a file and build a study pack to see your overview here.")

    with tab_flash:
        cards = pack.get("flashcards", [])
        if cards:
            idx = st.session_state.flash_idx % len(cards)
            card = cards[idx]
            st.caption(f"Card {idx + 1} of {len(cards)}")
            face = card["back"] if st.session_state.flash_show_answer else card["front"]
            st.markdown(f'<div class="flash-card">{face}</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if c1.button("⬅️ Prev", use_container_width=True, key="flash_prev"):
                st.session_state.flash_idx = (idx - 1) % len(cards)
                st.session_state.flash_show_answer = False
                st.rerun()
            if c2.button("🔄 Flip", use_container_width=True, key="flash_flip"):
                st.session_state.flash_show_answer = not st.session_state.flash_show_answer
                st.rerun()
            if c3.button("Next ➡️", use_container_width=True, key="flash_next"):
                st.session_state.flash_idx = (idx + 1) % len(cards)
                st.session_state.flash_show_answer = False
                st.rerun()
        else:
            st.caption("Build a study pack to generate flashcards from your material.")

    with tab_quiz:
        quiz_source = st.radio("Quiz source", ["📄 My material", "✍️ Generic topic"], horizontal=True)
        if quiz_source == "📄 My material":
            quiz = pack.get("quiz", [])
            if quiz:
                render_quiz(quiz, st.session_state.pack_quiz_answered, key_prefix="pack")
            else:
                st.caption("Build a study pack to generate a quiz from your material.")
        else:
            topic = st.text_input("Quiz me on...", placeholder="e.g. photosynthesis, WWII causes, Python decorators")
            n = st.slider("Number of questions", 3, 8, N_QUIZ_QUESTIONS, key="generic_quiz_n")
            if st.button("Generate quiz", use_container_width=True, key="generic_quiz_go"):
                if not topic.strip():
                    st.warning("Type a topic first.")
                elif not is_online:
                    st.error("Ollama needs to be online to generate a quiz. " + (err or ""))
                else:
                    with st.spinner("Writing questions..."):
                        try:
                            raw = llm.complete(
                                base_url, model_name, "You output only valid JSON, nothing else.",
                                docs.build_generic_quiz_prompt(topic, n), max_tokens=550, keep_alive=KEEP_ALIVE,
                            )
                            st.session_state.generic_quiz = docs.parse_quiz_json(raw)
                            st.session_state.generic_quiz_answered = {}
                        except llm.OllamaError as e:
                            st.error(str(e))
            if st.session_state.generic_quiz:
                render_quiz(st.session_state.generic_quiz, st.session_state.generic_quiz_answered, key_prefix="generic")
            else:
                st.caption("No upload needed — type any topic above and generate a quiz on the spot.")


# ----------------------------------------------------------------------------
# Layout: Study/Focus modes get an extra Study Pack tab alongside chat
# ----------------------------------------------------------------------------
show_doc_hub = active_mode in ("Study Mode", "Deep Focus Mode")

if show_doc_hub:
    tab_chat, tab_pack = st.tabs(["💬 Chat", "📚 Study Pack"])
    doc_context = (
        f"Uploaded course material (for reference): {st.session_state.doc_text[:1500]}"
        if st.session_state.doc_text else ""
    )
    with tab_chat:
        render_chat_panel(doc_context)
    with tab_pack:
        render_study_pack_tab()
else:
    render_chat_panel("")
