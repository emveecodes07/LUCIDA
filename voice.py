"""
voice.py
Optional, fully local "read aloud" support using the browser's built-in
speechSynthesis API — no external TTS service, no API key, works offline.

Speech-to-text (mic input) is opt-in and only activates if the optional
`streamlit-mic-recorder` + `faster-whisper` packages are installed, so the
base app never breaks if they're missing — it just tells you what to install.
"""

import os
import tempfile
import warnings

import streamlit.components.v1 as components

# The optional faster-whisper/ctranslate2 stack prints a noisy (harmless)
# pkg_resources deprecation warning on import — silence just that one so it
# doesn't clutter the terminal every time the sidebar checks availability.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")


def speak_button(text: str, key: str):
    """Renders a small 'read aloud' button next to a chat message."""
    safe_text = text.replace("\\", "\\\\").replace("`", "\\`").replace("\n", " ")
    components.html(
        f"""
        <button id="speak-{key}" style="
            background:none;border:none;cursor:pointer;font-size:14px;
            opacity:0.55;padding:2px 6px;" title="Read aloud">🔊</button>
        <script>
            document.getElementById("speak-{key}").onclick = function() {{
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance(`{safe_text}`);
                window.speechSynthesis.speak(utter);
            }};
        </script>
        """,
        height=28,
    )


def voice_input_available() -> bool:
    try:
        import streamlit_mic_recorder  # noqa: F401
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def try_transcribe_mic():
    """
    Returns (text, error). Both may be None if nothing was recorded yet.
    Never raises — degrades gracefully so a missing optional dependency
    can't crash the rest of the app.
    """
    try:
        from streamlit_mic_recorder import mic_recorder
        from faster_whisper import WhisperModel
    except ImportError:
        return None, (
            "Voice input needs two extra packages: "
            "`pip install streamlit-mic-recorder faster-whisper`"
        )

    audio = mic_recorder(start_prompt="🎙️ Speak", stop_prompt="⏹ Stop", key="mic_recorder")
    if not audio:
        return None, None

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio["bytes"])
            path = f.name
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(path)
        text = " ".join(seg.text for seg in segments).strip()
        return (text or None), None
    except Exception as e:
        return None, f"Transcription failed: {e}"
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
