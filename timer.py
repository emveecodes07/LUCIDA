"""
timer.py
Pomodoro-style work/break timer + a simple stopwatch, rendered for Study Mode
and Deep Focus Mode.

Deliberately built as ONE self-contained client-side widget (vanilla JS,
via components.html) rather than driven from Python/session_state. A
Streamlit rerun happens on basically every widget interaction in this app
(persona switch, chat message, sidebar toggle) — a Python-driven countdown
would either reset constantly or need a st.rerun() polling loop, which is
both janky and adds real server load. Counting time is a client-side problem;
this keeps it off the Python hot path entirely, same pattern as voice.py's
read-aloud button.

Trade-off: the timer's visible state doesn't survive a full page reload
(no cloud sync, nothing written to disk) — acceptable for a session-scoped
study aid, and consistent with the rest of the app's "nothing persists
unless it's explicitly memory" design.
"""

import streamlit.components.v1 as components


def render_pomodoro_and_stopwatch(work_minutes: int = 25, break_minutes: int = 5, key: str = "timer") -> None:
    components.html(
        f"""
        <div style="font-family: 'Inter', 'Segoe UI', sans-serif; color: #f5f6fa;">
          <style>
            #{key}-wrap {{
              background: linear-gradient(155deg, #1e272e 0%, #2d3436 100%);
              border-radius: 14px; padding: 16px 18px; margin-bottom: 6px;
              box-shadow: 0 4px 14px rgba(0,0,0,0.25);
            }}
            .{key}-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
            .{key}-label {{ font-size: 0.72rem; letter-spacing: .06em; text-transform: uppercase; opacity: 0.65; }}
            .{key}-time {{ font-size: 1.9rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
            .{key}-phase-work {{ color: #74b9ff; }}
            .{key}-phase-break {{ color: #55efc4; }}
            .{key}-btns button {{
              background: #3d4852; color: #f5f6fa; border: none; border-radius: 8px;
              padding: 5px 11px; margin-left: 6px; font-size: 0.78rem; cursor: pointer;
              transition: background .15s ease, transform .1s ease;
            }}
            .{key}-btns button:hover {{ background: #57636e; transform: translateY(-1px); }}
            .{key}-btns button:active {{ transform: translateY(0); }}
            .{key}-mini {{ font-size: 0.72rem; opacity: 0.6; margin-top: 2px; }}
            .{key}-divider {{ border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0; }}
          </style>

          <div id="{key}-wrap">
            <div class="{key}-row">
              <div>
                <div class="{key}-label" id="{key}-phase-label">🍅 Pomodoro — Work</div>
                <div class="{key}-time {key}-phase-work" id="{key}-pomo-time">{work_minutes:02d}:00</div>
                <div class="{key}-mini" id="{key}-pomo-cycles">0 sessions completed</div>
              </div>
              <div class="{key}-btns">
                <button onclick="{key}_pomoToggle()" id="{key}-pomo-btn">Start</button>
                <button onclick="{key}_pomoReset()">Reset</button>
              </div>
            </div>
            <div class="{key}-row" style="margin-bottom:0; font-size:0.75rem; opacity:0.7;">
              Work
              <input type="number" id="{key}-work-input" value="{work_minutes}" min="1" max="90"
                     style="width:44px; margin:0 6px; background:#3d4852; color:#f5f6fa; border:none; border-radius:5px; padding:2px 4px;">
              min &nbsp;·&nbsp; Break
              <input type="number" id="{key}-break-input" value="{break_minutes}" min="1" max="60"
                     style="width:44px; margin:0 6px; background:#3d4852; color:#f5f6fa; border:none; border-radius:5px; padding:2px 4px;">
              min
              <button onclick="{key}_applySettings()" style="background:#3d4852; color:#f5f6fa; border:none; border-radius:8px; padding:3px 10px; margin-left:6px; font-size:0.72rem; cursor:pointer;">Apply</button>
            </div>

            <div class="{key}-divider"></div>

            <div class="{key}-row" style="margin-bottom:0;">
              <div>
                <div class="{key}-label">⏱️ Study Stopwatch</div>
                <div class="{key}-time" style="color:#ffeaa7;" id="{key}-sw-time">00:00:00</div>
              </div>
              <div class="{key}-btns">
                <button onclick="{key}_swToggle()" id="{key}-sw-btn">Start</button>
                <button onclick="{key}_swReset()">Reset</button>
              </div>
            </div>
          </div>
        </div>

        <script>
          // ---- Pomodoro ----
          let {key}_workSec = {work_minutes} * 60;
          let {key}_breakSec = {break_minutes} * 60;
          let {key}_remaining = {key}_workSec;
          let {key}_onBreak = false;
          let {key}_running = false;
          let {key}_cycles = 0;
          let {key}_interval = null;

          function {key}_beep() {{
            try {{
              const ctx = new (window.AudioContext || window.webkitAudioContext)();
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.connect(gain); gain.connect(ctx.destination);
              osc.frequency.value = 880;
              gain.gain.setValueAtTime(0.15, ctx.currentTime);
              osc.start();
              osc.stop(ctx.currentTime + 0.35);
            }} catch (e) {{}}
          }}

          function {key}_fmt(totalSec) {{
            const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
            const s = Math.floor(totalSec % 60).toString().padStart(2, '0');
            return m + ':' + s;
          }}

          function {key}_renderPomo() {{
            document.getElementById('{key}-pomo-time').textContent = {key}_fmt({key}_remaining);
            const timeEl = document.getElementById('{key}-pomo-time');
            const labelEl = document.getElementById('{key}-phase-label');
            timeEl.className = '{key}-time ' + ({key}_onBreak ? '{key}-phase-break' : '{key}-phase-work');
            labelEl.textContent = {key}_onBreak ? '☕ Pomodoro — Break' : '🍅 Pomodoro — Work';
            document.getElementById('{key}-pomo-cycles').textContent = {key}_cycles + ' session' + ({key}_cycles === 1 ? '' : 's') + ' completed';
            document.getElementById('{key}-pomo-btn').textContent = {key}_running ? 'Pause' : 'Start';
          }}

          function {key}_pomoTick() {{
            {key}_remaining -= 1;
            if ({key}_remaining <= 0) {{
              {key}_beep();
              if (!{key}_onBreak) {{ {key}_cycles += 1; }}
              {key}_onBreak = !{key}_onBreak;
              {key}_remaining = {key}_onBreak ? {key}_breakSec : {key}_workSec;
            }}
            {key}_renderPomo();
          }}

          function {key}_pomoToggle() {{
            {key}_running = !{key}_running;
            if ({key}_running) {{
              {key}_interval = setInterval({key}_pomoTick, 1000);
            }} else {{
              clearInterval({key}_interval);
            }}
            {key}_renderPomo();
          }}

          function {key}_pomoReset() {{
            clearInterval({key}_interval);
            {key}_running = false;
            {key}_onBreak = false;
            {key}_remaining = {key}_workSec;
            {key}_renderPomo();
          }}

          function {key}_applySettings() {{
            const w = parseInt(document.getElementById('{key}-work-input').value, 10);
            const b = parseInt(document.getElementById('{key}-break-input').value, 10);
            {key}_workSec = (isNaN(w) || w < 1 ? {work_minutes} : w) * 60;
            {key}_breakSec = (isNaN(b) || b < 1 ? {break_minutes} : b) * 60;
            {key}_pomoReset();
          }}

          {key}_renderPomo();

          // ---- Stopwatch ----
          let {key}_swElapsed = 0;
          let {key}_swRunning = false;
          let {key}_swInterval = null;

          function {key}_swFmt(totalSec) {{
            const h = Math.floor(totalSec / 3600).toString().padStart(2, '0');
            const m = Math.floor((totalSec % 3600) / 60).toString().padStart(2, '0');
            const s = Math.floor(totalSec % 60).toString().padStart(2, '0');
            return h + ':' + m + ':' + s;
          }}

          function {key}_swRender() {{
            document.getElementById('{key}-sw-time').textContent = {key}_swFmt({key}_swElapsed);
            document.getElementById('{key}-sw-btn').textContent = {key}_swRunning ? 'Pause' : 'Start';
          }}

          function {key}_swToggle() {{
            {key}_swRunning = !{key}_swRunning;
            if ({key}_swRunning) {{
              {key}_swInterval = setInterval(() => {{ {key}_swElapsed += 1; {key}_swRender(); }}, 1000);
            }} else {{
              clearInterval({key}_swInterval);
            }}
            {key}_swRender();
          }}

          function {key}_swReset() {{
            clearInterval({key}_swInterval);
            {key}_swRunning = false;
            {key}_swElapsed = 0;
            {key}_swRender();
          }}

          {key}_swRender();
        </script>
        """,
        height=250,
    )
