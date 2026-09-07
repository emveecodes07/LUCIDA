"""
timer.py
Pomodoro-style work/break timer + a stopwatch with laps, rendered for Study
Mode and Deep Focus Mode.

Deliberately built as ONE self-contained client-side widget (vanilla JS, via
components.html) rather than driven from Python/session_state. A Streamlit
rerun happens on basically every widget interaction in this app (persona
switch, chat message, sidebar toggle) — a Python-driven countdown would
either reset constantly or need a st.rerun() polling loop, which is both
janky and adds real server load. Counting time is a client-side problem;
this keeps it off the Python hot path entirely, same pattern as voice.py's
read-aloud button — so none of the extra interactivity below (progress ring,
notifications, tab-title countdown, laps) costs a single additional Streamlit
rerun or model call.

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
              border-radius: 16px; padding: 18px 20px; margin-bottom: 6px;
              box-shadow: 0 6px 18px rgba(0,0,0,0.28);
            }}
            .{key}-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
            .{key}-label {{ font-size: 0.72rem; letter-spacing: .06em; text-transform: uppercase; opacity: 0.65; }}
            .{key}-time {{ font-size: 1.75rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
            .{key}-phase-work {{ color: #74b9ff; }}
            .{key}-phase-break {{ color: #55efc4; }}
            .{key}-btns button {{
              background: #3d4852; color: #f5f6fa; border: none; border-radius: 8px;
              padding: 5px 11px; margin-left: 6px; font-size: 0.76rem; cursor: pointer;
              transition: background .15s ease, transform .1s ease;
            }}
            .{key}-btns button.{key}-primary {{ background: #6c5ce7; }}
            .{key}-btns button:hover {{ background: #57636e; transform: translateY(-1px); }}
            .{key}-btns button.{key}-primary:hover {{ background: #8073ee; }}
            .{key}-btns button:active {{ transform: translateY(0); }}
            .{key}-mini {{ font-size: 0.72rem; opacity: 0.6; margin-top: 2px; }}
            .{key}-divider {{ border-top: 1px solid rgba(255,255,255,0.08); margin: 14px 0; }}
            .{key}-ring-wrap {{ position: relative; width: 78px; height: 78px; flex-shrink: 0; }}
            .{key}-ring {{
              width: 78px; height: 78px; border-radius: 50%;
              background: conic-gradient(#74b9ff 0deg, #3d4852 0deg);
              display: flex; align-items: center; justify-content: center;
              transition: background 0.9s linear;
            }}
            .{key}-ring-inner {{
              width: 62px; height: 62px; border-radius: 50%; background: #1e272e;
              display: flex; align-items: center; justify-content: center;
              font-size: 0.68rem; font-weight: 700; opacity: 0.85;
            }}
            .{key}-dots {{ display: flex; gap: 4px; margin-top: 5px; }}
            .{key}-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #3d4852; }}
            .{key}-dot.filled {{ background: #74b9ff; }}
            .{key}-laps {{ max-height: 90px; overflow-y: auto; margin-top: 8px; font-size: 0.72rem; opacity: 0.75; }}
            .{key}-laps div {{ display: flex; justify-content: space-between; padding: 2px 0; }}
            .{key}-target-input {{
              width: 34px; background:#3d4852; color:#f5f6fa; border:none; border-radius:5px; padding:2px 4px;
            }}
          </style>

          <div id="{key}-wrap">
            <div class="{key}-row">
              <div style="display:flex; align-items:center; gap:14px;">
                <div class="{key}-ring-wrap">
                  <div class="{key}-ring" id="{key}-ring">
                    <div class="{key}-ring-inner" id="{key}-ring-label">WORK</div>
                  </div>
                </div>
                <div>
                  <div class="{key}-label" id="{key}-phase-label">🍅 Pomodoro — Work</div>
                  <div class="{key}-time {key}-phase-work" id="{key}-pomo-time">{work_minutes:02d}:00</div>
                  <div class="{key}-dots" id="{key}-dots"></div>
                </div>
              </div>
              <div class="{key}-btns" style="align-self:flex-start;">
                <button class="{key}-primary" onclick="{key}_pomoToggle()" id="{key}-pomo-btn">Start</button>
                <button onclick="{key}_pomoSkip()">Skip</button>
                <button onclick="{key}_pomoReset()">Reset</button>
              </div>
            </div>

            <div class="{key}-row" style="margin-bottom:0; font-size:0.75rem; opacity:0.7; flex-wrap: wrap; gap: 4px;">
              <span>
                Work <input type="number" id="{key}-work-input" value="{work_minutes}" min="1" max="90" class="{key}-target-input">m
                &nbsp;·&nbsp; Break <input type="number" id="{key}-break-input" value="{break_minutes}" min="1" max="60" class="{key}-target-input">m
                &nbsp;·&nbsp; Target <input type="number" id="{key}-goal-input" value="4" min="1" max="12" class="{key}-target-input"> sessions
              </span>
              <button onclick="{key}_applySettings()" style="background:#3d4852; color:#f5f6fa; border:none; border-radius:8px; padding:3px 10px; font-size:0.72rem; cursor:pointer;">Apply</button>
            </div>
            <div class="{key}-row" style="margin-bottom:0; margin-top:4px;">
              <label style="font-size:0.72rem; opacity:0.7; cursor:pointer;">
                <input type="checkbox" id="{key}-autocontinue" checked style="vertical-align:middle; margin-right:5px;">
                Auto-continue to next phase
              </label>
              <label style="font-size:0.72rem; opacity:0.7; cursor:pointer;">
                <input type="checkbox" id="{key}-notify" style="vertical-align:middle; margin-right:5px;" onchange="{key}_toggleNotify(this)">
                Desktop notification
              </label>
            </div>

            <div class="{key}-divider"></div>

            <div class="{key}-row" style="margin-bottom:4px;">
              <div>
                <div class="{key}-label">⏱️ Study Stopwatch</div>
                <div class="{key}-time" style="color:#ffeaa7;" id="{key}-sw-time">00:00:00</div>
              </div>
              <div class="{key}-btns">
                <button class="{key}-primary" onclick="{key}_swToggle()" id="{key}-sw-btn">Start</button>
                <button onclick="{key}_swLap()">Lap</button>
                <button onclick="{key}_swReset()">Reset</button>
              </div>
            </div>
            <div class="{key}-laps" id="{key}-laps"></div>
          </div>
        </div>

        <script>
          const {key}_origTitle = (window.parent && window.parent.document) ? window.parent.document.title : document.title;
          let {key}_notifyOn = false;

          function {key}_setParentTitle(t) {{
            try {{ window.parent.document.title = t; }} catch (e) {{}}
          }}
          function {key}_restoreParentTitle() {{
            try {{ window.parent.document.title = {key}_origTitle; }} catch (e) {{}}
          }}

          function {key}_toggleNotify(cb) {{
            {key}_notifyOn = cb.checked;
            if (cb.checked && "Notification" in window && Notification.permission === "default") {{
              Notification.requestPermission();
            }}
          }}
          function {key}_notify(title, body) {{
            if ({key}_notifyOn && "Notification" in window && Notification.permission === "granted") {{
              try {{ new Notification(title, {{ body: body }}); }} catch (e) {{}}
            }}
          }}

          // ---- Pomodoro ----
          let {key}_workSec = {work_minutes} * 60;
          let {key}_breakSec = {break_minutes} * 60;
          let {key}_remaining = {key}_workSec;
          let {key}_onBreak = false;
          let {key}_running = false;
          let {key}_cycles = 0;
          let {key}_goal = 4;
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

          function {key}_renderDots() {{
            const wrap = document.getElementById('{key}-dots');
            wrap.innerHTML = '';
            for (let i = 0; i < {key}_goal; i++) {{
              const d = document.createElement('div');
              d.className = '{key}-dot' + (i < {key}_cycles ? ' filled' : '');
              wrap.appendChild(d);
            }}
          }}

          function {key}_renderPomo() {{
            document.getElementById('{key}-pomo-time').textContent = {key}_fmt({key}_remaining);
            const timeEl = document.getElementById('{key}-pomo-time');
            const labelEl = document.getElementById('{key}-phase-label');
            const ringLabelEl = document.getElementById('{key}-ring-label');
            const ringEl = document.getElementById('{key}-ring');
            timeEl.className = '{key}-time ' + ({key}_onBreak ? '{key}-phase-break' : '{key}-phase-work');
            labelEl.textContent = {key}_onBreak ? '☕ Pomodoro — Break' : '🍅 Pomodoro — Work';
            ringLabelEl.textContent = {key}_onBreak ? 'BREAK' : 'WORK';

            const total = {key}_onBreak ? {key}_breakSec : {key}_workSec;
            const pct = total > 0 ? (1 - {key}_remaining / total) * 360 : 0;
            const ringColor = {key}_onBreak ? '#55efc4' : '#74b9ff';
            ringEl.style.background = 'conic-gradient(' + ringColor + ' ' + pct + 'deg, #3d4852 ' + pct + 'deg)';

            document.getElementById('{key}-pomo-btn').textContent = {key}_running ? 'Pause' : 'Start';
            {key}_renderDots();

            if ({key}_running) {{
              {key}_setParentTitle(({key}_onBreak ? '☕ ' : '🍅 ') + {key}_fmt({key}_remaining) + ' · LUCIDA');
            }}
          }}

          function {key}_advancePhase() {{
            {key}_beep();
            const finishedWork = !{key}_onBreak;
            if (finishedWork) {{
              {key}_cycles += 1;
              {key}_notify('Work session done 🍅', 'Time for a ' + ({key}_breakSec/60) + '-minute break.');
            }} else {{
              {key}_notify("Break's over ☕", 'Back to a ' + ({key}_workSec/60) + '-minute work block.');
            }}
            {key}_onBreak = !{key}_onBreak;
            {key}_remaining = {key}_onBreak ? {key}_breakSec : {key}_workSec;
            const autoContinue = document.getElementById('{key}-autocontinue').checked;
            if (!autoContinue) {{
              {key}_running = false;
              clearInterval({key}_interval);
              {key}_restoreParentTitle();
            }}
          }}

          function {key}_pomoTick() {{
            {key}_remaining -= 1;
            if ({key}_remaining <= 0) {{
              {key}_advancePhase();
            }}
            {key}_renderPomo();
          }}

          function {key}_pomoToggle() {{
            {key}_running = !{key}_running;
            if ({key}_running) {{
              {key}_interval = setInterval({key}_pomoTick, 1000);
            }} else {{
              clearInterval({key}_interval);
              {key}_restoreParentTitle();
            }}
            {key}_renderPomo();
          }}

          function {key}_pomoSkip() {{
            clearInterval({key}_interval);
            {key}_remaining = 1;
            {key}_pomoTick();
            if ({key}_running) {{ {key}_interval = setInterval({key}_pomoTick, 1000); }}
          }}

          function {key}_pomoReset() {{
            clearInterval({key}_interval);
            {key}_running = false;
            {key}_onBreak = false;
            {key}_cycles = 0;
            {key}_remaining = {key}_workSec;
            {key}_restoreParentTitle();
            {key}_renderPomo();
          }}

          function {key}_applySettings() {{
            const w = parseInt(document.getElementById('{key}-work-input').value, 10);
            const b = parseInt(document.getElementById('{key}-break-input').value, 10);
            const g = parseInt(document.getElementById('{key}-goal-input').value, 10);
            {key}_workSec = (isNaN(w) || w < 1 ? {work_minutes} : w) * 60;
            {key}_breakSec = (isNaN(b) || b < 1 ? {break_minutes} : b) * 60;
            {key}_goal = (isNaN(g) || g < 1 ? 4 : g);
            {key}_pomoReset();
          }}

          {key}_goal = 4;
          {key}_renderPomo();

          // ---- Stopwatch ----
          let {key}_swElapsed = 0;
          let {key}_swRunning = false;
          let {key}_swInterval = null;
          let {key}_swLaps = [];

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

          function {key}_swRenderLaps() {{
            const wrap = document.getElementById('{key}-laps');
            wrap.innerHTML = '';
            for (let i = {key}_swLaps.length - 1; i >= 0; i--) {{
              const row = document.createElement('div');
              row.innerHTML = '<span>Lap ' + (i + 1) + '</span><span>' + {key}_swFmt({key}_swLaps[i]) + '</span>';
              wrap.appendChild(row);
            }}
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

          function {key}_swLap() {{
            if (!{key}_swRunning) return;
            {key}_swLaps.push({key}_swElapsed);
            {key}_swRenderLaps();
          }}

          function {key}_swReset() {{
            clearInterval({key}_swInterval);
            {key}_swRunning = false;
            {key}_swElapsed = 0;
            {key}_swLaps = [];
            {key}_swRender();
            {key}_swRenderLaps();
          }}

          {key}_swRender();
        </script>
        """,
        height=340,
    )
