from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import webbrowser

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>K5D</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;600;700;800&display=swap');
        * { box-sizing: border-box; }
        body { font-family: 'Syne', sans-serif; background: #020205; }
        #canvas-container {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 1;
            background: #000000;
        }
        /* Scanline overlay */
        #canvas-container::after {
            content: '';
            position: absolute; inset: 0;
            background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px);
            pointer-events: none; z-index: 2;
        }
        .ui-overlay { position: absolute; z-index: 10; pointer-events: none; }
        .ui-overlay > * { pointer-events: auto; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        select { appearance: none; -webkit-appearance: none; }

        /* Panel glass style */
        .hud-panel {
            background: rgba(8,8,14,0.88);
            border: 1px solid rgba(59,130,246,0.18);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            box-shadow: 0 0 0 1px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04), 0 4px 32px rgba(0,0,0,0.6);
        }
        /* Corner bracket decoration */
        .bracket::before, .bracket::after {
            content: '';
            position: absolute;
            width: 10px; height: 10px;
            border-color: rgba(59,130,246,0.5);
            border-style: solid;
        }
        .bracket::before { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
        .bracket::after  { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

        /* Blinking cursor */
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .blink { animation: blink 1.1s step-end infinite; }

        /* Scan sweep */
        @keyframes sweep { 0%{top:-4px} 100%{top:100%} }
        #scan-sweep {
            position: fixed; left: 0; right: 0; height: 3px; z-index: 9;
            background: linear-gradient(180deg, transparent 0%, rgba(59,130,246,0.18) 50%, transparent 100%);
            pointer-events: none;
            animation: sweep 6s linear infinite;
        }


        /* Pulse ring */
        @keyframes pulse-ring { 0%{transform:scale(0.8);opacity:0.8} 100%{transform:scale(2.2);opacity:0} }
        .pulse-ring {
            position: absolute; inset: -4px;
            border: 1px solid #22c55e;
            border-radius: 50%;
            animation: pulse-ring 1.8s ease-out infinite;
        }

        /* Value counter animation */
        @keyframes flicker { 0%,100%{opacity:1} 92%{opacity:1} 93%{opacity:0.7} 94%{opacity:1} }
        .flicker { animation: flicker 4s ease-in-out infinite; }

        /* Dial */
        .dial-track { stroke: rgba(59,130,246,0.15); }
        .dial-fill  { stroke: #3b82f6; stroke-linecap: round; transition: stroke-dashoffset 0.5s ease; }

        /* Minimap grid */
        .minimap-cell { width:3px; height:3px; background:rgba(59,130,246,0.08); border-radius:0.5px; }
        .minimap-cell.active { background:rgba(59,130,246,0.55); }
        .minimap-cell.obj { background:#f59e0b; }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(59,130,246,0.3); border-radius: 2px; }

        /* Warning flash */
        @keyframes warn { 0%,100%{border-color:rgba(251,191,36,0.3)} 50%{border-color:rgba(251,191,36,0.8)} }
        .warn-border { animation: warn 1.4s ease-in-out infinite; }

        /* Welcome modal */
        #welcome-overlay {
            position: fixed; inset: 0; z-index: 999999;
            background: rgba(0,0,0,0.65);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            display: flex; align-items: center; justify-content: center;
        }
        #welcome-box {
            background: rgba(12,12,22,0.72);
            border: 1px solid rgba(99,130,246,0.28);
            backdrop-filter: blur(32px) saturate(180%);
            -webkit-backdrop-filter: blur(32px) saturate(180%);
            box-shadow: 0 0 0 1px rgba(0,0,0,0.4), 0 8px 64px rgba(59,130,246,0.18), inset 0 1px 0 rgba(255,255,255,0.07);
            border-radius: 24px;
            padding: 40px 44px 36px;
            max-width: 560px;
            width: calc(100% - 40px);
            position: relative;
        }
        #welcome-box .wm-badge {
            display: inline-flex; align-items: center; gap: 6px;
            background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.3);
            border-radius: 999px; padding: 3px 12px;
            font-size: 11px; font-family: 'JetBrains Mono', monospace;
            color: #60a5fa; letter-spacing: 0.08em; margin-bottom: 18px;
        }
        #welcome-box h1 {
            font-size: 1.6rem; font-weight: 800; line-height: 1.25;
            background: linear-gradient(135deg, #e2e8ff 0%, #93b4fd 55%, #60a5fa 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        #welcome-box .wm-sub {
            font-size: 0.85rem; color: rgba(180,190,255,0.72); line-height: 1.6;
            margin-bottom: 22px;
        }
        #welcome-box .wm-divider {
            height: 1px; background: rgba(99,130,246,0.18); margin-bottom: 18px;
        }
        #welcome-box .wm-how-title {
            font-size: 0.7rem; font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.12em; color: #60a5fa; margin-bottom: 12px;
        }
        #welcome-box ul {
            list-style: none; padding: 0; margin: 0 0 28px;
            display: flex; flex-direction: column; gap: 9px;
        }
        #welcome-box ul li {
            font-size: 0.82rem; color: rgba(210,220,255,0.8);
            display: flex; align-items: flex-start; gap: 10px; line-height: 1.5;
        }
        #welcome-box ul li::before {
            content: '›'; color: #3b82f6; font-size: 1rem; flex-shrink: 0; margin-top: -1px;
        }
        #welcome-box .wm-footer {
            display: flex; align-items: center; justify-content: space-between; gap: 16px;
        }

        #welcome-close-btn {
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            color: #fff; border: none; cursor: pointer;
            font-family: 'Syne', sans-serif; font-weight: 700;
            font-size: 0.82rem; letter-spacing: 0.04em;
            padding: 10px 24px; border-radius: 10px;
            box-shadow: 0 4px 20px rgba(59,130,246,0.35);
            transition: transform 0.15s, box-shadow 0.15s;
        }
        #welcome-close-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 28px rgba(59,130,246,0.5); }

        /* Light mode overrides */
        body.light-mode { background: #f0f4ff !important; color: #1e1e2e !important; }
        body.light-mode #canvas-container { background: #dce3f7 !important; }
        body.light-mode .hud-panel { background: rgba(240,244,255,0.88) !important; border-color: rgba(59,130,246,0.25) !important; }
        body.light-mode #welcome-box { background: rgba(235,240,255,0.85) !important; }
        body.light-mode #welcome-box h1 { background: linear-gradient(135deg, #1e2060 0%, #2563eb 100%); -webkit-background-clip: text; background-clip: text; }
        body.light-mode #welcome-box .wm-sub { color: rgba(30,40,100,0.65); }
        body.light-mode #welcome-box ul li { color: rgba(20,30,80,0.85); }
        body.light-mode #welcome-box .wm-theme-row { color: rgba(30,40,100,0.6); }
        #context-menu {
            position: fixed;
            z-index: 9999;
            background: #18181b;
            border: 1px solid #3f3f46;
            border-radius: 12px;
            padding: 6px;
            min-width: 160px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.6);
            display: none;
            pointer-events: auto;
        }
        #context-menu button {
            display: flex;
            align-items: center;
            gap: 8px;
            width: 100%;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
            font-family: 'Syne', sans-serif;
            font-weight: 600;
            background: transparent;
            border: none;
            cursor: pointer;
            color: #d4d4d8;
            transition: background 0.15s;
        }
        #context-menu button:hover { background: #27272a; }
        #context-menu button.danger { color: #f87171; }
        #context-menu button.danger:hover { background: #3f1a1a; }
        #context-menu hr { border-color: #3f3f46; margin: 4px 0; }
        #rename-modal {
            position: fixed;
            inset: 0;
            z-index: 99999;
            background: rgba(0,0,0,0.7);
            display: none;
            align-items: center;
            justify-content: center;
        }
        #rename-modal.active { display: flex; }
        #rename-modal .modal-box {
            background: #18181b;
            border: 1px solid #3f3f46;
            border-radius: 16px;
            padding: 24px;
            width: 320px;
        }
        #rename-modal input {
            width: 100%;
            background: #27272a;
            border: 1px solid #3f3f46;
            border-radius: 8px;
            padding: 10px 14px;
            color: #fff;
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            outline: none;
            margin: 12px 0;
        }
        #rename-modal input:focus { border-color: #3b82f6; }
        .lib-section-title {
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.1em;
            color: #71717a;
            text-transform: uppercase;
            padding: 6px 0 4px 0;
        }
        .lib-divider { border-color: #27272a; margin: 6px 0; }
        .obj-lib-entry {
            display: flex;
            flex-direction: column;
            align-items: center;
            cursor: pointer;
            transition: transform 0.15s;
        }
        .obj-lib-entry:hover { transform: scale(1.13); }
        .obj-lib-meta {
            position: absolute;
            left: 100%;
            top: 0;
            margin-left: 8px;
            background: #18181b;
            border: 1px solid #3f3f46;
            border-radius: 10px;
            padding: 8px 12px;
            min-width: 220px;
            font-size: 11px;
            color: #a1a1aa;
            display: none;
            z-index: 100;
            pointer-events: none;
        }
        .obj-lib-entry:hover .obj-lib-meta { display: block; }
        .obj-lib-wrap { position: relative; }
        .cmd-log-entry {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            padding: 3px 6px;
            border-radius: 4px;
            margin-bottom: 2px;
        }
        .cmd-pending { color: #71717a; }
        .cmd-active { color: #fbbf24; background: rgba(251,191,36,0.1); }
        .cmd-done { color: #4ade80; }
        .cmd-error { color: #f87171; }
        #stl-drop-zone {
            border: 2px dashed #3f3f46;
            border-radius: 12px;
            padding: 12px;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.2s, background 0.2s;
        }
        #stl-drop-zone:hover, #stl-drop-zone.drag-over {
            border-color: #3b82f6;
            background: rgba(59,130,246,0.06);
        }
        #stl-progress {
            display: none;
            margin-top: 8px;
        }
        #stl-progress-bar-wrap {
            width: 100%;
            background: #27272a;
            border-radius: 999px;
            height: 4px;
            overflow: hidden;
            margin-top: 4px;
        }
        #stl-progress-bar {
            height: 4px;
            background: #3b82f6;
            border-radius: 999px;
            width: 0%;
            transition: width 0.2s;
        }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-200 overflow-hidden light-mode">

<!-- ═══ WELCOME MODAL ═══ -->
<div id="welcome-overlay">
  <div id="welcome-box">
    <div class="wm-badge">&#9679; PROBLABS ROBOTICS &nbsp;·&nbsp; K5D HOS</div>
    <h1>Welcome to K5D HOS Simulator</h1>
    <p class="wm-sub">The world's most advanced LLM-powered robotic simulator surpassing even the most cutting-edge systems from tech giants like Google, Tesla, and beyond! Officially tested!</p>
    <div class="wm-divider"></div>
    <div class="wm-how-title">HOW TO USE</div>
    <ul>
      <li>Give detailed, descriptive prompts to the AI for richer and more accurate output.</li>
      <li>Right-click any object in the scene to rename or delete it.</li>
      <li>Import custom 3D objects using a <span style="font-family:'JetBrains Mono',monospace;color:#60a5fa">.stl</span> file via the Import button.</li>
      <li>Use the object library on the left to select, move, rotate, and scale parts.</li>
      <li>Chain multiple AI tasks in sequence for complex multi-step assembly.</li>
      <li>Import any supported 3D model format using the Import .stl file button.</li>
      <li>Approve/edit LLM's high level plan just by a single click</li>
      <li>Find example super-difficult super-multi-step tasks on the top-left corner</li>
      <li>Use the camera controls (scroll, drag, right-drag) to navigate the 3D scene freely.</li>
    </ul>
    <div class="wm-footer">
      <button id="welcome-close-btn" onclick="launchWithSplash()">Launch Simulator &nbsp;›</button>
    </div>
  </div>
</div>

<!-- Splash screen -->
<div id="splash-overlay" style="display:none;position:fixed;inset:0;z-index:1000000;background:rgba(2,2,5,0.97);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);align-items:center;justify-content:center;flex-direction:column;">
  <div style="width:380px;max-width:calc(100% - 48px);display:flex;flex-direction:column;align-items:center;gap:28px;">
    <div style="display:flex;flex-direction:column;align-items:center;gap:8px;">
      <div style="width:48px;height:48px;background:linear-gradient(135deg,#1d4ed8,#4f46e5);border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:22px;color:#fff;letter-spacing:-1px;">K5</div>
      <div style="font-size:0.75rem;font-family:'JetBrains Mono',monospace;color:rgba(148,163,220,0.7);letter-spacing:0.12em;" id="splash-status-text">Initializing simulator…</div>
    </div>
    <div style="width:100%;display:flex;flex-direction:column;gap:10px;">
      <div style="width:100%;height:3px;background:rgba(59,130,246,0.12);border-radius:2px;overflow:hidden;">
        <div id="splash-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#2563eb,#60a5fa);border-radius:2px;transition:width 0.12s linear;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:0.68rem;font-family:'JetBrains Mono',monospace;color:rgba(148,163,220,0.45);">K5D Drone Simulator</div>
        <div id="splash-pct" style="font-size:0.68rem;font-family:'JetBrains Mono',monospace;color:rgba(148,163,220,0.55);">0%</div>
      </div>
    </div>
  </div>
</div>

<!-- Scan sweep line -->
<div id="scan-sweep"></div>

<!-- ═══ TOP HUD BAR ═══ -->
<div class="ui-overlay top-0 left-0 right-0" style="background:rgba(4,4,10,0.96);border-bottom:1px solid rgba(59,130,246,0.2);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);z-index:20;">
    <!-- Main header row -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 20px;">
        <!-- Left: branding + live axis readout -->
        <div style="display:flex;align-items:center;gap:16px;">
            <div style="position:relative;width:38px;height:38px;flex-shrink:0;">
                <div style="width:38px;height:38px;background:linear-gradient(135deg,#1d4ed8,#4f46e5);border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:17px;color:#fff;letter-spacing:-1px;">K5</div>
                <div class="pulse-ring" style="border-color:#3b82f6;animation-duration:2.4s;"></div>
            </div>
            <div>
                <div style="font-size:14px;font-weight:800;letter-spacing:-0.02em;color:#f4f4f5;">K5D <span style="color:rgba(59,130,246,0.7);font-weight:400;">·</span> Precision Cartesian Gantry</div>
                <div class="mono" style="font-size:9px;color:#3f3f46;letter-spacing:0.08em;margin-top:1px;">PROLABS V12.2 &nbsp;·&nbsp; AI-CONTROLLED &nbsp;·&nbsp; 20×11 GRID &nbsp;·&nbsp; 3-AXIS &nbsp;·&nbsp; SN:PL-K5D-00A1</div>
            </div>
            <!-- Axis position pills -->
            <div style="display:flex;gap:6px;margin-left:8px;">
                <div class="mono" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.25);border-radius:6px;padding:4px 10px;">
                    <span style="font-size:8px;color:#52525b;display:block;letter-spacing:0.1em;">X-AXIS</span>
                    <span id="hud-x" style="font-size:13px;color:#60a5fa;font-weight:700;">A</span>
                </div>
                <div class="mono" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.25);border-radius:6px;padding:4px 10px;">
                    <span style="font-size:8px;color:#52525b;display:block;letter-spacing:0.1em;">Y-AXIS</span>
                    <span id="hud-y" style="font-size:13px;color:#60a5fa;font-weight:700;">1</span>
                </div>
                <div class="mono" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.25);border-radius:6px;padding:4px 10px;">
                    <span style="font-size:8px;color:#52525b;display:block;letter-spacing:0.1em;">Z-AXIS</span>
                    <span id="hud-z" style="font-size:13px;color:#60a5fa;font-weight:700;">4.0</span>
                </div>
                <div class="mono" style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.2);border-radius:6px;padding:4px 10px;">
                    <span style="font-size:8px;color:#52525b;display:block;letter-spacing:0.1em;">GRIPPER</span>
                    <span id="hud-grip" style="font-size:11px;color:#34d399;font-weight:700;">OPEN</span>
                </div>
                <div class="mono" style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.18);border-radius:6px;padding:4px 10px;">
                    <span style="font-size:8px;color:#52525b;display:block;letter-spacing:0.1em;">OBJECTS</span>
                    <span id="hud-obj-count" style="font-size:13px;color:#94a3b8;font-weight:700;">0</span>
                </div>
            </div>
        </div>

        <!-- Center: main status + live clock -->
        <div style="display:flex;flex-direction:column;align-items:center;gap:4px;">
            <div id="status" style="padding:5px 16px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);color:#34d399;border-radius:20px;font-size:10px;font-family:'JetBrains Mono',monospace;font-weight:700;display:flex;align-items:center;gap:6px;letter-spacing:0.08em;">
                <span style="position:relative;width:6px;height:6px;flex-shrink:0;display:flex;">
                    <span style="position:absolute;inset:0;background:#22c55e;border-radius:50%;animation:pulse-ring 1.4s ease-out infinite;transform:scale(0.8);opacity:0.8;"></span>
                    <span style="width:6px;height:6px;background:#22c55e;border-radius:50%;position:relative;z-index:1;"></span>
                </span>
                READY
            </div>
            <div class="mono" id="live-clock" style="font-size:9px;color:#3f3f46;letter-spacing:0.12em;"></div>
        </div>

        <!-- Right: action buttons -->
        <div style="display:flex;align-items:center;gap:8px;">
            <button onclick="takeTopDownScreenshot()" style="padding:7px 14px;background:rgba(109,40,217,0.3);border:1px solid rgba(139,92,246,0.4);border-radius:8px;color:#c4b5fd;font-family:'Syne',sans-serif;font-size:11px;font-weight:700;cursor:pointer;letter-spacing:0.03em;transition:all 0.15s;" onmouseover="this.style.background='rgba(109,40,217,0.5)'" onmouseout="this.style.background='rgba(109,40,217,0.3)'">
                📸 SCREENSHOT
            </button>
            <button onclick="copyFullPrompt()" style="padding:7px 14px;background:rgba(39,39,42,0.8);border:1px solid rgba(63,63,70,0.8);border-radius:8px;color:#a1a1aa;font-family:'Syne',sans-serif;font-size:11px;font-weight:700;cursor:pointer;letter-spacing:0.03em;transition:all 0.15s;" onmouseover="this.style.background='rgba(63,63,70,0.8)'" onmouseout="this.style.background='rgba(39,39,42,0.8)'">
                📋 COPY PROMPT
            </button>
            <button onclick="resetToHome()" style="padding:7px 14px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);border-radius:8px;color:#fca5a5;font-family:'Syne',sans-serif;font-size:11px;font-weight:700;cursor:pointer;letter-spacing:0.03em;transition:all 0.15s;" onmouseover="this.style.background='rgba(239,68,68,0.25)'" onmouseout="this.style.background='rgba(239,68,68,0.12)'">
                ⌂ RESET HOME
            </button>
            <!-- System health indicators -->
            <div style="display:flex;flex-direction:column;gap:3px;margin-left:6px;padding-left:12px;border-left:1px solid rgba(59,130,246,0.12);">
                <div style="display:flex;align-items:center;gap:5px;">
                    <span style="width:5px;height:5px;background:#22c55e;border-radius:50%;"></span>
                    <span class="mono" style="font-size:8px;color:#3f3f46;letter-spacing:0.06em;">MOTOR</span>
                </div>
                <div style="display:flex;align-items:center;gap:5px;">
                    <span style="width:5px;height:5px;background:#22c55e;border-radius:50%;"></span>
                    <span class="mono" style="font-size:8px;color:#3f3f46;letter-spacing:0.06em;">COMMS</span>
                </div>
                <div style="display:flex;align-items:center;gap:5px;">
                    <span id="ai-dot" style="width:5px;height:5px;background:#3f3f46;border-radius:50%;"></span>
                    <span class="mono" style="font-size:8px;color:#3f3f46;letter-spacing:0.06em;">AI&nbsp;PLNR</span>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- ═══ BOTTOM STATUS BAR ═══ -->
<div class="ui-overlay bottom-0 left-0 right-0" style="background:rgba(4,4,10,0.95);border-top:1px solid rgba(59,130,246,0.15);padding:5px 20px;display:flex;align-items:center;justify-content:space-between;backdrop-filter:blur(16px);">
    <div style="display:flex;gap:20px;align-items:center;">
        <span class="mono" style="font-size:9px;color:#27272a;letter-spacing:0.06em;">K5D CONTROL SYSTEM</span>
        <span class="mono" style="font-size:9px;color:rgba(59,130,246,0.4);">FW v12.2.1-stable</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:#27272a;" id="bottom-pos">POS: A1 · Z:4.0</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:#27272a;">VEL: 0.0 mm/s</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:#27272a;">TORQUE: 0.00 Nm</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:rgba(251,191,36,0.5);" id="bottom-uptime">UPTIME: 00:00:00</span>
    </div>
    <div style="display:flex;gap:16px;align-items:center;">
        <span class="mono" style="font-size:9px;color:#27272a;">CELL SIZE: 50×50mm</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:#27272a;">GRID: 20×11</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:#27272a;">MAX LIFT: 8kg</span>
        <span class="mono" style="font-size:9px;color:#27272a;">·</span>
        <span class="mono" style="font-size:9px;color:rgba(59,130,246,0.4);">© PROLABS 2025</span>
    </div>
</div>
    <div id="canvas-container"></div>
    <!-- Hidden elements used by JS animations (not shown in UI) -->
    <div style="display:none">
        <select id="x-letter"></select>
        <select id="y-number"></select>
        <input type="range" id="z-slider" min="0.5" max="7" step="0.1" value="4.0">
        <span id="z-label">4.0</span>
        <div id="current-position">A1</div>
        <div id="current-coords">(0.0, 0.0, 4.0)</div>
        <div id="gripper-state">Gripper: OPEN</div>
    </div>

    <!-- Task List Panel — scrollable, height capped so it doesn't overlap the bottom library panel -->
    <div class="ui-overlay top-20 left-6 bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl w-64" style="max-height: calc(48vh - 10px); display:flex; flex-direction:column;">
        <div class="px-4 pt-4 pb-2 shrink-0">
            <h2 class="text-xs font-bold mb-0.5 text-zinc-300 tracking-widest uppercase">Quick Tasks</h2>
            <p class="text-xs text-zinc-600 mono">Click a task to run with K5D AI</p>
        </div>
        <div class="overflow-y-auto px-4 pb-4" style="scrollbar-width:thin; scrollbar-color:#3f3f46 transparent;">
            <div class="space-y-1.5 pt-1">
                <button onclick="showTaskPopup('Sweeping','Sweep the entire floor of the board clean. Use the broom to sweep all cells and collect dust with the dustpan.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F9F9;</span> Sweeping
                </button>
                <button onclick="showTaskPopup('Mopping','Mop the entire floor of the board. Fill the bucket with water and disinfectant, then mop all cells row by row.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1FAA3;</span> Mopping
                </button>
                <button onclick="showTaskPopup('Washing utensils','Wash all dirty utensils on the board. Apply soap to each utensil cell, then wipe clean with a cloth. Work through every dirty pot, pan, plate, bowl, mug, glass, and cutlery using Apply_soap and Apply_cloth commands.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F37D;&#xFE0F;</span> Washing utensils
                </button>
                <button onclick="showTaskPopup('Cooking','Cook a meal. Follow this exact sequence with no extra steps: 1) Pick up the pot and place it on the stove cell. 2) Turn on the stove. 3) Pick up the vegetable(s) if present, if no vegitables then keep vegitable basket on the pot (same cell as stove). 4) Move gripper to A1. 5) Wait 4 seconds using wait_for(4). 6) Pick up the vegetable basket from the pot and place it on the plate. 7) Turn off the stove. Do not use a knife, cutting board, or any other objects.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F373;</span> Cooking
                </button>
                <button onclick="showTaskPopup('Washing clothes','Wash all dirty clothes on the board. Load garments into the washing machine with detergent, run the wash cycle, then unload clean clothes.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F455;</span> Washing clothes
                </button>
                <button onclick="showTaskPopup('Folding and ironing clothes','Iron and fold all wrinkled clothes on the board. Heat the iron, iron each garment on the ironing board to remove wrinkles, then fold them neatly. Turn off the iron when done.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1FA84;</span> Folding &amp; Ironing
                </button>
                <button onclick="showTaskPopup('Cutting vegetables','Bring the knife to the vegitable(s), slice the vegetable(s) into pieces for cooking prep., then keep the knife on A11')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F955;</span> Cutting vegetables
                </button>
                <button onclick="showTaskPopup('Cleaning the bathroom and toilet','Deep clean the bathroom area on the board. Scrub the toilet and sink with brushes, apply disinfectant to all surfaces, mop the floor tiles thoroughly, and clean all tools when done.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F6BD;</span> Cleaning bathroom
                </button>
                <button onclick="showTaskPopup('Dusting furniture and surfaces','Dust all furniture and surfaces on the board from top to bottom. Use the duster on all objects, then sweep up the fallen dust.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1FAB6;</span> Dusting surfaces
                </button>
                <button onclick="showTaskPopup('Tidying up the board','Tidy and organise the entire board. Sort all objects into their correct zones: cleaning tools in A1-D4, dining items in E1-H4, kitchen in I1-L4, laundry in M1-P4, pantry in Q1-T4. Keep the working area clear.')" class="w-full text-left px-3 py-2.5 bg-zinc-800/80 hover:bg-zinc-700/80 border border-zinc-700/50 hover:border-blue-500/50 rounded-xl text-xs font-semibold text-zinc-200 transition-all flex items-center gap-2.5">
                    <span class="text-base">&#x1F4E6;</span> Tidying up the board
                </button>
            </div>
        </div>
    </div>

    <!-- Glassmorphism Task Popup -->
    <div id="task-popup" style="display:none; position:fixed; inset:0; z-index:99998; background:rgba(0,0,0,0.55); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); align-items:center; justify-content:center;">
        <div style="background:rgba(18,18,20,0.82); backdrop-filter:blur(28px); -webkit-backdrop-filter:blur(28px); border:1px solid rgba(255,255,255,0.1); border-radius:24px; padding:28px 26px 24px; width:420px; max-width:92vw; max-height:88vh; overflow-y:auto; box-shadow:0 40px 100px rgba(0,0,0,0.8);">
            <!-- Header -->
            <div style="display:flex; align-items:center; gap:14px; margin-bottom:18px;">
                <div style="width:44px; height:44px; background:linear-gradient(135deg,#3b82f6,#6366f1); border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:20px; flex-shrink:0;">&#x1F916;</div>
                <div>
                    <div style="font-family:'Syne',sans-serif; font-size:15px; font-weight:700; color:#f4f4f5;" id="popup-title">Task Ready</div>
                    <div style="font-family:'JetBrains Mono',monospace; font-size:10px; color:#52525b; margin-top:2px;">K5D AI · Add objects then continue</div>
                </div>
            </div>
            <!-- Suggested objects -->
            <div style="background:rgba(39,39,42,0.6); border:1px solid rgba(255,255,255,0.07); border-radius:14px; padding:14px 16px; margin-bottom:18px;">
                <div style="font-family:'Syne',sans-serif; font-size:10px; font-weight:700; color:#71717a; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:10px;">Suggested objects to add</div>
                <div id="popup-suggestions" style="display:flex; flex-direction:column; gap:7px;"></div>
            </div>
            <p style="font-family:'Syne',sans-serif; font-size:12px; color:#71717a; margin:0 0 20px 0; line-height:1.5;">Add these from the <strong style="color:#93c5fd;">Objects Library</strong> panel (bottom-left), then click <strong style="color:#a3e635;">Continue</strong> when ready.</p>
            <!-- Buttons -->
            <div style="display:flex; gap:10px;">
                <button onclick="closeTaskPopup()" style="flex:1; padding:11px 0; background:rgba(39,39,42,0.9); border:1px solid rgba(255,255,255,0.08); border-radius:12px; color:#a1a1aa; font-family:'Syne',sans-serif; font-size:12px; font-weight:600; cursor:pointer;" onmouseover="this.style.background='rgba(63,63,70,0.95)'" onmouseout="this.style.background='rgba(39,39,42,0.9)'">
                    Ok, adding objects&#x2026;
                </button>
                <button onclick="confirmTaskPopup()" style="flex:1; padding:11px 0; background:linear-gradient(135deg,#16a34a,#15803d); border:1px solid rgba(74,222,128,0.25); border-radius:12px; color:#fff; font-family:'Syne',sans-serif; font-size:12px; font-weight:700; cursor:pointer;" onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
                    &#x2713; Continue, already added
                </button>
            </div>
        </div>
    </div>

    <div class="ui-overlay top-20 right-6 w-80 flex flex-col gap-0" style="bottom:34px;">
        <div class="bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl p-4 mb-3 shrink-0" style="max-height: 28vh; overflow-y: auto;">
            <h2 class="text-xs font-bold mb-3 text-zinc-300 tracking-widest uppercase">Object Positions</h2>
            <div id="objects-list" class="space-y-2">
                <div class="text-xs text-zinc-500 italic">No objects on board</div>
            </div>
        </div>
        <div class="bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl flex flex-col flex-1 min-h-0">
            <div class="flex items-center gap-2 px-4 pt-3 pb-3 border-b border-zinc-700/60 shrink-0">
                <div class="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">AI</div>
                <div>
                    <div class="text-xs font-bold text-zinc-200 tracking-widest uppercase">K5D Task Planner</div>
                    <div class="text-xs text-zinc-500 mono">Prolabs V12.2 · Claude</div>
                </div>
                <div id="ai-status-dot" class="ml-auto w-2 h-2 bg-zinc-600 rounded-full" style="transition:background 0.3s;"></div>
            </div>
            <div id="exec-log" class="shrink-0 px-3 pt-2 pb-1 border-b border-zinc-800/50 overflow-y-auto" style="max-height: 120px; display:none;">
                <div class="text-xs mono text-zinc-500 mb-1 uppercase tracking-widest">Execution Plan</div>
                <div id="exec-log-entries"></div>
            </div>
            <div id="chat-messages" class="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
                <div class="flex gap-2">
                    <div class="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">AI</div>
                    <div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-300 leading-relaxed">Hi! I'm the K5D Task Planner. I'll <span class="text-yellow-300 font-bold">plan first</span> and wait for your approval before executing anything. Try: <span class="text-blue-400">"Sweep the floor"</span>, <span class="text-blue-400">"Wash the clothes"</span>, or <span class="text-blue-400">"Cook a meal"</span>. Type <span class="text-purple-300">memory</span> to see what I remember, or <span class="text-purple-300">remember: [note]</span> to teach me something.</div>
                </div>
            </div>
            <div class="px-3 pb-3 pt-2 border-t border-zinc-800 shrink-0">
                <!-- Plan approval panel (hidden until a plan is ready) -->
                <div id="plan-approval" class="hidden mb-2">
                    <div class="bg-zinc-700/60 border border-blue-500/40 rounded-xl p-3 mb-2">
                        <div class="text-xs font-bold text-blue-300 mb-2">📋 PLAN — approve to execute</div>
                        <pre id="plan-text" class="text-xs text-zinc-200 whitespace-pre-wrap leading-relaxed max-h-36 overflow-y-auto"></pre>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="approvePlan()" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-2 px-3 rounded-lg transition-colors">✅ Approve & Execute</button>
                        <button onclick="editPlan()" class="bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-xs font-bold py-2 px-3 rounded-lg transition-colors">✏️ Edit</button>
                        <button onclick="rejectPlan()" class="bg-red-900/60 hover:bg-red-800 text-red-300 text-xs font-bold py-2 px-3 rounded-lg transition-colors">✖ Cancel</button>
                    </div>
                </div>
                <div class="flex gap-2">
                    <input id="chat-input" type="text" placeholder="Describe a task to execute..."
                        class="flex-1 bg-zinc-800 border border-zinc-700 focus:border-blue-500 rounded-xl px-3 py-2 text-xs text-zinc-200 outline-none mono placeholder-zinc-600"
                        onkeydown="if(event.key==='Enter')sendTask()">
                    <button onclick="sendTask()" id="chat-send-btn" class="bg-blue-600 hover:bg-blue-500 transition-colors rounded-xl px-3 py-2 text-white text-xs font-bold">▶</button>
                    <button onclick="showMemory()" title="Show robot memory" class="bg-zinc-700 hover:bg-zinc-600 transition-colors rounded-xl px-2 py-2 text-purple-300 text-xs font-bold">🧠</button>
                </div>
                <div id="task-progress" class="mt-2 hidden">
                    <div class="flex items-center justify-between mb-1">
                        <span class="text-xs mono text-zinc-500">Executing...</span>
                        <span id="task-step-counter" class="text-xs mono text-zinc-500">0/0</span>
                    </div>
                    <div class="w-full bg-zinc-800 rounded-full h-1.5">
                        <div id="task-progress-bar" class="bg-blue-500 h-1.5 rounded-full transition-all duration-300" style="width:0%"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="ui-overlay left-6 bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl p-5 w-80" style="bottom:34px; max-height: 48vh; overflow-y: auto;">
        <h3 class="text-xs font-bold mb-1 tracking-widest text-zinc-400 uppercase">Objects Library</h3>
        <p class="text-xs text-zinc-600 mb-3 mono">Right-click any board object to rename or delete</p>
        <div class="lib-section-title">Basic</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('bottle')">
                <div class="text-3xl mb-1">🍼</div>
                <span class="text-xs text-zinc-400">Bottle</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('box')">
                <div class="text-3xl mb-1">📦</div>
                <span class="text-xs text-zinc-400">Box</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('mug')">
                <div class="text-3xl mb-1">☕</div>
                <span class="text-xs text-zinc-400">Mug</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('book')">
                <div class="text-3xl mb-1">📖</div>
                <span class="text-xs text-zinc-400">Book</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('plant')">
                <div class="text-3xl mb-1">🪴</div>
                <span class="text-xs text-zinc-400">Plant</span>
            </div>
        </div>
        <hr class="lib-divider">
        <div class="lib-section-title">Household (Library)</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('wooden_box')">
                <div class="text-3xl mb-1">🪵</div>
                <span class="text-xs text-zinc-400">Wooden Box</span>
                <div class="obj-lib-meta">
                    <div class="font-bold text-zinc-200 mb-1">wooden_box</div>
                    <div>Open-lid wooden box. Material: wood. Graspability: surprisingly decent.</div>
                </div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('water_cup')">
                <div class="text-3xl mb-1">🥤</div>
                <span class="text-xs text-zinc-400">Water Cup</span>
                <div class="obj-lib-meta">
                    <div class="font-bold text-zinc-200 mb-1">water_cup</div>
                    <div>Cup filled with water. Risk: spill = career-ending. Fragility: moderate.</div>
                </div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('powder_box')">
                <div class="text-3xl mb-1">🧴</div>
                <span class="text-xs text-zinc-400">Powder Box</span>
                <div class="obj-lib-meta">
                    <div class="font-bold text-zinc-200 mb-1">powder_box</div>
                    <div>Cylindrical container. Contents: unknown powder. Sneeze factor: extreme.</div>
                </div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('plate')">
                <div class="text-3xl mb-1">🍽️</div>
                <span class="text-xs text-zinc-400">Plate</span>
                <div class="obj-lib-meta">
                    <div class="font-bold text-zinc-200 mb-1">ceramic_dinner_plate</div>
                    <div>Pristine ceramic plate. Dishwasher safe but emotionally fragile. Breakage: 50/50.</div>
                </div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('glass')">
                <div class="text-3xl mb-1">🥛</div>
                <span class="text-xs text-zinc-400">Glass</span>
                <div class="obj-lib-meta">
                    <div class="font-bold text-zinc-200 mb-1">glass_of_juice</div>
                    <div>Glass of OJ. State: dangerously close to becoming a science experiment.</div>
                </div>
            </div>
        </div>
        <hr class="lib-divider">
        <div class="lib-section-title">Kitchen & Appliances</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('oven')">
                <div class="text-3xl mb-1">🔥</div>
                <span class="text-xs text-zinc-400">Oven</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('cookies')">
                <div class="text-3xl mb-1">🍪</div>
                <span class="text-xs text-zinc-400">Cookies</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('cutting_board')">
                <div class="text-3xl mb-1">🔪</div>
                <span class="text-xs text-zinc-400">Cutting Board</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('knife')">
                <div class="text-3xl mb-1">🗡️</div>
                <span class="text-xs text-zinc-400">Knife</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('pot')">
                <div class="text-3xl mb-1">🍲</div>
                <span class="text-xs text-zinc-400">Pot</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('pan')">
                <div class="text-3xl mb-1">🍳</div>
                <span class="text-xs text-zinc-400">Pan</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('spoon')">
                <div class="text-3xl mb-1">🥄</div>
                <span class="text-xs text-zinc-400">Spoon</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('bowl')">
                <div class="text-3xl mb-1">🥣</div>
                <span class="text-xs text-zinc-400">Bowl</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('napkins')">
                <div class="text-3xl mb-1">🧻</div>
                <span class="text-xs text-zinc-400">Napkins</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('towel')">
                <div class="text-3xl mb-1">🧽</div>
                <span class="text-xs text-zinc-400">Towel</span>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('soap_bottle')">
                <div class="text-3xl mb-1">🧼</div>
                <span class="text-xs text-zinc-400">Soap Bottle</span>
            </div>
        </div>
        <hr class="lib-divider">
        <div class="lib-section-title">🧹 Cleaning & Floor</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('broom')">
                <div class="text-3xl mb-1">🧹</div>
                <span class="text-xs text-zinc-400">Broom</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">broom</div><div>Sweeping tool. Use sweep() command to clear floors.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('dustpan')">
                <div class="text-3xl mb-1">🗑️</div>
                <span class="text-xs text-zinc-400">Dustpan</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">dustpan</div><div>Collects swept dust. Pair with broom.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('mop')">
                <div class="text-3xl mb-1">🧻</div>
                <span class="text-xs text-zinc-400">Mop</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">mop</div><div>Wet mop for floor cleaning. Dip in bucket first.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('bucket')">
                <div class="text-3xl mb-1">🪣</div>
                <span class="text-xs text-zinc-400">Bucket</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">bucket</div><div>Fill with water + disinfectant for mopping.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('duster')">
                <div class="text-3xl mb-1">🪶</div>
                <span class="text-xs text-zinc-400">Duster</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">duster</div><div>Feather duster for furniture and surfaces.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('sponge')">
                <div class="text-3xl mb-1">🧽</div>
                <span class="text-xs text-zinc-400">Sponge</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">sponge</div><div>For scrubbing dishes and surfaces.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('scrub_brush')">
                <div class="text-3xl mb-1">🪥</div>
                <span class="text-xs text-zinc-400">Scrub Brush</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">scrub_brush</div><div>Heavy-duty scrubbing for bathroom/tiles.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('toilet_brush')">
                <div class="text-3xl mb-1">🚽</div>
                <span class="text-xs text-zinc-400">Toilet Brush</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">toilet_brush</div><div>Toilet and drain scrubbing tool.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('disinfectant')">
                <div class="text-3xl mb-1">💜</div>
                <span class="text-xs text-zinc-400">Disinfectant</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">disinfectant</div><div>Spray disinfectant bottle for surfaces and floors.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('sink')">
                <div class="text-3xl mb-1">🚰</div>
                <span class="text-xs text-zinc-400">Sink</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">sink</div><div>2x1 basin. Fill with water for washing utensils.</div></div>
            </div>
        </div>
        <hr class="lib-divider">
        <div class="lib-section-title">👕 Laundry & Ironing</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('washing_machine')">
                <div class="text-3xl mb-1">🫧</div>
                <span class="text-xs text-zinc-400">Washing Machine</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">washing_machine</div><div>Open door, load clothes, add detergent, run_cycle. Too heavy to lift.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('clothes_pile')">
                <div class="text-3xl mb-1">👕</div>
                <span class="text-xs text-zinc-400">Clothes Pile</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">clothes_pile</div><div>Starts 60% dirty, wrinkled, unfolded. Wash → iron → fold.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('iron')">
                <div class="text-3xl mb-1">🪄</div>
                <span class="text-xs text-zinc-400">Iron</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">iron</div><div>Heat it up then iron(clothes_pile) to remove wrinkles.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('ironing_board')">
                <div class="text-3xl mb-1">📐</div>
                <span class="text-xs text-zinc-400">Ironing Board</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">ironing_board</div><div>2x1 padded surface for ironing clothes.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('detergent')">
                <div class="text-3xl mb-1">🧴</div>
                <span class="text-xs text-zinc-400">Detergent</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">detergent</div><div>Laundry detergent. Add to board, then pour into machine before running cycle.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('shirt')">
                <div class="text-3xl mb-1">👕</div>
                <span class="text-xs text-zinc-400">Shirt</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">shirt</div><div>Single shirt. Wash → iron → fold. Random colour each time.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('pants')">
                <div class="text-3xl mb-1">👖</div>
                <span class="text-xs text-zinc-400">Pants</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">pants</div><div>Single pair of trousers. Wash → iron → fold. Random colour each time.</div></div>
            </div>
        </div>
        <hr class="lib-divider">
        <div class="lib-section-title">🍳 Cooking & Shopping</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('stove')">
                <div class="text-3xl mb-1">🔥</div>
                <span class="text-xs text-zinc-400">Stove / Hob</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">stove</div><div>2x1 cooking surface with 4 burners. turn_on to heat. Too heavy to lift.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('ingredient_jar')">
                <div class="text-3xl mb-1">🫙</div>
                <span class="text-xs text-zinc-400">Ingredient Jar</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">ingredient_jar</div><div>Spice or ingredient jar. Twist cap, pour into pot/pan.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('vegetable_basket')">
                <div class="text-3xl mb-1">🧺</div>
                <span class="text-xs text-zinc-400">Veg Basket</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">vegetable_basket</div><div>Fresh produce from market. Unpack onto cutting board for prep.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('shopping_bag')">
                <div class="text-3xl mb-1">🛍️</div>
                <span class="text-xs text-zinc-400">Shopping Bag</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">shopping_bag</div><div>Empty bag for market trips. Fill with produce.</div></div>
            </div>
        </div>
        <div class="lib-section-title">🥕 Vegetables (Sliceable)</div>
        <div class="grid grid-cols-5 gap-3 mb-2">
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('carrot')">
                <div class="text-3xl mb-1">🥕</div>
                <span class="text-xs text-zinc-400">Carrot</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">carrot</div><div>Orange root vegetable. sliceable — bring knife to same cell first.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('cucumber')">
                <div class="text-3xl mb-1">🥒</div>
                <span class="text-xs text-zinc-400">Cucumber</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">cucumber</div><div>Green cucumber. sliceable — bring knife to same cell first.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('tomato')">
                <div class="text-3xl mb-1">🍅</div>
                <span class="text-xs text-zinc-400">Tomato</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">tomato</div><div>Red tomato. sliceable — squirts juice if cut fast.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('onion')">
                <div class="text-3xl mb-1">🧅</div>
                <span class="text-xs text-zinc-400">Onion</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">onion</div><div>Layered onion. sliceable — handle with care.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('potato')">
                <div class="text-3xl mb-1">🥔</div>
                <span class="text-xs text-zinc-400">Potato</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">potato</div><div>Brown potato. sliceable — needs firm grip.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('bell_pepper')">
                <div class="text-3xl mb-1">🫑</div>
                <span class="text-xs text-zinc-400">Bell Pepper</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">bell_pepper</div><div>Green bell pepper. sliceable — hollow inside.</div></div>
            </div>
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('broccoli')">
                <div class="text-3xl mb-1">🥦</div>
                <span class="text-xs text-zinc-400">Broccoli</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">broccoli</div><div>Broccoli head. sliceable into florets.</div></div>
            </div>
        </div>
        <hr class="lib-divider">
        <div id="stl-drop-zone"
             onclick="document.getElementById('stl-upload').click()"
             ondragover="event.preventDefault(); this.classList.add('drag-over')"
             ondragleave="this.classList.remove('drag-over')"
             ondrop="handleSTLDrop(event)">
            <div class="text-2xl mb-1">📐</div>
            <div class="text-xs font-bold text-zinc-300">Upload STL Model</div>
            <div class="text-xs text-zinc-500 mono mt-0.5">Binary or ASCII · .stl</div>
            <div class="text-xs text-zinc-600 mono mt-1">Click or drag & drop</div>
            <input type="file" id="stl-upload" accept=".stl" class="hidden" onchange="handleSTLUpload(event)">
        </div>
        <div id="stl-progress">
            <div class="text-xs mono text-zinc-400" id="stl-progress-label">Parsing STL...</div>
            <div id="stl-progress-bar-wrap"><div id="stl-progress-bar"></div></div>
        </div>
    </div>

    <div id="context-menu">
        <div class="text-xs mono text-zinc-500 px-3 py-1" id="ctx-obj-name">object</div>
        <hr>
        <button onclick="ctxRename()">✏️ Rename</button>
        <button onclick="ctxDelete()" class="danger">🗑️ Delete</button>
    </div>
    <div id="rename-modal">
        <div class="modal-box">
            <div class="text-sm font-bold text-zinc-300 mb-1">Rename Object</div>
            <div class="text-xs text-zinc-500 mono" id="rename-current"></div>
            <input type="text" id="rename-input" placeholder="Enter new name..." maxlength="32">
            <div class="flex gap-2 mt-2">
                <button onclick="confirmRename()" class="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded-lg text-sm font-bold transition-colors">Rename</button>
                <button onclick="closeRenameModal()" class="flex-1 bg-zinc-700 hover:bg-zinc-600 py-2 rounded-lg text-sm font-bold transition-colors">Cancel</button>
            </div>
        </div>
    </div>

    <script>
        function launchWithSplash() {
          document.getElementById('welcome-overlay').style.display = 'none';
          const splash = document.getElementById('splash-overlay');
          splash.style.display = 'flex';

          const bar = document.getElementById('splash-bar');
          const pct = document.getElementById('splash-pct');
          const statusEl = document.getElementById('splash-status-text');
          const steps = [
            { at: 10,  label: 'Loading 3D engine…' },
            { at: 35,  label: 'Building scene graph…' },
            { at: 58,  label: 'Configuring model…' },
            { at: 78,  label: 'Calibrating k5D…' },
            { at: 92,  label: 'Configuring trigonometry…' },
            { at: 100, label: 'Ready.' },
          ];
          const duration = 5000;
          const start = performance.now();

          function tick() {
            const elapsed = performance.now() - start;
            const progress = Math.min(elapsed / duration, 1);
            const pctVal = Math.round(progress * 100);
            bar.style.width = pctVal + '%';
            pct.textContent = pctVal + '%';

            for (let i = steps.length - 1; i >= 0; i--) {
              if (pctVal >= steps[i].at) {
                statusEl.textContent = steps[i].label;
                break;
              }
            }

            if (progress < 1) {
              requestAnimationFrame(tick);
            } else {
              setTimeout(() => { splash.style.display = 'none'; }, 180);
            }
          }
          requestAnimationFrame(tick);
        }

        let scene, camera, renderer;
        let xRail, yCarriage, zRailGroup, zCarriage, gripperMount;
        let gripperLeftJaw, gripperRightJaw;
        let isDraggingCamera = false;
        let prevMouseX = 0, prevMouseY = 0;
        let azimuth = 2.8, elevation = 1.05, orbitDistance = 28;
        const orbitTarget = new THREE.Vector3(10, 4, 5.5);
        const GRID_WIDTH = 20, GRID_HEIGHT = 11;
        let currentX = 0, currentY = 0, currentZ = 4.0;
        let gripperOpen = true;
        let heldObject = null;
        let draggingObject = null;
        let isAnimating = false;
        let selectedObject = null;
        let objects = [];
        const objectTypes = new Map();
        const objectNames = new Map();
        const objectSprites = new Map();
        const objectState = new Map();
        const objectFootprint = new Map();
        const objectWeight = new Map();
        const MAX_LIFT_WEIGHT = 8;
        const RAIL_TOP_Y = 8.5, RAIL_LENGTH = 8.0;
        let ctxTarget = null;
        let commandQueue = [];
        let executionActive = false;
        let totalCommands = 0;
        let completedCommands = 0;

        function setStatus(html) { document.getElementById('status').innerHTML = html; }
        function setGripperState(s) {
            document.getElementById('gripper-state').textContent = 'Gripper: ' + s;
            const el = document.getElementById('hud-grip');
            if (el) { el.textContent = s; el.style.color = s === 'OPEN' ? '#34d399' : '#f59e0b'; }
            const aidot = document.getElementById('ai-status-dot');
            function syncAiDot(color) { const d = document.getElementById('ai-dot'); if(d) d.style.background = color; }
        }

        // Live clock + uptime
        const _startTime = Date.now();
        function _padTwo(n) { return String(n).padStart(2,'0'); }
        function _tickClock() {
            const now = new Date();
            const cl = document.getElementById('live-clock');
            if (cl) cl.textContent = now.toLocaleTimeString('en-GB', { hour12: false }) + '  UTC+' + (-(now.getTimezoneOffset()/60));
            const elapsed = Math.floor((Date.now() - _startTime) / 1000);
            const h = Math.floor(elapsed/3600), m = Math.floor((elapsed%3600)/60), s = elapsed%60;
            const ut = document.getElementById('bottom-uptime');
            if (ut) ut.textContent = `UPTIME: ${_padTwo(h)}:${_padTwo(m)}:${_padTwo(s)}`;
        }
        setInterval(_tickClock, 1000);
        _tickClock();

        function colLetterToX(col) {
            const letter = col.trim().toUpperCase();
            const idx = letter.charCodeAt(0) - 65;
            if (idx >= 0 && idx < GRID_WIDTH) return idx;
            return null;
        }
        function rowNumberToY(row) {
            const num = parseInt(row.trim());
            if (!isNaN(num) && num >= 1 && num <= GRID_HEIGHT) return num - 1;
            return null;
        }

        function parseCoord(str) {
            str = str.trim().toUpperCase();
            const m = str.match(/^([A-T])(\d+)$/);
            if (!m) return null;
            return { col: m[1], row: m[2] };
        }

        function getTouchingCoordinates(colIdx, rowIdx, w = 1, h = 1) {
            const touching = new Set();
            for (let dx = -1; dx <= w; dx++) {
                for (let dz = -1; dz <= h; dz++) {
                    const insideFootprint = dx >= 0 && dx < w && dz >= 0 && dz < h;
                    if (insideFootprint) continue;
                    const nx = colIdx + dx, nz = rowIdx + dz;
                    if (nx >= 0 && nx < GRID_WIDTH && nz >= 0 && nz < GRID_HEIGHT) {
                        touching.add(`${String.fromCharCode(65 + nx)}${nz + 1}`);
                    }
                }
            }
            return Array.from(touching);
        }

        // --- Object configuration: affordances, footprint, weight, capacity, default state ---
        // Affordances describe WHAT KIND of interaction an object supports, so generic commands
        // (open/close, turn_on/off, fill, pour_into, slice, twist_cap, ...) can validate themselves
        // against any object — built-in or custom STL upload — without per-object special-casing.
        function getObjectConfig(type) {
            const t = (type || '').toLowerCase();
            const cfg = { affordances: ['liftable'], footprint: { w: 1, h: 1 }, weight: 2, capacity: 0, defaultState: { dirty: 0 } };
            if (t.includes('soap_bottle')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable', 'twistable_cap'];
                cfg.weight = 1; cfg.capacity = 1.0;
                cfg.defaultState = { fillLevel: 1.0, capOn: true, dirty: 0 };
            } else if (t.includes('bottle')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable', 'twistable_cap'];
                cfg.weight = 1; cfg.capacity = 1.0;
                cfg.defaultState = { fillLevel: 1.0, capOn: true, dirty: 0 };
            } else if (t.includes('powder_box')) {
                cfg.affordances = ['liftable', 'openable', 'pourable', 'fillable'];
                cfg.weight = 2; cfg.capacity = 1.0;
                cfg.defaultState = { isOpen: false, fillLevel: 1.0, dirty: 0 };
            } else if (t.includes('wooden_box')) {
                cfg.affordances = ['liftable', 'openable'];
                cfg.weight = 4; cfg.defaultState = { isOpen: false, dirty: 0 };
            } else if (t.includes('box')) {
                cfg.affordances = ['liftable', 'openable'];
                cfg.weight = 3; cfg.defaultState = { isOpen: false, dirty: 0 };
            } else if (t.includes('mug') || t.includes('water_cup') || t.includes('glass')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable'];
                cfg.weight = 1; cfg.capacity = 1.0;
                cfg.defaultState = { fillLevel: 0, dirty: 0 };
            } else if (t.includes('bowl')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable'];
                cfg.weight = 2; cfg.capacity = 1.5;
                cfg.defaultState = { fillLevel: 0, dirty: 0 };
            } else if (t.includes('pot') || t.includes('pan')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable', 'heatable'];
                cfg.weight = 3; cfg.capacity = t.includes('pot') ? 2.0 : 1.0;
                cfg.defaultState = { fillLevel: 0, dirty: 0, temperature: 'room' };
            } else if (t.includes('plate')) {
                cfg.affordances = ['liftable']; cfg.weight = 1; cfg.defaultState = { dirty: 0 };
            } else if (t.includes('cutting_board')) {
                cfg.affordances = ['liftable', 'sliceable_surface']; cfg.weight = 2; cfg.defaultState = { dirty: 0 };
            } else if (t.includes('knife')) {
                cfg.affordances = ['liftable', 'cutting_tool']; cfg.weight = 1;
            } else if (t.includes('spoon')) {
                cfg.affordances = ['liftable']; cfg.weight = 1;
            } else if (t.includes('napkins')) {
                cfg.affordances = ['liftable', 'cleaning_tool']; cfg.weight = 1;
            } else if (t.includes('towel')) {
                cfg.affordances = ['liftable', 'cleaning_tool', 'foldable', 'ironable']; cfg.weight = 1;
                cfg.defaultState = { folded: false, ironed: false, wrinkled: false, dirty: 0 };
            } else if (t.includes('plant')) {
                cfg.affordances = ['liftable']; cfg.weight = 2;
            } else if (t.includes('book')) {
                cfg.affordances = ['liftable']; cfg.weight = 1;
            } else if (t.includes('cookies')) {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1 };
            } else if (t.includes('oven')) {
                cfg.affordances = ['openable', 'switchable', 'heatable'];
                cfg.footprint = { w: 2, h: 2 }; cfg.weight = 25;
                cfg.defaultState = { isOpen: false, power: false, temperature: 'room' };
            // --- Cleaning & Floor ---
            } else if (t.includes('broom')) {
                cfg.affordances = ['liftable', 'sweeping_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0 };
            } else if (t.includes('dustpan')) {
                cfg.affordances = ['liftable', 'collecting_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0, dustLoad: 0 };
            } else if (t.includes('mop')) {
                cfg.affordances = ['liftable', 'mopping_tool']; cfg.weight = 2;
                cfg.defaultState = { dirty: 0, wet: false };
            } else if (t.includes('bucket')) {
                cfg.affordances = ['liftable', 'fillable', 'pourable']; cfg.weight = 2; cfg.capacity = 2.0;
                cfg.defaultState = { fillLevel: 0, dirty: 0, contents: 'empty' };
            } else if (t.includes('sponge')) {
                cfg.affordances = ['liftable', 'cleaning_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0, wet: false };
            } else if (t.includes('disinfectant')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable', 'spray_tool']; cfg.weight = 1; cfg.capacity = 1.0;
                cfg.defaultState = { fillLevel: 1.0, capOn: true, dirty: 0 };
            } else if (t.includes('scrub_brush')) {
                cfg.affordances = ['liftable', 'cleaning_tool', 'scrubbing_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0 };
            } else if (t.includes('duster')) {
                cfg.affordances = ['liftable', 'cleaning_tool', 'dusting_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0 };
            } else if (t.includes('toilet_brush')) {
                cfg.affordances = ['liftable', 'cleaning_tool', 'scrubbing_tool']; cfg.weight = 1;
                cfg.defaultState = { dirty: 0 };
            } else if (t.includes('sink')) {
                cfg.affordances = ['fillable', 'drainable']; cfg.footprint = { w: 2, h: 1 }; cfg.weight = 30;
                cfg.defaultState = { fillLevel: 0, dirty: 0, contents: 'empty' };
            // --- Laundry ---
            } else if (t.includes('washing_machine')) {
                cfg.affordances = ['openable', 'switchable']; cfg.weight = 40;
                cfg.defaultState = { isOpen: false, power: false, cycleRunning: false, cycleComplete: false };
            } else if (t.includes('clothes_pile') || t.includes('clothes')) {
                cfg.affordances = ['liftable', 'foldable', 'ironable']; cfg.weight = 2;
                cfg.defaultState = { folded: false, ironed: false, wrinkled: true, dirty: 0.6 };
            } else if (t === 'shirt') {
                cfg.affordances = ['liftable', 'foldable', 'ironable']; cfg.weight = 1;
                cfg.defaultState = { folded: false, ironed: false, wrinkled: true, dirty: 0.0 };
            } else if (t === 'pants') {
                cfg.affordances = ['liftable', 'foldable', 'ironable']; cfg.weight = 1;
                cfg.defaultState = { folded: false, ironed: false, wrinkled: true, dirty: 0.0 };
            } else if (t.includes('iron') && !t.includes('ironing')) {
                cfg.affordances = ['liftable', 'switchable', 'heatable']; cfg.weight = 2;
                cfg.defaultState = { power: false, temperature: 'room' };
            } else if (t.includes('ironing_board')) {
                cfg.affordances = ['liftable']; cfg.footprint = { w: 2, h: 1 }; cfg.weight = 5;
            } else if (t.includes('detergent')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable']; cfg.weight = 2; cfg.capacity = 1.0;
                cfg.defaultState = { fillLevel: 1.0, dirty: 0 };
            // --- Cooking ---
            } else if (t.includes('stove')) {
                cfg.affordances = ['switchable', 'heatable']; cfg.footprint = { w: 2, h: 1 }; cfg.weight = 20;
                cfg.defaultState = { power: false, temperature: 'room' };
            } else if (t.includes('ingredient_jar') || t.includes('spice')) {
                cfg.affordances = ['liftable', 'pourable', 'fillable', 'twistable_cap']; cfg.weight = 1; cfg.capacity = 0.5;
                cfg.defaultState = { fillLevel: 1.0, capOn: true, dirty: 0 };
            } else if (t.includes('chopping_board') || t.includes('chopping')) {
                cfg.affordances = ['liftable', 'sliceable_surface']; cfg.weight = 2; cfg.defaultState = { dirty: 0 };
            // --- Shopping ---
            } else if (t === 'carrot') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'cucumber') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'tomato') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'onion') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'potato') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'bell_pepper') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t === 'broccoli') {
                cfg.affordances = ['liftable', 'sliceable']; cfg.weight = 1;
                cfg.defaultState = { sliced: false, pieces: 1, dirty: 0 };
            } else if (t.includes('vegetable_basket') || t.includes('veggie')) {
                cfg.affordances = ['liftable', 'openable']; cfg.weight = 4;
                cfg.defaultState = { isOpen: true, dirty: 0, filled: true };
            } else if (t.includes('shopping_bag')) {
                cfg.affordances = ['liftable', 'openable']; cfg.weight = 2;
                cfg.defaultState = { isOpen: false, dirty: 0 };
            }
            return cfg;
        }

        function getObjectColor(obj) {
            let color = null;
            obj.traverse(child => {
                if (!color && child.material && child.material.color) color = '#' + child.material.color.getHexString();
            });
            return color || '#888888';
        }

        function findObjectByKey(key) {
            const k = (key || '').trim().toLowerCase();
            for (const obj of objects) {
                const t = (objectNames.get(obj) || objectTypes.get(obj) || '').toLowerCase();
                if (t === k) return obj;
            }
            return null;
        }

        // --- Occupancy & simple collision-aware pathing ---
        function getOccupiedCells(excludeObj) {
            const cells = new Set();
            for (const obj of objects) {
                if (obj === excludeObj || obj === heldObject || obj === draggingObject) continue;
                const x = Math.floor(obj.position.x), z = Math.floor(obj.position.z);
                const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
                for (let dx = 0; dx < fp.w; dx++) {
                    for (let dz = 0; dz < fp.h; dz++) cells.add(`${x + dx},${z + dz}`);
                }
            }
            return cells;
        }
        function isCellOccupied(colIdx, rowIdx, excludeObj) {
            return getOccupiedCells(excludeObj).has(`${colIdx},${rowIdx}`);
        }
        function sampleLinePath(x0, y0, x1, y1) {
            const steps = Math.max(Math.abs(Math.round(x1) - Math.round(x0)), Math.abs(Math.round(y1) - Math.round(y0)));
            const cells = [];
            for (let s = 1; s <= steps; s++) {
                const t = s / steps;
                cells.push([Math.round(x0 + (x1 - x0) * t), Math.round(y0 + (y1 - y0) * t)]);
            }
            return cells;
        }
        // Returns null if the direct path is clear, an {x,y} waypoint if an L-shaped detour avoids
        // obstacles, or the string 'blocked' if no simple 2-segment route is clear either.
        function findClearPath(fromX, fromY, toX, toY) {
            const occupied = getOccupiedCells(null);
            const isBlocked = path => path.slice(0, -1).some(([cx, cz]) => occupied.has(`${cx},${cz}`));
            if (!isBlocked(sampleLinePath(fromX, fromY, toX, toY))) return null;
            const routeA = [...sampleLinePath(fromX, fromY, toX, fromY), ...sampleLinePath(toX, fromY, toX, toY)];
            if (!isBlocked(routeA)) return { x: toX, y: fromY };
            const routeB = [...sampleLinePath(fromX, fromY, fromX, toY), ...sampleLinePath(fromX, toY, toX, toY)];
            if (!isBlocked(routeB)) return { x: fromX, y: toY };
            return 'blocked';
        }

        function createFlatLabel(text) {
            const canvas = document.createElement('canvas');
            canvas.width = 256; canvas.height = 128;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 68px Arial';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(text, 128, 68);
            const texture = new THREE.CanvasTexture(canvas);
            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
            sprite.scale.set(1.35, 0.68, 1);
            return sprite;
        }
        function createNameLabel(name) {
            const canvas = document.createElement('canvas');
            canvas.width = 512; canvas.height = 128;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'rgba(30,30,40,0.85)';
            ctx.roundRect(4, 4, 504, 120, 18);
            ctx.fill();
            ctx.fillStyle = '#93c5fd';
            ctx.font = 'bold 52px Arial';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(name.substring(0, 16), 256, 64);
            const texture = new THREE.CanvasTexture(canvas);
            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
            sprite.scale.set(2.2, 0.55, 1);
            return sprite;
        }

        function buildGripper(parent) {
            const gripperGroup = new THREE.Group();
            const darkMat = new THREE.MeshPhongMaterial({ color: 0x1a1f2e });
            const midMat = new THREE.MeshPhongMaterial({ color: 0x2d3748 });
            const accentMat = new THREE.MeshPhongMaterial({ color: 0x1e40af });
            const silverMat = new THREE.MeshPhongMaterial({ color: 0x94a3b8 });
            const rubberMat = new THREE.MeshPhongMaterial({ color: 0x111827 });
            const housing = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.7, 1.8), darkMat);
            gripperGroup.add(housing);
            const railL = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.72, 1.8), accentMat);
            railL.position.set(-0.85, 0, 0); gripperGroup.add(railL);
            const railR = railL.clone(); railR.position.x = 0.85; gripperGroup.add(railR);
            const motorCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.55, 20), midMat);
            motorCyl.position.set(0, 0.62, 0); gripperGroup.add(motorCyl);
            const motorTop = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.15, 20), silverMat);
            motorTop.position.set(0, 0.97, 0); gripperGroup.add(motorTop);
            const guideRod1 = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 1.7, 10), silverMat);
            guideRod1.rotation.x = Math.PI / 2; guideRod1.position.set(-0.4, -0.28, 0); gripperGroup.add(guideRod1);
            const guideRod2 = guideRod1.clone(); guideRod2.position.x = 0.4; gripperGroup.add(guideRod2);
            function makeJaw(side) {
                const jaw = new THREE.Group();
                const body = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.32, 0.85), midMat);
                body.position.y = -0.28; jaw.add(body);
                const hole1 = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.88, 10), darkMat);
                hole1.rotation.x = Math.PI / 2; hole1.position.set(0, -0.28, 0); jaw.add(hole1);
                const finger = new THREE.Mesh(new THREE.BoxGeometry(0.28, 1.4, 0.42), darkMat);
                finger.position.set(0, -1.1, 0.0); jaw.add(finger);
                const pad = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1.0, 0.36), rubberMat);
                pad.position.set(-side * 0.105, -1.1, 0); jaw.add(pad);
                for (let i = -1; i <= 1; i++) {
                    const nub = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 0.08), rubberMat);
                    nub.position.set(-side * 0.16, -1.75, i * 0.12); jaw.add(nub);
                }
                jaw.position.x = side * 0.55;
                return jaw;
            }
            gripperLeftJaw = makeJaw(-1);
            gripperRightJaw = makeJaw(1);
            gripperGroup.add(gripperLeftJaw);
            gripperGroup.add(gripperRightJaw);
            const mountPlate = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.22, 2.2), midMat);
            mountPlate.position.y = 0.46; gripperGroup.add(mountPlate);
            const sensor = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.22, 10), accentMat);
            sensor.rotation.x = Math.PI / 2; sensor.position.set(0, -0.07, 0.92); gripperGroup.add(sensor);
            const sensor2 = sensor.clone(); sensor2.position.z = -0.92; gripperGroup.add(sensor2);
            parent.add(gripperGroup);
            return gripperGroup;
        }
        function setGripperSpread(openFraction) {
            const maxSpread = 0.55, spread = openFraction * maxSpread;
            if (gripperLeftJaw) gripperLeftJaw.position.x = -spread;
            if (gripperRightJaw) gripperRightJaw.position.x = spread;
        }
        function animateGripper(toOpen, duration, onDone) {
            const startOpen = gripperOpen ? 1 : 0, endOpen = toOpen ? 1 : 0;
            const steps = Math.round(duration / 16); let step = 0;
            const tick = () => {
                step++;
                const t = step / steps, val = startOpen + (endOpen - startOpen) * t;
                setGripperSpread(val);
                if (step < steps) requestAnimationFrame(tick);
                else { gripperOpen = toOpen; setGripperState(toOpen ? 'OPEN' : 'CLOSED'); if (onDone) onDone(); }
            };
            requestAnimationFrame(tick);
        }

        function buildZAxis(parent) {
            zRailGroup = new THREE.Group();
            const railMat = new THREE.MeshPhongMaterial({ color: 0x374151 });
            const carriageMat = new THREE.MeshPhongMaterial({ color: 0x1e3a5f });
            const accentMat = new THREE.MeshPhongMaterial({ color: 0x2563eb });
            const silverMat = new THREE.MeshPhongMaterial({ color: 0x94a3b8 });
            const darkMat = new THREE.MeshPhongMaterial({ color: 0x111827 });
            const RLEN = RAIL_LENGTH;
            const rail1 = new THREE.Mesh(new THREE.BoxGeometry(0.22, RLEN, 0.22), railMat);
            rail1.position.set(-0.55, -RLEN / 2, 0); zRailGroup.add(rail1);
            const rail2 = rail1.clone(); rail2.position.x = 0.55; zRailGroup.add(rail2);
            const endPlate = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.18, 1.0), darkMat);
            zRailGroup.add(endPlate);
            const botPlate = endPlate.clone(); botPlate.position.set(0, -RLEN, 0); zRailGroup.add(botPlate);
            const screw = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, RLEN, 14), silverMat);
            screw.position.set(0, -RLEN / 2, 0); zRailGroup.add(screw);
            const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.55, 20), darkMat);
            motor.position.set(0, 0.36, 0); zRailGroup.add(motor);
            const motorCap = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.12, 12), accentMat);
            motorCap.position.set(0, 0.68, 0); zRailGroup.add(motorCap);
            const pulley = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.28, 16), silverMat);
            pulley.position.set(0, -RLEN - 0.22, 0); zRailGroup.add(pulley);
            zCarriage = new THREE.Group(); zRailGroup.add(zCarriage);
            const cBody = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.7, 1.2), carriageMat);
            zCarriage.add(cBody);
            const stripe = new THREE.Mesh(new THREE.BoxGeometry(1.62, 0.12, 1.22), accentMat);
            stripe.position.y = 0.22; zCarriage.add(stripe);
            const block1 = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.65, 0.72), darkMat);
            block1.position.set(-0.55, 0, -0.25); zCarriage.add(block1);
            const block2 = block1.clone(); block2.position.x = 0.55; zCarriage.add(block2);
            const nut = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.3, 8), new THREE.MeshPhongMaterial({ color: 0xb45309 }));
            nut.position.set(0, 0, 0.18); zCarriage.add(nut);
            for (let i = 0; i < 6; i++) {
                const seg = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.4, 0.04), new THREE.MeshPhongMaterial({ color: 0x374151 }));
                seg.position.set(0.75, -i * 0.4, -0.4); zRailGroup.add(seg);
            }
            gripperMount = new THREE.Group(); gripperMount.position.y = -0.55; zCarriage.add(gripperMount);
            buildGripper(gripperMount);
            parent.add(zRailGroup);
            return zRailGroup;
        }

        function initThree() {
            const container = document.getElementById('canvas-container');
            scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
            camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 100);
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.shadowMap.enabled = true;
            container.appendChild(renderer.domElement);
            scene.add(new THREE.AmbientLight(0xaaaaaa, 0.9));
            const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
            dirLight.position.set(25, 30, 20); scene.add(dirLight);
            const fillLight = new THREE.DirectionalLight(0x4466ff, 0.3);
            fillLight.position.set(-10, 5, -5); scene.add(fillLight);
            const floor = new THREE.Mesh(new THREE.PlaneGeometry(55, 40), new THREE.MeshPhongMaterial({ color: 0x0a0a0a }));
            floor.rotation.x = -Math.PI / 2; scene.add(floor);
            const lineMat = new THREE.LineBasicMaterial({ color: 0xef4444 });
            for (let x = 0; x <= GRID_WIDTH; x++) {
                const pts = [new THREE.Vector3(x, 0.06, 0), new THREE.Vector3(x, 0.06, GRID_HEIGHT)];
                scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
            }
            for (let y = 0; y <= GRID_HEIGHT; y++) {
                const pts = [new THREE.Vector3(0, 0.06, y), new THREE.Vector3(GRID_WIDTH, 0.06, y)];
                scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
            }
            for (let x = 0; x < GRID_WIDTH; x++) {
                for (let y = 0; y < GRID_HEIGHT; y++) {
                    const label = createFlatLabel(String.fromCharCode(65 + x) + (y + 1));
                    label.position.set(x + 0.5, 0.08, y + 0.5); label.rotation.x = -Math.PI / 2;
                    scene.add(label);
                }
            }
            const xBeamMat = new THREE.MeshPhongMaterial({ color: 0x555566 });
            const xBeam1 = new THREE.Mesh(new THREE.BoxGeometry(GRID_WIDTH + 6, 0.8, 0.9), xBeamMat);
            xBeam1.position.set(GRID_WIDTH / 2, RAIL_TOP_Y + 0.1, -1.2); scene.add(xBeam1);
            const xBeam2 = xBeam1.clone(); xBeam2.position.z = GRID_HEIGHT + 1.2; scene.add(xBeam2);
            xRail = new THREE.Group(); scene.add(xRail);
            const yBeamMat = new THREE.MeshPhongMaterial({ color: 0x1e40af });
            const yBeam = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.95, GRID_HEIGHT + 4.0), yBeamMat);
            yBeam.position.set(0, RAIL_TOP_Y + 0.1, GRID_HEIGHT / 2); xRail.add(yBeam);
            yCarriage = new THREE.Group(); xRail.add(yCarriage);
            const yCarBody = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.05, 1.5), new THREE.MeshPhongMaterial({ color: 0x1e3a8a }));
            yCarBody.position.set(0, RAIL_TOP_Y + 0.1, 0); yCarriage.add(yCarBody);
            const yCarStripe = new THREE.Mesh(new THREE.BoxGeometry(1.42, 0.14, 1.52), new THREE.MeshPhongMaterial({ color: 0x3b82f6 }));
            yCarStripe.position.set(0, RAIL_TOP_Y + 0.52, 0); yCarriage.add(yCarStripe);
            buildZAxis(yCarriage);
            zRailGroup.position.set(0, RAIL_TOP_Y, 0);
            setGripperSpread(1);
            const xSelect = document.getElementById('x-letter');
            for (let i = 0; i < GRID_WIDTH; i++) {
                const opt = document.createElement('option');
                opt.value = String.fromCharCode(65 + i); opt.textContent = String.fromCharCode(65 + i);
                if (i === 0) opt.selected = true; xSelect.appendChild(opt);
            }
            const ySelect = document.getElementById('y-number');
            for (let i = 1; i <= GRID_HEIGHT; i++) {
                const opt = document.createElement('option');
                opt.value = i; opt.textContent = i;
                if (i === 1) opt.selected = true; ySelect.appendChild(opt);
            }
            updateGantryPosition(0, 0, 4.0);
            updateCameraPosition();
            const canvas = renderer.domElement;
            canvas.addEventListener('mousedown', onMouseDown);
            canvas.addEventListener('mousemove', onMouseMove);
            canvas.addEventListener('mouseup', onMouseUp);
            canvas.addEventListener('mouseleave', onMouseUp);
            canvas.addEventListener('contextmenu', onRightClick);
            canvas.addEventListener('wheel', (e) => {
                orbitDistance = Math.max(14, Math.min(52, orbitDistance + e.deltaY * 0.03));
                updateCameraPosition();
            });
            window.addEventListener('resize', () => {
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            });
            document.addEventListener('click', hideContextMenu);
            document.addEventListener('contextmenu', (e) => {
                if (e.target !== renderer.domElement) hideContextMenu();
            });
            document.getElementById('rename-input').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') confirmRename();
                if (e.key === 'Escape') closeRenameModal();
            });
        }

        function onMouseDown(e) {
            if (e.button !== 0) return;
            const mouse = new THREE.Vector2(
                (e.clientX / window.innerWidth) * 2 - 1,
                -(e.clientY / window.innerHeight) * 2 + 1
            );
            const raycaster = new THREE.Raycaster();
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(objects, true);
            if (intersects.length > 0) {
                let obj = intersects[0].object;
                while (obj.parent && !objects.includes(obj)) obj = obj.parent;
                selectedObject = obj;
            } else {
                isDraggingCamera = true;
                prevMouseX = e.clientX; prevMouseY = e.clientY;
            }
        }
        function onRightClick(e) {
            e.preventDefault();
            const mouse = new THREE.Vector2(
                (e.clientX / window.innerWidth) * 2 - 1,
                -(e.clientY / window.innerHeight) * 2 + 1
            );
            const raycaster = new THREE.Raycaster();
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(objects, true);
            if (intersects.length > 0) {
                let obj = intersects[0].object;
                while (obj.parent && !objects.includes(obj)) obj = obj.parent;
                ctxTarget = obj;
                const menu = document.getElementById('context-menu');
                const name = objectNames.get(obj) || objectTypes.get(obj) || 'object';
                document.getElementById('ctx-obj-name').textContent = name;
                menu.style.display = 'block';
                const menuW = 170, menuH = 100;
                let left = e.clientX, top = e.clientY;
                if (left + menuW > window.innerWidth) left = window.innerWidth - menuW - 8;
                if (top + menuH > window.innerHeight) top = window.innerHeight - menuH - 8;
                menu.style.left = left + 'px'; menu.style.top = top + 'px';
            }
        }
        function hideContextMenu() { document.getElementById('context-menu').style.display = 'none'; }
        window.ctxRename = function() {
            hideContextMenu();
            if (!ctxTarget) return;
            const current = objectNames.get(ctxTarget) || objectTypes.get(ctxTarget) || 'object';
            document.getElementById('rename-current').textContent = 'Current: ' + current;
            document.getElementById('rename-input').value = current;
            document.getElementById('rename-modal').classList.add('active');
            setTimeout(() => document.getElementById('rename-input').select(), 50);
        };
        window.ctxDelete = function() {
            hideContextMenu();
            if (!ctxTarget) return;
            if (heldObject === ctxTarget) heldObject = null;
            if (draggingObject === ctxTarget) draggingObject = null;
            const sprite = objectSprites.get(ctxTarget);
            if (sprite) scene.remove(sprite);
            objectSprites.delete(ctxTarget);
            scene.remove(ctxTarget);
            objects = objects.filter(o => o !== ctxTarget);
            objectTypes.delete(ctxTarget);
            objectNames.delete(ctxTarget);
            objectState.delete(ctxTarget);
            objectFootprint.delete(ctxTarget);
            objectWeight.delete(ctxTarget);
            ctxTarget = null;
            updateObjectPositionsDisplay();
            setStatus('🗑️ Object deleted');
        };
        window.confirmRename = function() {
            const val = document.getElementById('rename-input').value.trim();
            if (!val || !ctxTarget) { closeRenameModal(); return; }
            objectNames.set(ctxTarget, val);
            const oldSprite = objectSprites.get(ctxTarget);
            if (oldSprite) {
                oldSprite.material.map = createNameLabel(val).material.map;
                oldSprite.material.needsUpdate = true;
            }
            updateObjectPositionsDisplay();
            setStatus(`✏️ Renamed to "${val}"`);
            closeRenameModal();
        };
        window.closeRenameModal = function() { document.getElementById('rename-modal').classList.remove('active'); };

        function onMouseMove(e) {
            if (selectedObject) {
                const mouse = new THREE.Vector2(
                    (e.clientX / window.innerWidth) * 2 - 1,
                    -(e.clientY / window.innerHeight) * 2 + 1
                );
                const raycaster = new THREE.Raycaster();
                raycaster.setFromCamera(mouse, camera);
                const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.5);
                const point = new THREE.Vector3();
                if (raycaster.ray.intersectPlane(plane, point)) {
                    selectedObject.position.x = Math.max(0.5, Math.min(GRID_WIDTH - 0.5, Math.floor(point.x) + 0.5));
                    selectedObject.position.z = Math.max(0.5, Math.min(GRID_HEIGHT - 0.5, Math.floor(point.z) + 0.5));
                    selectedObject.position.y = 0.5;
                    const sprite = objectSprites.get(selectedObject);
                    if (sprite) { sprite.position.x = selectedObject.position.x; sprite.position.z = selectedObject.position.z; }
                }
            } else if (isDraggingCamera) {
                const dx = (e.clientX - prevMouseX) * 0.004, dy = (e.clientY - prevMouseY) * 0.004;
                azimuth += dx; elevation = Math.max(0.3, Math.min(2.4, elevation - dy));
                updateCameraPosition();
                prevMouseX = e.clientX; prevMouseY = e.clientY;
            }
        }
        function onMouseUp() { selectedObject = null; isDraggingCamera = false; }
        function updateCameraPosition() {
            const x = orbitTarget.x + orbitDistance * Math.sin(elevation) * Math.cos(azimuth);
            const z = orbitTarget.z + orbitDistance * Math.sin(elevation) * Math.sin(azimuth);
            const y = orbitTarget.y + orbitDistance * Math.cos(elevation);
            camera.position.set(x, y, z); camera.lookAt(orbitTarget);
        }

        function updateGantryPosition(x, y, z) {
            xRail.position.x = x; yCarriage.position.z = y; zCarriage.position.y = -z;
            currentX = x; currentY = y; currentZ = z;
            if (heldObject) {
                const tipY = RAIL_TOP_Y - z - 0.55 - 1.75;
                heldObject.position.set(x + 0.5, Math.max(0.5, tipY), y + 0.5);
                const sprite = objectSprites.get(heldObject);
                if (sprite) { sprite.position.x = heldObject.position.x; sprite.position.z = heldObject.position.z; sprite.position.y = heldObject.position.y + 2.2; }
            }
            if (draggingObject) {
                draggingObject.position.x = x + 0.5;
                draggingObject.position.z = y + 0.5;
                draggingObject.position.y = 0.5;
                const dSprite = objectSprites.get(draggingObject);
                if (dSprite) { dSprite.position.x = draggingObject.position.x; dSprite.position.z = draggingObject.position.z; dSprite.position.y = draggingObject.position.y + 2.2; }
            }
            const letter = String.fromCharCode(65 + Math.round(x)), num = Math.round(y) + 1;
            document.getElementById('current-position').textContent = letter + num;
            document.getElementById('current-coords').textContent = `(${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)})`;
            // Update HUD pills
            const hx = document.getElementById('hud-x'); if (hx) hx.textContent = letter;
            const hy = document.getElementById('hud-y'); if (hy) hy.textContent = num;
            const hz = document.getElementById('hud-z'); if (hz) hz.textContent = z.toFixed(1);
            const bp = document.getElementById('bottom-pos'); if (bp) bp.textContent = `POS: ${letter}${num} · Z:${z.toFixed(1)}`;
        }
        function animateZ(fromZ, toZ, duration, onDone) {
            const steps = Math.round(duration / 16); let step = 0;
            const tick = () => {
                step++;
                const t = 1 - Math.pow(1 - step / steps, 3), z = fromZ + (toZ - fromZ) * t;
                updateGantryPosition(currentX, currentY, z);
                document.getElementById('z-slider').value = z;
                document.getElementById('z-label').textContent = z.toFixed(1);
                if (step < steps) requestAnimationFrame(tick);
                else if (onDone) onDone();
            };
            requestAnimationFrame(tick);
        }
        function animateXY(toX, toY, duration, onDone) {
            const startX = currentX, startY = currentY, steps = Math.round(duration / 16); let step = 0;
            const tick = () => {
                step++;
                const t = 1 - Math.pow(1 - step / steps, 3);
                updateGantryPosition(startX + (toX - startX) * t, startY + (toY - startY) * t, currentZ);
                if (step < steps) requestAnimationFrame(tick);
                else if (onDone) onDone();
            };
            requestAnimationFrame(tick);
        }
        function getObjectAtCurrentCell() {
            const cx = Math.floor(currentX), cz = Math.floor(currentY);
            let fallback = null;
            for (const obj of objects) {
                const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
                const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
                if (cx >= ox && cx < ox + fp.w && cz >= oz && cz < oz + fp.h) {
                    // Prefer objects that are NOT inside a container — containers themselves take priority
                    if (!(objectState.get(obj) || {}).inContainer) return obj;
                    if (!fallback) fallback = obj;
                }
            }
            return fallback; // only reached if everything at the cell is inside a container
        }

        window.onZSlider = function(val) {
            const v = parseFloat(val);
            document.getElementById('z-label').textContent = v.toFixed(1);
            if (!isAnimating) updateGantryPosition(currentX, currentY, v);
        };
        window.moveGripper = function() {
            if (isAnimating) return;
            const letter = document.getElementById('x-letter').value;
            const num = parseInt(document.getElementById('y-number').value);
            const targetX = letter.charCodeAt(0) - 65, targetY = num - 1;
            const targetZ = parseFloat(document.getElementById('z-slider').value);
            isAnimating = true;
            setStatus(`<span class="w-2 h-2 bg-blue-400 rounded-full inline-block animate-pulse"></span>&nbsp;Moving to ${letter}${num}...`);
            animateXY(targetX, targetY, 600, () => {
                animateZ(currentZ, targetZ, 400, () => {
                    isAnimating = false;
                    setStatus(`✅ ${letter}${num} · Z=${targetZ.toFixed(1)}`);
                });
            });
        };
        window.doPickup = function() {
            if (isAnimating) return;
            const obj = getObjectAtCurrentCell();
            if (!obj) { setStatus('⚠️ No object at current cell'); return; }
            isAnimating = true; setStatus('Opening gripper...');
            animateGripper(true, 250, () => {
                setStatus('Descending...');
                animateZ(currentZ, 5.8, 700, () => {
                    setStatus('Closing gripper...');
                    animateGripper(false, 350, () => {
                        heldObject = obj; setStatus('Lifting...');
                        animateZ(currentZ, 2.5, 700, () => { isAnimating = false; setStatus('✅ Object held'); });
                    });
                });
            });
        };
        window.doKeep = function() {
            if (isAnimating) return;
            if (!heldObject) { setStatus('⚠️ Not holding any object'); return; }
            isAnimating = true; setStatus('Descending to place...');
            animateZ(currentZ, 5.8, 700, () => {
                setStatus('Releasing...');
                heldObject.position.set(Math.round(currentX) + 0.5, 0.5, Math.round(currentY) + 0.5);
                const sprite = objectSprites.get(heldObject);
                if (sprite) { sprite.position.x = heldObject.position.x; sprite.position.z = heldObject.position.z; sprite.position.y = heldObject.position.y + 2.2; }
                animateGripper(true, 350, () => {
                    heldObject = null; setStatus('Lifting up...');
                    animateZ(currentZ, 3.0, 600, () => { isAnimating = false; setStatus('✅ Object placed'); });
                });
            });
        };
        function animateTilt(fromDeg, toDeg, duration, onDone) {
            const steps = Math.round(duration / 16); let step = 0;
            const fromRad = fromDeg * Math.PI / 180, toRad = toDeg * Math.PI / 180;
            const tick = () => {
                step++;
                const t = 1 - Math.pow(1 - step / steps, 3);
                gripperMount.rotation.x = fromRad + (toRad - fromRad) * t;
                if (heldObject) heldObject.rotation.x = gripperMount.rotation.x;
                if (step < steps) requestAnimationFrame(tick);
                else if (onDone) onDone();
            };
            requestAnimationFrame(tick);
        }
        window.doPour = function() {
            if (isAnimating) return;
            const target = heldObject || getObjectAtCurrentCell();
            if (!target) { setStatus('⚠️ No object at current position'); return; }
            isAnimating = true;
            heldObject = target;
            setStatus('Tilting to pour...');
            animateTilt(0, 135, 600, () => {
                setStatus('Pouring...');
                setTimeout(() => {
                    setStatus('Returning upright...');
                    animateTilt(135, 0, 500, () => {
                        target.rotation.x = 0;
                        isAnimating = false;
                        setStatus('✅ Pour complete · Still holding');
                    });
                }, 1000);
            });
        };
        window.resetToHome = function() {
            if (isAnimating) return;
            isAnimating = true; heldObject = null;
            gripperMount.rotation.x = 0;
            animateGripper(true, 200, () => {
                animateZ(currentZ, 4.0, 400, () => {
                    animateXY(0, 0, 600, () => {
                        isAnimating = false;
                        document.getElementById('z-slider').value = 4.0;
                        document.getElementById('z-label').textContent = '4.0';
                        setStatus('<span class="text-emerald-400">Home · A1</span>');
                    });
                });
            });
        };

        function spawnObject(obj, type) {
            const rx = Math.floor(Math.random() * GRID_WIDTH) + 0.5;
            const ry = Math.floor(Math.random() * GRID_HEIGHT) + 0.5;
            obj.position.set(rx, 0.5, ry);
            scene.add(obj);
            objects.push(obj);
            objectTypes.set(obj, type);
            const cfg = getObjectConfig(type);
            objectFootprint.set(obj, cfg.footprint);
            objectWeight.set(obj, cfg.weight);
            objectState.set(obj, JSON.parse(JSON.stringify(cfg.defaultState)));
            // Assign a unique name when multiple objects share the same type
            const sameType = objects.filter(o => objectTypes.get(o) === type);
            if (sameType.length > 1) {
                // Retroactively rename the first instance if it has no custom name yet
                const first = sameType[0];
                if (!objectNames.has(first)) {
                    objectNames.set(first, type + '_1');
                    const firstSprite = objectSprites.get(first);
                    if (firstSprite) { scene.remove(firstSprite); objectSprites.delete(first); }
                    const fs = createNameLabel(type + '_1');
                    fs.position.set(first.position.x, 2.7, first.position.z);
                    scene.add(fs); objectSprites.set(first, fs);
                }
                const uniqueName = type + '_' + sameType.length;
                objectNames.set(obj, uniqueName);
                const sprite = createNameLabel(uniqueName);
                sprite.position.set(rx, 2.7, ry);
                scene.add(sprite); objectSprites.set(obj, sprite);
            } else {
                const sprite = createNameLabel(type);
                sprite.position.set(rx, 2.7, ry);
                scene.add(sprite); objectSprites.set(obj, sprite);
            }
            updateObjectPositionsDisplay();
        }
        window.addObject = function(type) {
            let obj;
            if (type === 'bottle') obj = createWaterBottle();
            else if (type === 'box') obj = createGreyBox();
            else if (type === 'mug') obj = createCoffeeMug();
            else if (type === 'book') obj = createBook();
            else if (type === 'plant') obj = createPottedPlant();
            else if (type === 'wooden_box') obj = createWoodenBox();
            else if (type === 'water_cup') obj = createWaterCup();
            else if (type === 'powder_box') obj = createPowderBox();
            else if (type === 'plate') obj = createPlate();
            else if (type === 'glass') obj = createGlass();
            else if (type === 'oven') obj = createOven();
            else if (type === 'cookies') obj = createCookies();
            else if (type === 'cutting_board') obj = createCuttingBoard();
            else if (type === 'knife') obj = createKnife();
            else if (type === 'pot') obj = createPot();
            else if (type === 'pan') obj = createPan();
            else if (type === 'spoon') obj = createSpoon();
            else if (type === 'bowl') obj = createBowl();
            else if (type === 'napkins') obj = createNapkins();
            else if (type === 'towel') obj = createTowel();
            else if (type === 'soap_bottle') obj = createSoapBottle();
            else if (type === 'broom') obj = createBroom();
            else if (type === 'dustpan') obj = createDustpan();
            else if (type === 'mop') obj = createMop();
            else if (type === 'bucket') obj = createBucket();
            else if (type === 'sponge') obj = createSponge();
            else if (type === 'disinfectant') obj = createDisinfectantBottle();
            else if (type === 'scrub_brush') obj = createScrubBrush();
            else if (type === 'duster') obj = createDuster();
            else if (type === 'toilet_brush') obj = createToiletBrush();
            else if (type === 'sink') obj = createSink();
            else if (type === 'washing_machine') obj = createWashingMachine();
            else if (type === 'clothes_pile') obj = createClothesPile();
            else if (type === 'shirt') obj = createShirt();
            else if (type === 'pants') obj = createPants();
            else if (type === 'iron') obj = createIron();
            else if (type === 'ironing_board') obj = createIroningBoard();
            else if (type === 'detergent') obj = createDetergent();
            else if (type === 'stove') obj = createStove();
            else if (type === 'ingredient_jar') obj = createIngredientJar();
            else if (type === 'vegetable_basket') obj = createVegetableBasket();
            else if (type === 'shopping_bag') obj = createShoppingBag();
            else if (type === 'carrot') obj = createCarrot();
            else if (type === 'cucumber') obj = createCucumber();
            else if (type === 'tomato') obj = createTomato();
            else if (type === 'onion') obj = createOnion();
            else if (type === 'potato') obj = createPotato();
            else if (type === 'bell_pepper') obj = createBellPepper();
            else if (type === 'broccoli') obj = createBroccoli();
            if (obj) { spawnObject(obj, type); setStatus(`✅ Added ${type}`); }
        };

        function rotateObject(obj, axis, rad) {
            if (!obj) return;
            if (axis === 'x') obj.rotation.x += rad;
            else if (axis === 'y') obj.rotation.y += rad;
            else if (axis === 'z') obj.rotation.z += rad;
        }
        function setAllObjectsFaceUp(token) {
            // token examples: '+x', '-x', '+y', '-y', '+z', '-z'
            if (!token || token.length < 2) return;
            const sign = token[0] === '-' ? -1 : 1;
            const axis = token[1].toLowerCase();
            const vFrom = new THREE.Vector3();
            if (axis === 'x') vFrom.set(sign, 0, 0);
            else if (axis === 'y') vFrom.set(0, sign, 0);
            else if (axis === 'z') vFrom.set(0, 0, sign);
            const vTo = new THREE.Vector3(0, 1, 0); // world up
            const q = new THREE.Quaternion();
            q.setFromUnitVectors(vFrom, vTo);
            for (const obj of objects) {
                // apply the quaternion so that the chosen local axis faces up
                obj.quaternion.copy(q);
            }
            setStatus(`🔄 Set all objects so ${token.toUpperCase()} faces up`);
        }
        window.rotateAllObjects = function(axis, degrees) {
            const rad = degrees * Math.PI / 180;
            if (objects.length === 0) {
                setStatus('⚠️ No objects on board to rotate');
                return;
            }
            objects.forEach(obj => rotateObject(obj, axis, rad));
            setStatus(`🔄 Rotated all objects ${axis.toUpperCase()} ${degrees > 0 ? '+' : ''}${degrees}°`);
        };

        function parseSTL(buffer) {
            const headerView = new Uint8Array(buffer, 0, Math.min(256, buffer.byteLength));
            const headerText = String.fromCharCode(...headerView).trimStart();
            const isASCII = headerText.startsWith('solid') && headerText.includes('facet');
            if (isASCII) return parseASCIISTL(new TextDecoder().decode(buffer));
            else return parseBinarySTL(buffer);
        }
        function parseBinarySTL(buffer) {
            const view = new DataView(buffer);
            const triCount = view.getUint32(80, true);
            const positions = new Float32Array(triCount * 9);
            const normals = new Float32Array(triCount * 9);
            let offset = 84;
            for (let i = 0; i < triCount; i++) {
                const nx = view.getFloat32(offset, true);
                const ny = view.getFloat32(offset + 4, true);
                const nz = view.getFloat32(offset + 8, true);
                offset += 12;
                for (let v = 0; v < 3; v++) {
                    const base = i * 9 + v * 3;
                    positions[base]     = view.getFloat32(offset, true);
                    positions[base + 1] = view.getFloat32(offset + 4, true);
                    positions[base + 2] = view.getFloat32(offset + 8, true);
                    normals[base] = nx; normals[base + 1] = ny; normals[base + 2] = nz;
                    offset += 12;
                }
                offset += 2;
            }
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            geo.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
            return geo;
        }
        function parseASCIISTL(text) {
            const posArr = [], normArr = [];
            const facetRe = /facet\s+normal\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)[\s\S]*?vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)/g;
            let m;
            while ((m = facetRe.exec(text)) !== null) {
                const nx = parseFloat(m[1]), ny = parseFloat(m[2]), nz = parseFloat(m[3]);
                for (let v = 0; v < 3; v++) {
                    posArr.push(parseFloat(m[4 + v*3]), parseFloat(m[5 + v*3]), parseFloat(m[6 + v*3]));
                    normArr.push(nx, ny, nz);
                }
            }
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(posArr), 3));
            geo.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normArr), 3));
            return geo;
        }
        function normalizeSTLGeometry(geo) {
            geo.computeBoundingBox();
            const box = geo.boundingBox;
            const center = new THREE.Vector3();
            box.getCenter(center);
            const size = new THREE.Vector3();
            box.getSize(size);
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 1.5 / maxDim;
            geo.translate(-center.x, -center.y, -center.z);
            geo.scale(scale, scale, scale);
            geo.computeBoundingBox();
            geo.translate(0, -geo.boundingBox.min.y, 0);
            return geo;
        }
        function showSTLProgress(show, label) {
            const prog = document.getElementById('stl-progress');
            prog.style.display = show ? 'block' : 'none';
            if (label) document.getElementById('stl-progress-label').textContent = label;
        }
        function setSTLProgressBar(pct) {
            document.getElementById('stl-progress-bar').style.width = pct + '%';
        }
        function loadSTLFromBuffer(buffer, typeName) {
            showSTLProgress(true, 'Parsing STL...');
            setSTLProgressBar(30);
            setTimeout(() => {
                try {
                    let geo = parseSTL(buffer);
                    setSTLProgressBar(65);
                    normalizeSTLGeometry(geo);
                    setSTLProgressBar(85);
                    const mat = new THREE.MeshPhongMaterial({ color: 0x64b5f6, specular: 0x2266aa, shininess: 60, side: THREE.DoubleSide });
                    const mesh = new THREE.Mesh(geo, mat);
                    const group = new THREE.Group();
                    group.add(mesh);
                    const baseMat = new THREE.MeshPhongMaterial({ color: 0x1e3a5f });
                    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.08, 24), baseMat);
                    base.position.y = -0.04;
                    group.add(base);
                    setSTLProgressBar(100);
                    spawnObject(group, typeName);
                    setStatus(`✅ STL loaded: ${typeName}`);
                    showSTLProgress(false, '');
                    document.getElementById('stl-upload').value = '';
                } catch (err) {
                    showSTLProgress(false, '');
                    setStatus('❌ STL parse error: ' + err.message);
                }
            }, 30);
        }
        window.handleSTLUpload = function(event) {
            const file = event.target.files[0];
            if (!file) return;
            if (!file.name.toLowerCase().endsWith('.stl')) { setStatus('⚠️ Please upload a .stl file'); return; }
            const typeName = file.name.replace(/\.stl$/i, '').substring(0, 18) || 'stl_model';
            showSTLProgress(true, 'Reading file...');
            setSTLProgressBar(10);
            const reader = new FileReader();
            reader.onload = (e) => loadSTLFromBuffer(e.target.result, typeName);
            reader.readAsArrayBuffer(file);
        };
        window.handleSTLDrop = function(event) {
            event.preventDefault();
            document.getElementById('stl-drop-zone').classList.remove('drag-over');
            const file = event.dataTransfer.files[0];
            if (!file) return;
            if (!file.name.toLowerCase().endsWith('.stl')) { setStatus('⚠️ Please drop a .stl file'); return; }
            const typeName = file.name.replace(/\.stl$/i, '').substring(0, 18) || 'stl_model';
            showSTLProgress(true, 'Reading file...');
            setSTLProgressBar(10);
            const reader = new FileReader();
            reader.onload = (e) => loadSTLFromBuffer(e.target.result, typeName);
            reader.readAsArrayBuffer(file);
        };

        function createWaterBottle() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0x3b82f6 });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.52, 2.5, 28), mat);
            body.position.y = 1.25; g.add(body);
            const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.21, 0.26, 0.7, 20), mat);
            neck.position.y = 2.75; g.add(neck);
            const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 0.28, 20), new THREE.MeshPhongMaterial({ color: 0x1e40af }));
            cap.position.y = 3.18; g.add(cap);
            return g;
        }
        function createGreyBox() {
            const g = new THREE.Group();
            const b = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.3, 1.7), new THREE.MeshPhongMaterial({ color: 0x9ca3af }));
            b.position.y = 0.65; g.add(b);
            return g;
        }
        function createCoffeeMug() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.47, 1.3, 28), new THREE.MeshPhongMaterial({ color: 0xf59e0b }));
            body.position.y = 0.65; g.add(body);
            const handle = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.07, 10, 20, Math.PI), new THREE.MeshPhongMaterial({ color: 0xf59e0b }));
            handle.position.set(0.6, 0.65, 0); handle.rotation.y = Math.PI / 2; g.add(handle);
            return g;
        }
        function createBook() {
            const g = new THREE.Group();
            const b = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.35, 1.5), new THREE.MeshPhongMaterial({ color: 0x4f46e5 }));
            b.position.y = 0.175; g.add(b);
            return g;
        }
        function createPottedPlant() {
            const g = new THREE.Group();
            const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.65, 0.48, 1.1, 24), new THREE.MeshPhongMaterial({ color: 0xb45309 }));
            pot.position.y = 0.55; g.add(pot);
            const leaves = new THREE.Mesh(new THREE.ConeGeometry(0.85, 2.0, 6), new THREE.MeshPhongMaterial({ color: 0x22c55e }));
            leaves.position.y = 2.1; g.add(leaves);
            return g;
        }
        function createWoodenBox() {
            const g = new THREE.Group();
            const woodMat = new THREE.MeshPhongMaterial({ color: 0x8b5a3c });
            const darkWoodMat = new THREE.MeshPhongMaterial({ color: 0x5a3a1c });
            const body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.2, 1.8), woodMat);
            body.position.y = 0.6; g.add(body);
            const lid = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.15, 1.9), woodMat);
            lid.position.set(0, 1.35, -0.25); lid.rotation.x = 0.5; g.add(lid);
            const hinge = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.3, 12), darkWoodMat);
            hinge.rotation.z = Math.PI / 2; hinge.position.set(-0.7, 1.2, 0); g.add(hinge);
            const hinge2 = hinge.clone(); hinge2.position.x = 0.7; g.add(hinge2);
            const grain = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.02, 1.8), darkWoodMat);
            grain.position.y = 0.62; g.add(grain);
            return g;
        }
        function createWaterCup() {
            const g = new THREE.Group();
            const cupMat = new THREE.MeshPhongMaterial({ color: 0xe8f4f8, shininess: 50 });
            const waterMat = new THREE.MeshPhongMaterial({ color: 0x4fb3d9, transparent: true, opacity: 0.7 });
            const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.35, 1.2, 24), cupMat);
            cup.position.y = 0.6; g.add(cup);
            const water = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.33, 0.95, 24), waterMat);
            water.position.y = 0.52; g.add(water);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.41, 0.04, 8, 24), cupMat);
            rim.position.y = 1.25; rim.rotation.x = Math.PI / 2; g.add(rim);
            const surface = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.01, 24), waterMat);
            surface.position.y = 1.0; g.add(surface);
            return g;
        }
        function createPowderBox() {
            const g = new THREE.Group();
            const powderMat = new THREE.MeshPhongMaterial({ color: 0xf5deb3 });
            const labelMat = new THREE.MeshPhongMaterial({ color: 0xd4a574 });
            const cylinder = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, 1.6, 28), powderMat);
            cylinder.position.y = 0.8; g.add(cylinder);
            const label = new THREE.Mesh(new THREE.CylinderGeometry(0.46, 0.46, 0.4, 28), labelMat);
            label.position.y = 0.8; g.add(label);
            const lid = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.45, 0.25, 24), new THREE.MeshPhongMaterial({ color: 0xcd9b6d }));
            lid.position.y = 1.7; g.add(lid);
            const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.12, 0.15, 16), new THREE.MeshPhongMaterial({ color: 0xa68860 }));
            knob.position.y = 1.95; g.add(knob);
            return g;
        }
        function createPlate() {
            const g = new THREE.Group();
            const plateMat = new THREE.MeshPhongMaterial({ color: 0xfffafa });
            const rimMat = new THREE.MeshPhongMaterial({ color: 0xe6e6e6 });
            const plate = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.0, 0.15, 32), plateMat);
            plate.position.y = 0.1; g.add(plate);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.95, 0.08, 12, 32), rimMat);
            rim.position.y = 0.12; rim.rotation.x = Math.PI / 2; g.add(rim);
            const innerRing = new THREE.Mesh(new THREE.TorusGeometry(0.65, 0.04, 10, 32), rimMat);
            innerRing.position.y = 0.13; innerRing.rotation.x = Math.PI / 2; g.add(innerRing);
            return g;
        }
        function createGlass() {
            const g = new THREE.Group();
            const glassMat = new THREE.MeshPhongMaterial({ color: 0xc0ffff, transparent: true, opacity: 0.6, shininess: 100 });
            const liquidMat = new THREE.MeshPhongMaterial({ color: 0xffd700, transparent: true, opacity: 0.5 });
            const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.42, 1.4, 24), glassMat);
            glass.position.y = 0.7; g.add(glass);
            const liquid = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.4, 1.0, 24), liquidMat);
            liquid.position.y = 0.45; g.add(liquid);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.03, 8, 24), glassMat);
            rim.position.y = 1.4; rim.rotation.x = Math.PI / 2; g.add(rim);
            const surface = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.01, 24), liquidMat);
            surface.position.y = 0.95; g.add(surface);
            return g;
        }

        function createOven() {
            const g = new THREE.Group();
            const ovenMat = new THREE.MeshPhongMaterial({ color: 0x1f2937 });
            const body = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.0, 2.0), ovenMat);
            body.position.y = 1.0; g.add(body);
            const doorMat = new THREE.MeshPhongMaterial({ color: 0x374151 });
            const door = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.6, 0.15), doorMat);
            door.position.set(0, 0.8, 1.08); g.add(door);
            const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.6, 12), ovenMat);
            handle.rotation.z = Math.PI / 2; handle.position.set(1.0, 0.8, 1.1); g.add(handle);
            return g;
        }
        function createCookies() {
            const g = new THREE.Group();
            const cookieMat = new THREE.MeshPhongMaterial({ color: 0xd2691e });
            for (let i = 0; i < 3; i++) {
                const cookie = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 0.1, 16), cookieMat);
                cookie.position.set(i * 0.5 - 0.5, 0.1 + i * 0.08, 0);
                g.add(cookie);
            }
            return g;
        }
        function createCuttingBoard() {
            const g = new THREE.Group();
            const boardMat = new THREE.MeshPhongMaterial({ color: 0x8b7355 });
            const board = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.2, 1.8), boardMat);
            board.position.y = 0.1; g.add(board);
            const groove = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.05, 1.6), new THREE.MeshPhongMaterial({ color: 0x654321 }));
            groove.position.y = 0.12; g.add(groove);
            return g;
        }
        function createKnife() {
            const g = new THREE.Group();
            const bladeMat = new THREE.MeshPhongMaterial({ color: 0xc0c0c0 });
            const handleMat = new THREE.MeshPhongMaterial({ color: 0x8b4513 });
            const blade = new THREE.Mesh(new THREE.BoxGeometry(0.15, 2.2, 0.02), bladeMat);
            blade.position.set(0, 1.1, 0); g.add(blade);
            const handle = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.8, 0.1), handleMat);
            handle.position.set(0, -0.2, 0); g.add(handle);
            const pommel = new THREE.Mesh(new THREE.SphereGeometry(0.15, 8, 8), handleMat);
            pommel.position.set(0, -0.65, 0); g.add(pommel);
            return g;
        }
        function createPot() {
            const g = new THREE.Group();
            const potMat = new THREE.MeshPhongMaterial({ color: 0xdc2626 });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.65, 1.4, 28), potMat);
            body.position.y = 0.7; g.add(body);
            const lid = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.73, 0.15, 28), potMat);
            lid.position.y = 1.5; g.add(lid);
            const handle1 = new THREE.Mesh(new THREE.TorusGeometry(0.4, 0.08, 10, 20, Math.PI), potMat);
            handle1.position.set(0.75, 0.7, 0); handle1.rotation.y = Math.PI / 2; g.add(handle1);
            const handle2 = handle1.clone(); handle2.position.x = -0.75; g.add(handle2);
            return g;
        }
        function createPan() {
            const g = new THREE.Group();
            const panMat = new THREE.MeshPhongMaterial({ color: 0xf59e0b });
            const base = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.75, 0.4, 28), panMat);
            base.position.y = 0.2; g.add(base);
            const side = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.73, 0.6, 28), panMat);
            side.position.y = 0.5; g.add(side);
            const handle = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.12, 0.12), panMat);
            handle.position.set(0.9, 0.6, 0); g.add(handle);
            const knob = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 8), new THREE.MeshPhongMaterial({ color: 0x000000 }));
            knob.position.set(1.6, 0.6, 0); g.add(knob);
            return g;
        }
        function createSpoon() {
            const g = new THREE.Group();
            const spoonMat = new THREE.MeshPhongMaterial({ color: 0xc0c0c0 });
            const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 1.8, 12), spoonMat);
            handle.position.set(0, 0.9, 0); g.add(handle);
            const bowl = new THREE.Mesh(new THREE.SphereGeometry(0.35, 12, 12), spoonMat);
            bowl.scale.set(1.0, 0.6, 1.0);
            bowl.position.set(0, -0.35, 0); g.add(bowl);
            return g;
        }
        function createBowl() {
            const g = new THREE.Group();
            const bowlMat = new THREE.MeshPhongMaterial({ color: 0xfbbf24 });
            const body = new THREE.Mesh(new THREE.SphereGeometry(0.9, 20, 20), bowlMat);
            body.scale.set(1.0, 0.7, 1.0);
            body.position.y = 0.5; g.add(body);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.08, 12, 32), bowlMat);
            rim.position.y = 0.85; rim.rotation.x = Math.PI / 2; g.add(rim);
            return g;
        }
        function createNapkins() {
            const g = new THREE.Group();
            const napkinMat = new THREE.MeshPhongMaterial({ color: 0xfef08a });
            for (let i = 0; i < 4; i++) {
                const napkin = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.08, 1.0), napkinMat);
                napkin.position.y = i * 0.12;
                napkin.rotation.z = Math.random() * 0.2 - 0.1;
                g.add(napkin);
            }
            return g;
        }
        function createTowel() {
            const g = new THREE.Group();
            const towelMat = new THREE.MeshPhongMaterial({ color: 0x3b82f6 });
            const towel = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.15, 1.2), towelMat);
            towel.position.y = 0.1; g.add(towel);
            const folds = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.3, 1.2), towelMat);
            folds.position.set(0, 0.3, 0);
            folds.rotation.z = 0.3;
            g.add(folds);
            return g;
        }
        function createSoapBottle() {
            const g = new THREE.Group();
            const soapMat = new THREE.MeshPhongMaterial({ color: 0x06b6d4 });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.35, 1.8, 24), soapMat);
            body.position.y = 0.9; g.add(body);
            const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.18, 0.5, 16), soapMat);
            neck.position.y = 1.8; g.add(neck);
            const pump = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.35, 12), new THREE.MeshPhongMaterial({ color: 0x0891b2 }));
            pump.position.y = 2.15; g.add(pump);
            return g;
        }

        // --- NEW GEOMETRY CREATORS ---

        function createBroom() {
            const g = new THREE.Group();
            const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 3.5, 8), new THREE.MeshPhongMaterial({ color: 0xa0522d }));
            stick.position.y = 2.1; g.add(stick);
            const head = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.12, 0.3), new THREE.MeshPhongMaterial({ color: 0xf59e0b }));
            head.position.y = 0.36; g.add(head);
            for (let i = 0; i < 7; i++) {
                const bristle = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.01, 0.3, 5), new THREE.MeshPhongMaterial({ color: 0xd97706 }));
                bristle.position.set(-0.42 + i * 0.14, 0.15, 0); g.add(bristle);
            }
            return g;
        }
        function createDustpan() {
            const g = new THREE.Group();
            const panMat = new THREE.MeshPhongMaterial({ color: 0x64748b });
            const pan = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.08, 0.85), panMat);
            pan.position.y = 0.08; g.add(pan);
            const backWall = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.25, 0.06), panMat);
            backWall.position.set(0, 0.2, -0.39); g.add(backWall);
            const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.2, 8), new THREE.MeshPhongMaterial({ color: 0x475569 }));
            handle.rotation.x = Math.PI / 3; handle.position.set(0, 0.6, -0.75); g.add(handle);
            return g;
        }
        function createMop() {
            const g = new THREE.Group();
            const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 3.5, 8), new THREE.MeshPhongMaterial({ color: 0x6b7280 }));
            stick.position.y = 2.1; g.add(stick);
            const head = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.35, 0.35, 16), new THREE.MeshPhongMaterial({ color: 0xe0e7ff }));
            head.position.y = 0.18; g.add(head);
            for (let i = 0; i < 10; i++) {
                const strand = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.015, 0.45, 5), new THREE.MeshPhongMaterial({ color: 0xc7d2fe }));
                const a = (i / 10) * Math.PI * 2;
                strand.position.set(Math.cos(a) * 0.28, -0.08, Math.sin(a) * 0.28); g.add(strand);
            }
            return g;
        }
        function createBucket() {
            const g = new THREE.Group();
            const bucketMat = new THREE.MeshPhongMaterial({ color: 0xfbbf24 });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.42, 1.1, 20), bucketMat);
            body.position.y = 0.55; g.add(body);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.56, 0.05, 8, 24), new THREE.MeshPhongMaterial({ color: 0xf59e0b }));
            rim.rotation.x = Math.PI / 2; rim.position.y = 1.1; g.add(rim);
            const handle = new THREE.Mesh(new THREE.TorusGeometry(0.52, 0.035, 6, 16, Math.PI), new THREE.MeshPhongMaterial({ color: 0x78716c }));
            handle.rotation.x = -Math.PI / 2; handle.position.y = 1.35; g.add(handle);
            return g;
        }
        function createSponge() {
            const g = new THREE.Group();
            const sponge = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.35, 0.6), new THREE.MeshPhongMaterial({ color: 0xfde047 }));
            sponge.position.y = 0.18; g.add(sponge);
            const scrub = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.1, 0.6), new THREE.MeshPhongMaterial({ color: 0x16a34a }));
            scrub.position.y = 0.4; g.add(scrub);
            return g;
        }
        function createDisinfectantBottle() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0x7c3aed });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.29, 1.6, 16), mat);
            body.position.y = 0.8; g.add(body);
            const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 0.4, 12), mat);
            neck.position.y = 1.6; g.add(neck);
            const trigger = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.12, 0.12), new THREE.MeshPhongMaterial({ color: 0x5b21b6 }));
            trigger.position.set(0.2, 1.75, 0); g.add(trigger);
            const nozzle = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.45, 8), new THREE.MeshPhongMaterial({ color: 0x4c1d95 }));
            nozzle.rotation.z = Math.PI / 2; nozzle.position.set(0.35, 1.95, 0); g.add(nozzle);
            const label = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.7, 0.01), new THREE.MeshPhongMaterial({ color: 0xddd6fe }));
            label.position.set(0.33, 0.85, 0); g.add(label);
            return g;
        }
        function createScrubBrush() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.28, 0.5), new THREE.MeshPhongMaterial({ color: 0x2563eb }));
            body.position.y = 0.22; g.add(body);
            for (let i = 0; i < 5; i++) for (let j = 0; j < 3; j++) {
                const bristle = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.02, 0.18, 5), new THREE.MeshPhongMaterial({ color: 0x93c5fd }));
                bristle.position.set(-0.28 + i * 0.14, 0.04, -0.15 + j * 0.15); g.add(bristle);
            }
            const handle = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.16, 0.24), new THREE.MeshPhongMaterial({ color: 0x1d4ed8 }));
            handle.position.set(0, 0.45, 0); g.add(handle);
            return g;
        }
        function createDuster() {
            const g = new THREE.Group();
            const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 2.2, 8), new THREE.MeshPhongMaterial({ color: 0xa0522d }));
            stick.position.y = 1.4; g.add(stick);
            for (let i = 0; i < 14; i++) {
                const feather = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.7, 0.04), new THREE.MeshPhongMaterial({ color: i % 2 === 0 ? 0xf9a8d4 : 0xfecdd3 }));
                const a = (i / 14) * Math.PI * 2;
                feather.position.set(Math.cos(a) * 0.35, 0.5, Math.sin(a) * 0.35);
                feather.rotation.y = a; feather.rotation.z = 0.6; g.add(feather);
            }
            return g;
        }
        function createToiletBrush() {
            const g = new THREE.Group();
            const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 2.6, 8), new THREE.MeshPhongMaterial({ color: 0xd1d5db }));
            stick.position.y = 1.6; g.add(stick);
            const head = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.22, 0.5, 14), new THREE.MeshPhongMaterial({ color: 0xf3f4f6 }));
            head.position.y = 0.35; g.add(head);
            for (let i = 0; i < 8; i++) {
                const bristle = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.01, 0.32, 5), new THREE.MeshPhongMaterial({ color: 0xe5e7eb }));
                const a = (i / 8) * Math.PI * 2;
                bristle.position.set(Math.cos(a) * 0.18, 0.16, Math.sin(a) * 0.18);
                bristle.rotation.x = Math.cos(a) * 0.5; bristle.rotation.z = Math.sin(a) * 0.5; g.add(bristle);
            }
            const holder = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.65, 14), new THREE.MeshPhongMaterial({ color: 0x9ca3af }));
            holder.position.y = -0.2; g.add(holder);
            return g;
        }
        function createSink() {
            const g = new THREE.Group();
            const baseMat = new THREE.MeshPhongMaterial({ color: 0xe5e7eb });
            const basin = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.7, 1.6), baseMat);
            basin.position.y = 0.35; g.add(basin);
            const inner = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.55, 1.2), new THREE.MeshPhongMaterial({ color: 0xf0fdfa }));
            inner.position.y = 0.5; g.add(inner);
            const drain = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.1, 12), new THREE.MeshPhongMaterial({ color: 0x6b7280 }));
            drain.position.set(0, 0.25, 0); g.add(drain);
            const tap = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.55, 10), new THREE.MeshPhongMaterial({ color: 0xc0c0c0, shininess: 120 }));
            tap.position.set(0, 1.1, -0.7); g.add(tap);
            const spout = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 10), new THREE.MeshPhongMaterial({ color: 0xc0c0c0, shininess: 120 }));
            spout.rotation.x = Math.PI / 2; spout.position.set(0, 1.2, -0.45); g.add(spout);
            return g;
        }
        function createWashingMachine() {
            const g = new THREE.Group();
            const bodyMat = new THREE.MeshPhongMaterial({ color: 0xf1f5f9 });
            const body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 2.0, 1.8), bodyMat);
            body.position.y = 1.0; g.add(body);
            const door = new THREE.Mesh(new THREE.CylinderGeometry(0.58, 0.58, 0.12, 32), new THREE.MeshPhongMaterial({ color: 0xbfdbfe, shininess: 80 }));
            door.rotation.x = Math.PI / 2; door.position.set(0, 1.1, 0.91); g.add(door);
            const ring = new THREE.Mesh(new THREE.TorusGeometry(0.59, 0.06, 8, 32), new THREE.MeshPhongMaterial({ color: 0x9ca3af }));
            ring.position.set(0, 1.1, 0.88); g.add(ring);
            const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.52, 0.08, 32), new THREE.MeshPhongMaterial({ color: 0xdbeafe, transparent: true, opacity: 0.5 }));
            drum.rotation.x = Math.PI / 2; drum.position.set(0, 1.1, 0.95); g.add(drum);
            const panel = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.45, 1.82), new THREE.MeshPhongMaterial({ color: 0xe2e8f0 }));
            panel.position.y = 2.22; g.add(panel);
            for (let i = 0; i < 3; i++) {
                const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.06, 12), new THREE.MeshPhongMaterial({ color: 0x3b82f6 }));
                knob.rotation.x = Math.PI / 2; knob.position.set(-0.5 + i * 0.5, 2.22, 0.92); g.add(knob);
            }
            return g;
        }
        function createClothesPile() {
            const g = new THREE.Group();
            const colors = [0x3b82f6, 0xef4444, 0x10b981, 0xf59e0b, 0x8b5cf6];
            for (let i = 0; i < 5; i++) {
                const cloth = new THREE.Mesh(new THREE.BoxGeometry(1.6 - i * 0.08, 0.18, 1.1 - i * 0.06), new THREE.MeshPhongMaterial({ color: colors[i] }));
                cloth.position.y = 0.12 + i * 0.2;
                cloth.rotation.y = (Math.random() - 0.5) * 0.3; g.add(cloth);
            }
            return g;
        }
        function createShirt() {
            const g = new THREE.Group();
            const palette = [0x3b82f6, 0xef4444, 0x10b981, 0x8b5cf6, 0xf59e0b, 0xe11d48, 0x0ea5e9, 0x14b8a6];
            const c = palette[Math.floor(Math.random() * palette.length)];
            const mat = new THREE.MeshPhongMaterial({ color: c });
            // Body (torso)
            const body = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.07, 1.1), mat);
            body.position.y = 0.035; g.add(body);
            // Left sleeve
            const lSleeve = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.07, 0.32), mat);
            lSleeve.position.set(-0.91, 0.035, -0.12); lSleeve.rotation.y = 0.28; g.add(lSleeve);
            // Right sleeve
            const rSleeve = lSleeve.clone();
            rSleeve.position.set(0.91, 0.035, -0.12); rSleeve.rotation.y = -0.28; g.add(rSleeve);
            // Collar
            const collar = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.045, 6, 16, Math.PI), new THREE.MeshPhongMaterial({ color: 0xffffff }));
            collar.rotation.x = Math.PI / 2; collar.position.set(0, 0.08, -0.48); g.add(collar);
            // Buttons
            for (let i = 0; i < 4; i++) {
                const btn = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.02, 8), new THREE.MeshPhongMaterial({ color: 0xf1f5f9 }));
                btn.position.set(0, 0.08, -0.3 + i * 0.2); g.add(btn);
            }
            return g;
        }
        function createPants() {
            const g = new THREE.Group();
            const palette = [0x1e3a5f, 0x374151, 0x78350f, 0x14532d, 0x4c1d95, 0x881337];
            const c = palette[Math.floor(Math.random() * palette.length)];
            const mat = new THREE.MeshPhongMaterial({ color: c });
            // Waist panel
            const waist = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.07, 0.28), mat);
            waist.position.y = 0.035; g.add(waist);
            // Left leg
            const lLeg = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.07, 0.9), mat);
            lLeg.position.set(-0.3, 0.035, 0.62); g.add(lLeg);
            // Right leg
            const rLeg = lLeg.clone();
            rLeg.position.set(0.3, 0.035, 0.62); g.add(rLeg);
            // Crotch panel
            const crotch = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.07, 0.34), mat);
            crotch.position.set(0, 0.035, 0.22); g.add(crotch);
            // Belt
            const belt = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.08, 0.16), new THREE.MeshPhongMaterial({ color: 0x1c1917 }));
            belt.position.set(0, 0.09, -0.08); g.add(belt);
            // Buckle
            const buckle = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.08, 0.14), new THREE.MeshPhongMaterial({ color: 0xc0c0c0, shininess: 150 }));
            buckle.position.set(0, 0.09, -0.06); g.add(buckle);
            return g;
        }
        function createIron() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0xe2e8f0, shininess: 100 });
            const body = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.42, 1.1), mat);
            body.position.y = 0.45; g.add(body);
            const sole = new THREE.Mesh(new THREE.BoxGeometry(0.68, 0.08, 1.1), new THREE.MeshPhongMaterial({ color: 0xc0c0c0, shininess: 160 }));
            sole.position.y = 0.24; g.add(sole);
            const handle = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.7, 0.28), new THREE.MeshPhongMaterial({ color: 0x1d4ed8 }));
            handle.position.set(0, 0.85, -0.28); g.add(handle);
            const top = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.16, 0.5), new THREE.MeshPhongMaterial({ color: 0x3b82f6 }));
            top.position.set(0, 0.78, 0.15); g.add(top);
            const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.0, 8), new THREE.MeshPhongMaterial({ color: 0x1e1b4b }));
            cord.rotation.z = 0.7; cord.position.set(-0.55, 0.75, -0.28); g.add(cord);
            return g;
        }
        function createIroningBoard() {
            const g = new THREE.Group();
            const boardMat = new THREE.MeshPhongMaterial({ color: 0xfef9c3 });
            const surface = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.1, 1.0), boardMat);
            surface.position.y = 1.3; g.add(surface);
            const cover = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.06, 1.0), new THREE.MeshPhongMaterial({ color: 0xfde68a }));
            cover.position.y = 1.38; g.add(cover);
            for (let i = 0; i < 4; i++) {
                const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.3, 8), new THREE.MeshPhongMaterial({ color: 0x6b7280 }));
                const xp = i < 2 ? -1.1 : 1.1, zp = (i % 2 === 0) ? -0.35 : 0.35;
                leg.position.set(xp, 0.65, zp);
                const angle = xp * 0.25; leg.rotation.z = angle; leg.rotation.x = (i % 2 === 0 ? 0.12 : -0.12); g.add(leg);
            }
            return g;
        }
        function createDetergent() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0x2563eb });
            const body = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.6, 0.65), mat);
            body.position.y = 0.8; g.add(body);
            const top = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.45, 0.65), new THREE.MeshPhongMaterial({ color: 0x1d4ed8 }));
            top.position.y = 1.82; g.add(top);
            const label = new THREE.Mesh(new THREE.BoxGeometry(0.88, 0.9, 0.01), new THREE.MeshPhongMaterial({ color: 0xdbeafe }));
            label.position.set(0.34, 0.85, 0); g.add(label);
            const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.22, 12), new THREE.MeshPhongMaterial({ color: 0x3b82f6 }));
            cap.position.y = 2.16; g.add(cap);
            return g;
        }
        function createStove() {
            const g = new THREE.Group();
            const bodyMat = new THREE.MeshPhongMaterial({ color: 0x374151 });
            const top = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.18, 1.8), bodyMat);
            top.position.y = 0.65; g.add(top);
            const body = new THREE.Mesh(new THREE.BoxGeometry(3.2, 1.1, 1.8), new THREE.MeshPhongMaterial({ color: 0x4b5563 }));
            body.position.y = 0.05; g.add(body);
            const burnerPos = [[-0.75, -0.38], [-0.75, 0.38], [0.75, -0.38], [0.75, 0.38]];
            burnerPos.forEach(([x, z]) => {
                const ring = new THREE.Mesh(new THREE.TorusGeometry(0.35, 0.06, 8, 24), new THREE.MeshPhongMaterial({ color: 0x1f2937 }));
                ring.rotation.x = Math.PI / 2; ring.position.set(x, 0.76, z); g.add(ring);
                const inner = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.06, 16), new THREE.MeshPhongMaterial({ color: 0x111827 }));
                inner.position.set(x, 0.74, z); g.add(inner);
            });
            for (let i = 0; i < 4; i++) {
                const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.07, 12), new THREE.MeshPhongMaterial({ color: 0x6b7280 }));
                knob.rotation.x = Math.PI / 2; knob.position.set(-1.1 + i * 0.72, 0.65, 0.92); g.add(knob);
            }
            return g;
        }
        function createIngredientJar() {
            const g = new THREE.Group();
            const colors = [0xef4444, 0xf59e0b, 0x84cc16, 0x8b5cf6, 0xec4899];
            const c = colors[Math.floor(Math.random() * colors.length)];
            const jar = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.25, 1.0, 16), new THREE.MeshPhongMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.7 }));
            jar.position.y = 0.5; g.add(jar);
            const fill = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.22, 0.7, 16), new THREE.MeshPhongMaterial({ color: c }));
            fill.position.y = 0.35; g.add(fill);
            const lid = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.15, 16), new THREE.MeshPhongMaterial({ color: 0xd1d5db }));
            lid.position.y = 1.07; g.add(lid);
            return g;
        }
        function createVegetableBasket() {
            const g = new THREE.Group();
            const basketMat = new THREE.MeshPhongMaterial({ color: 0x92400e });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.65, 0.85, 18), basketMat);
            body.position.y = 0.45; g.add(body);
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.86, 0.06, 6, 22), new THREE.MeshPhongMaterial({ color: 0x78350f }));
            rim.rotation.x = Math.PI / 2; rim.position.y = 0.88; g.add(rim);
            const vegData = [
                { color: 0xef4444, x: 0.1, z: 0.1, r: 0.25 },   // tomato
                { color: 0x22c55e, x: -0.3, z: -0.1, r: 0.22 },  // cabbage
                { color: 0xf97316, x: 0.3, z: -0.25, r: 0.2 },   // carrot
                { color: 0x84cc16, x: -0.15, z: 0.3, r: 0.18 },  // lime
            ];
            vegData.forEach(v => {
                const veg = new THREE.Mesh(new THREE.SphereGeometry(v.r, 10, 10), new THREE.MeshPhongMaterial({ color: v.color }));
                veg.position.set(v.x, 0.95, v.z); g.add(veg);
            });
            const carrot = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.14, 0.65, 8), new THREE.MeshPhongMaterial({ color: 0xf97316 }));
            carrot.position.set(0.25, 1.05, 0.25); carrot.rotation.z = 0.4; g.add(carrot);
            const handle = new THREE.Mesh(new THREE.TorusGeometry(0.8, 0.045, 6, 16, Math.PI), new THREE.MeshPhongMaterial({ color: 0x78350f }));
            handle.position.set(0, 1.55, 0); g.add(handle);
            return g;
        }
        function createShoppingBag() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0xfef9c3 });
            const body = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.5, 0.7), mat);
            body.position.y = 0.75; g.add(body);
            const base = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.12, 0.7), new THREE.MeshPhongMaterial({ color: 0xfde68a }));
            base.position.y = 0.06; g.add(base);
            const handle1 = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.04, 8, 16, Math.PI), new THREE.MeshPhongMaterial({ color: 0x92400e }));
            handle1.position.set(-0.25, 1.65, 0); g.add(handle1);
            const handle2 = handle1.clone(); handle2.position.set(0.25, 1.65, 0); g.add(handle2);
            return g;
        }

        // ── Vegetable geometry creators ─────────────────────────────────────
        function createCarrot() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.22, 1.1, 10), new THREE.MeshPhongMaterial({ color: 0xf97316 }));
            body.position.y = 0.55; g.add(body);
            for (let i = 0; i < 3; i++) {
                const tip = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.05, 0.22, 6), new THREE.MeshPhongMaterial({ color: 0xf97316 }));
                tip.position.set((i-1)*0.04, 0.04, 0); g.add(tip);
            }
            const leaf = new THREE.Mesh(new THREE.ConeGeometry(0.14, 0.38, 5), new THREE.MeshPhongMaterial({ color: 0x16a34a }));
            leaf.position.y = 1.28; g.add(leaf);
            return g;
        }
        function createCucumber() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.20, 1.4, 14), new THREE.MeshPhongMaterial({ color: 0x4ade80 }));
            body.position.y = 0.7; g.add(body);
            const cap = new THREE.Mesh(new THREE.SphereGeometry(0.22, 10, 8), new THREE.MeshPhongMaterial({ color: 0x4ade80 }));
            cap.position.y = 1.42; g.add(cap);
            const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.18, 8), new THREE.MeshPhongMaterial({ color: 0x15803d }));
            stem.position.y = 0.1; g.add(stem);
            for (let i = 0; i < 6; i++) {
                const bump = new THREE.Mesh(new THREE.SphereGeometry(0.05, 6, 5), new THREE.MeshPhongMaterial({ color: 0x22c55e }));
                const a = (i/6)*Math.PI*2;
                bump.position.set(Math.cos(a)*0.22, 0.5 + i*0.15, Math.sin(a)*0.22); g.add(bump);
            }
            return g;
        }
        function createTomato() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.SphereGeometry(0.42, 16, 14), new THREE.MeshPhongMaterial({ color: 0xef4444, shininess: 80 }));
            body.scale.y = 0.82; body.position.y = 0.38; g.add(body);
            const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.22, 8), new THREE.MeshPhongMaterial({ color: 0x4d7c0f }));
            stem.position.y = 0.74; g.add(stem);
            for (let i = 0; i < 5; i++) {
                const leaf = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.04, 0.08), new THREE.MeshPhongMaterial({ color: 0x65a30d }));
                leaf.rotation.y = (i/5)*Math.PI*2; leaf.position.set(Math.cos((i/5)*Math.PI*2)*0.18, 0.73, Math.sin((i/5)*Math.PI*2)*0.18); g.add(leaf);
            }
            return g;
        }
        function createOnion() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.SphereGeometry(0.40, 14, 12), new THREE.MeshPhongMaterial({ color: 0xd97706 }));
            body.scale.y = 0.9; body.position.y = 0.38; g.add(body);
            const skin = new THREE.Mesh(new THREE.SphereGeometry(0.41, 14, 12), new THREE.MeshPhongMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.35 }));
            skin.scale.y = 0.9; skin.position.y = 0.38; g.add(skin);
            const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.05, 0.3, 8), new THREE.MeshPhongMaterial({ color: 0x92400e }));
            stem.position.y = 0.8; g.add(stem);
            const root = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.02, 0.12, 8), new THREE.MeshPhongMaterial({ color: 0x78350f }));
            root.position.y = 0.05; g.add(root);
            return g;
        }
        function createPotato() {
            const g = new THREE.Group();
            const body = new THREE.Mesh(new THREE.SphereGeometry(0.38, 10, 8), new THREE.MeshPhongMaterial({ color: 0x92400e }));
            body.scale.set(1.25, 0.85, 1.0); body.position.y = 0.34; g.add(body);
            const skin = new THREE.Mesh(new THREE.SphereGeometry(0.39, 10, 8), new THREE.MeshPhongMaterial({ color: 0xa16207, transparent: true, opacity: 0.25 }));
            skin.scale.set(1.25, 0.85, 1.0); skin.position.y = 0.34; g.add(skin);
            for (let i = 0; i < 4; i++) {
                const eye = new THREE.Mesh(new THREE.SphereGeometry(0.04, 6, 5), new THREE.MeshPhongMaterial({ color: 0x78350f }));
                eye.position.set((Math.random()-0.5)*0.45, 0.32+(Math.random()-0.5)*0.2, (Math.random()-0.5)*0.35); g.add(eye);
            }
            return g;
        }
        function createBellPepper() {
            const g = new THREE.Group();
            const colors = [0x22c55e, 0xef4444, 0xf59e0b, 0xf97316];
            const c = colors[Math.floor(Math.random()*colors.length)];
            const mat = new THREE.MeshPhongMaterial({ color: c, shininess: 90 });
            for (let i = 0; i < 3; i++) {
                const lobe = new THREE.Mesh(new THREE.SphereGeometry(0.28, 10, 9), mat);
                lobe.scale.set(0.9, 0.85, 0.95);
                const a = (i/3)*Math.PI*2;
                lobe.position.set(Math.cos(a)*0.14, 0.3, Math.sin(a)*0.14); g.add(lobe);
            }
            const top = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.30, 0.12, 14), mat);
            top.position.y = 0.58; g.add(top);
            const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.04, 0.26, 8), new THREE.MeshPhongMaterial({ color: 0x4d7c0f }));
            stem.position.y = 0.78; g.add(stem);
            return g;
        }
        function createBroccoli() {
            const g = new THREE.Group();
            const stalkMat = new THREE.MeshPhongMaterial({ color: 0x65a30d });
            const headMat  = new THREE.MeshPhongMaterial({ color: 0x15803d });
            const stalk = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.14, 0.9, 10), stalkMat);
            stalk.position.y = 0.45; g.add(stalk);
            const headData = [
                { x:0,    y:1.02, z:0,    r:0.34 },
                { x:0.24, y:0.88, z:0.1,  r:0.22 },
                { x:-0.2, y:0.88, z:0.12, r:0.20 },
                { x:0.1,  y:0.88, z:-0.22,r:0.21 },
                { x:-0.12,y:0.88, z:-0.2, r:0.19 },
            ];
            headData.forEach(h => {
                const head = new THREE.Mesh(new THREE.SphereGeometry(h.r, 8, 7), headMat);
                head.position.set(h.x, h.y, h.z); g.add(head);
            });
            return g;
        }

        function updateObjectPositionsDisplay() {
            const list = document.getElementById('objects-list');
            const oc = document.getElementById('hud-obj-count'); if (oc) oc.textContent = objects.length;
            if (objects.length === 0) {
                list.innerHTML = '<div class="text-xs text-zinc-500 italic">No objects on board</div>';
                return;
            }
            let html = '';
            objects.forEach((obj, idx) => {
                const x = Math.floor(obj.position.x), z = Math.floor(obj.position.z);
                const letter = String.fromCharCode(65 + x), num = z + 1;
                const coord = `${letter}${num}`;
                const type = objectTypes.get(obj) || 'Unknown';
                const displayName = objectNames.get(obj) || type;
                let colorClass = 'text-zinc-300';
                if (type.includes('bottle')) colorClass = 'text-blue-400';
                else if (type.includes('box')) colorClass = 'text-amber-400';
                else if (type.includes('mug')) colorClass = 'text-amber-300';
                else if (type.includes('book')) colorClass = 'text-indigo-400';
                else if (type.includes('plant')) colorClass = 'text-green-400';
                else if (type.includes('wooden')) colorClass = 'text-orange-600';
                else if (type.includes('water_cup')) colorClass = 'text-cyan-400';
                else if (type.includes('powder')) colorClass = 'text-yellow-600';
                else if (type.includes('plate')) colorClass = 'text-gray-300';
                else if (type.includes('glass')) colorClass = 'text-cyan-300';
                else if (type.includes('stl') || type.includes('_')) colorClass = 'text-blue-300';
                else colorClass = 'text-purple-400';
                const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
                const touchList = getTouchingCoordinates(x, z, fp.w, fp.h);
                const st = objectState.get(obj) || {};
                const weight = objectWeight.get(obj);
                const stBits = [];
                if ('isOpen' in st) stBits.push(st.isOpen ? 'open' : 'closed');
                if ('power' in st) stBits.push(st.power ? 'ON' : 'OFF');
                if ('temperature' in st) stBits.push(st.temperature);
                if ('fillLevel' in st) stBits.push(`${Math.round(st.fillLevel * 100)}% full`);
                if ('capOn' in st) stBits.push(st.capOn ? 'cap on' : 'cap off');
                if ('dirty' in st && st.dirty > 0.05) stBits.push(`${Math.round(st.dirty * 100)}% dirty`);
                if (st.sliced) stBits.push(`sliced x${st.pieces}`);
                stBits.push(`wt ${weight}`);
                const fpLabel = (fp.w > 1 || fp.h > 1) ? ` · ${fp.w}x${fp.h}` : '';
                html += `<div class="bg-zinc-800/50 border border-zinc-700/40 rounded-lg p-3 hover:bg-zinc-800 transition-colors">
                    <div class="flex items-center justify-between">
                        <div>
                            <div class="text-sm font-bold ${colorClass}">${displayName}</div>
                            <div class="text-xs text-zinc-500 mono">ID: ${idx} · ${type}${fpLabel}</div>
                        </div>
                        <div class="text-right">
                            <div class="text-lg font-bold text-blue-400 mono">${coord}</div>
                            <div class="text-xs text-zinc-500 mono">(${obj.position.x.toFixed(1)}, ${obj.position.z.toFixed(1)})</div>
                        </div>
                    </div>
                    <div class="text-xs text-zinc-600 mono mt-1.5 pt-1.5 border-t border-zinc-700/30">Touching: ${touchList.join(', ')}</div>
                    <div class="text-xs text-zinc-500 mono mt-1">State: ${stBits.join(' · ')}</div>
                </div>`;
            });
            list.innerHTML = html;
        }

        let updateCounter = 0;
        function animate() {
            requestAnimationFrame(animate);
            renderer.render(scene, camera);
            updateCounter++;
            if (updateCounter % 10 === 0) {
                updateObjectPositionsDisplay();
                objects.forEach(obj => {
                    const sprite = objectSprites.get(obj);
                    if (sprite && obj !== heldObject) {
                        sprite.position.set(obj.position.x, obj.position.y + 2.2, obj.position.z);
                    }
                });
            }
        }

        window.takeTopDownScreenshot = function() {
            const PAD = 0.3;
            const PANEL_W = 340, FOOTER_H = 90, CELL_PX = 56;
            const GRID_PX_W = Math.round(GRID_WIDTH * CELL_PX);
            const GRID_PX_H = Math.round(GRID_HEIGHT * CELL_PX);
            const TOTAL_W = GRID_PX_W + PANEL_W;
            const TOTAL_H = GRID_PX_H + FOOTER_H;
            const shotRenderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
            shotRenderer.setSize(GRID_PX_W, GRID_PX_H);
            shotRenderer.setPixelRatio(1);
            const cx = GRID_WIDTH / 2, cz = GRID_HEIGHT / 2;
            const orthoCamera = new THREE.OrthographicCamera(
                -(cx + PAD), cx + PAD, cz + PAD, -(cz + PAD), 0.1, 300
            );
            orthoCamera.position.set(cx, 100, cz);
            orthoCamera.lookAt(new THREE.Vector3(cx, 0, cz));
            orthoCamera.up.set(0, 0, -1);
            orthoCamera.updateProjectionMatrix();
            const armParts = [xRail, yCarriage, zRailGroup];
            armParts.forEach(p => { p.visible = false; });
            const savedBg = scene.background;
            scene.background = new THREE.Color(0x09090b);
            shotRenderer.render(scene, orthoCamera);
            armParts.forEach(p => { p.visible = true; });
            scene.background = savedBg;
            const canvas2d = document.createElement('canvas');
            canvas2d.width = TOTAL_W; canvas2d.height = TOTAL_H;
            const ctx = canvas2d.getContext('2d');
            ctx.fillStyle = '#09090b';
            ctx.fillRect(0, 0, TOTAL_W, TOTAL_H);
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, 0, 0, GRID_PX_W, GRID_PX_H);
                const px = GRID_PX_W, pw = PANEL_W;
                ctx.fillStyle = '#18181b';
                ctx.fillRect(px, 0, pw, GRID_PX_H);
                ctx.strokeStyle = '#3f3f46'; ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, GRID_PX_H); ctx.stroke();
                ctx.fillStyle = '#ffffff';
                ctx.font = 'bold 13px monospace';
                ctx.fillText('OBJECT POSITIONS', px + 20, 36);
                ctx.strokeStyle = '#27272a'; ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(px + 12, 48); ctx.lineTo(px + pw - 12, 48); ctx.stroke();
                const colorMap = {
                    bottle: '#60a5fa', box: '#fbbf24', mug: '#fcd34d', book: '#818cf8',
                    plant: '#4ade80', wooden_box: '#ea580c', wooden: '#ea580c',
                    water_cup: '#22d3ee', powder_box: '#ca8a04', powder: '#ca8a04',
                    plate: '#d4d4d8', glass: '#67e8f9'
                };
                function objColor(type) {
                    for (const k of Object.keys(colorMap)) { if (type.includes(k)) return colorMap[k]; }
                    return '#93c5fd';
                }
                let rowY = 68;
                objects.forEach((obj, idx) => {
                    const x = Math.floor(obj.position.x), z = Math.floor(obj.position.z);
                    const coord = String.fromCharCode(65 + x) + (z + 1);
                    const type = objectTypes.get(obj) || 'Unknown';
                    const name = objectNames.get(obj) || type;
                    const col = objColor(type);
                    ctx.fillStyle = '#27272a';
                    roundRect(ctx, px + 12, rowY, pw - 24, 68, 10);
                    ctx.fill();
                    ctx.fillStyle = col;
                    ctx.font = 'bold 15px monospace';
                    ctx.fillText(name.substring(0, 14), px + 20, rowY + 22);
                    ctx.fillStyle = col; ctx.font = 'bold 24px monospace';
                    ctx.textAlign = 'right';
                    ctx.fillText(coord, px + pw - 20, rowY + 26);
                    ctx.textAlign = 'left';
                    ctx.fillStyle = '#71717a'; ctx.font = '11px monospace';
                    ctx.fillText('ID: ' + idx + ' · ' + type.substring(0, 14), px + 20, rowY + 44);
                    ctx.fillStyle = '#52525b'; ctx.font = '11px monospace';
                    ctx.textAlign = 'right';
                    ctx.fillText('(' + obj.position.x.toFixed(1) + ', ' + obj.position.z.toFixed(1) + ')', px + pw - 20, rowY + 44);
                    ctx.textAlign = 'left';
                    rowY += 80;
                });
                if (objects.length === 0) {
                    ctx.fillStyle = '#52525b'; ctx.font = 'italic 13px monospace';
                    ctx.fillText('No objects on board', px + 20, 80);
                }
                ctx.fillStyle = '#09090b';
                ctx.fillRect(0, GRID_PX_H, TOTAL_W, FOOTER_H);
                ctx.strokeStyle = '#27272a'; ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(0, GRID_PX_H); ctx.lineTo(TOTAL_W, GRID_PX_H); ctx.stroke();
                ctx.fillStyle = '#93c5fd'; ctx.font = 'bold 16px monospace';
                ctx.fillText('K5D Prolabs V12.2 · Top-Down View · ' + new Date().toLocaleString(), 16, GRID_PX_H + 32);
                ctx.fillStyle = '#52525b'; ctx.font = '12px monospace';
                let summary = objects.map(o => {
                    const n = objectNames.get(o) || objectTypes.get(o) || '?';
                    const x = Math.floor(o.position.x), z = Math.floor(o.position.z);
                    return n + '@' + String.fromCharCode(65 + x) + (z + 1);
                }).join(' ');
                ctx.fillText((summary || 'No objects on board').substring(0, 180), 16, GRID_PX_H + 60);
                const a = document.createElement('a');
                a.href = canvas2d.toDataURL('image/png');
                a.download = 'k3d_' + Date.now() + '.png';
                a.click();
                shotRenderer.dispose();
                setStatus('📸 Screenshot saved');
            };
            img.src = shotRenderer.domElement.toDataURL('image/png');
        };
        function roundRect(ctx, x, y, w, h, r) {
            ctx.beginPath();
            ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y);
            ctx.quadraticCurveTo(x + w, y, x + w, y + r);
            ctx.lineTo(x + w, y + h - r);
            ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
            ctx.lineTo(x + r, y + h);
            ctx.quadraticCurveTo(x, y + h, x, y + h - r);
            ctx.lineTo(x, y + r);
            ctx.quadraticCurveTo(x, y, x + r, y);
            ctx.closePath();
        }

        function getBoardContext() {
            const objs = objects.map((o, i) => {
                const x = Math.floor(o.position.x), z = Math.floor(o.position.z);
                const name = objectNames.get(o) || objectTypes.get(o) || 'unknown';
                const fp = objectFootprint.get(o) || { w: 1, h: 1 };
                const touching = getTouchingCoordinates(x, z, fp.w, fp.h);
                const st = objectState.get(o) || {};
                const weight = objectWeight.get(o);
                const stateParts = [];
                if ('isOpen' in st) stateParts.push(st.isOpen ? 'open' : 'closed');
                if ('power' in st) stateParts.push(st.power ? 'power ON' : 'power OFF');
                if ('temperature' in st) stateParts.push(`temp:${st.temperature}`);
                if ('fillLevel' in st) stateParts.push(`fill:${Math.round(st.fillLevel * 100)}%`);
                if ('capOn' in st) stateParts.push(st.capOn ? 'cap ON' : 'cap OFF');
                if ('dirty' in st && st.dirty > 0.05) stateParts.push(`dirty:${Math.round(st.dirty * 100)}%`);
                if (st.sliced) stateParts.push(`sliced x${st.pieces}`);
                stateParts.push(`weight:${weight}${weight > MAX_LIFT_WEIGHT ? '(too heavy to lift, drag instead)' : ''}`);
                const footprintStr = (fp.w > 1 || fp.h > 1) ? ` [${fp.w}x${fp.h} footprint]` : '';
                return `${name} at ${String.fromCharCode(65 + x)}${z + 1}${footprintStr} {${stateParts.join(', ')}} (touching: ${touching.join(', ')})`;
            });
            return `Gantry at ${String.fromCharCode(65 + Math.round(currentX))}${Math.round(currentY) + 1}, Z=${currentZ.toFixed(1)}. ` +
                `Gripper: ${gripperOpen ? 'OPEN' : 'CLOSED'}. ` +
                `Holding: ${heldObject ? (objectNames.get(heldObject) || objectTypes.get(heldObject) || 'object') : 'nothing'}. ` +
                `Dragging: ${draggingObject ? (objectNames.get(draggingObject) || objectTypes.get(draggingObject) || 'object') : 'nothing'}. ` +
                `Objects on board: ${objs.length ? objs.join(' | ') : 'none'}.`;
        }

        function appendMessage(role, text) {
            const box = document.getElementById('chat-messages');
            const wrap = document.createElement('div');
            wrap.className = 'flex gap-2' + (role === 'user' ? ' justify-end' : '');
            if (role === 'assistant') {
                wrap.innerHTML = '<div class="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">AI</div>' +
                    '<div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-300 leading-relaxed max-w-xs">' + text + '</div>';
            } else {
                wrap.innerHTML = '<div class="bg-blue-600 rounded-xl rounded-tr-sm px-3 py-2 text-xs text-white leading-relaxed max-w-xs">' + text + '</div>';
            }
            box.appendChild(wrap);
            box.scrollTop = box.scrollHeight;
        }
        function appendThinking() {
            const box = document.getElementById('chat-messages');
            const wrap = document.createElement('div');
            wrap.id = 'thinking-bubble';
            wrap.className = 'flex gap-2';
            wrap.innerHTML = '<div class="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">AI</div>' +
                '<div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-500 italic">Planning task...</div>';
            box.appendChild(wrap);
            box.scrollTop = box.scrollHeight;
        }

        function showExecLog(commands) {
            const logDiv = document.getElementById('exec-log');
            const entries = document.getElementById('exec-log-entries');
            logDiv.style.display = 'block';
            entries.innerHTML = '';
            commands.forEach((cmd, i) => {
                const div = document.createElement('div');
                div.id = `cmd-entry-${i}`;
                div.className = 'cmd-log-entry cmd-pending';
                div.textContent = `${i + 1}. ${cmd}`;
                entries.appendChild(div);
            });
        }
        function markCmdActive(i) {
            const el = document.getElementById(`cmd-entry-${i}`);
            if (el) { el.className = 'cmd-log-entry cmd-active'; el.scrollIntoView({ block: 'nearest' }); }
        }
        function markCmdDone(i) {
            const el = document.getElementById(`cmd-entry-${i}`);
            if (el) el.className = 'cmd-log-entry cmd-done';
        }
        function updateProgress(done, total) {
            document.getElementById('task-progress').classList.remove('hidden');
            document.getElementById('task-step-counter').textContent = `${done}/${total}`;
            document.getElementById('task-progress-bar').style.width = total > 0 ? `${(done / total) * 100}%` : '0%';
        }
        function hideProgress() {
            document.getElementById('task-progress').classList.add('hidden');
            document.getElementById('exec-log').style.display = 'none';
        }

        function moveTo(col, row) {
            return new Promise(resolve => {
                const targetX = colLetterToX(col);
                const targetY = rowNumberToY(row);
                if (targetX === null || targetY === null) { resolve(); return; }
                isAnimating = true;
                const waypoint = findClearPath(currentX, currentY, targetX, targetY);
                const finalLeg = () => {
                    setStatus(`<span class="w-2 h-2 bg-blue-400 rounded-full inline-block animate-pulse"></span>&nbsp;Moving to ${col.toUpperCase()}${row}...`);
                    animateXY(targetX, targetY, 500, () => { isAnimating = false; resolve(); });
                };
                if (waypoint === 'blocked') {
                    appendMessage('assistant', `⚠️ No clear route to ${col.toUpperCase()}${row} around obstacles — moving directly anyway.`);
                    finalLeg();
                } else if (waypoint) {
                    setStatus(`<span class="w-2 h-2 bg-blue-400 rounded-full inline-block animate-pulse"></span>&nbsp;Routing around obstacle...`);
                    animateXY(waypoint.x, waypoint.y, 350, finalLeg);
                } else {
                    finalLeg();
                }
            });
        }
        function pickup() {
            return new Promise(resolve => {
                const obj = getObjectAtCurrentCell();
                if (!obj) {
                    setStatus('⚠️ No object found at cell');
                    appendMessage('assistant', '⚠️ No object at target cell — skipping pickup.');
                    resolve(); return;
                }
                const weight = objectWeight.get(obj) ?? 2;
                if (weight > MAX_LIFT_WEIGHT) {
                    const label = objectNames.get(obj) || objectTypes.get(obj) || 'object';
                    setStatus(`⚠️ Too heavy to lift (weight ${weight})`);
                    appendMessage('assistant', `⚠️ "${label}" is too heavy to lift directly (weight ${weight}, limit ${MAX_LIFT_WEIGHT}). Use {drag_from_coordinate(...)_to_coordinate(...)} to slide it instead.`);
                    resolve(); return;
                }
                // If this object was inside a container, remove it from that container
                const srcState = objectState.get(obj) || {};
                if (srcState.inContainer) {
                    const containerName = srcState.inContainer;
                    const container = findObjectByKey(containerName);
                    if (container) {
                        const cState = objectState.get(container) || {};
                        const label = objectNames.get(obj) || objectTypes.get(obj) || 'object';
                        if (cState.contents) {
                            const items = cState.contents.split(', ').filter(s => s !== label);
                            cState.contents = items.join(', ') || null;
                        }
                        objectState.set(container, cState);
                    }
                    delete srcState.inContainer;
                    objectState.set(obj, srcState);
                }
                isAnimating = true; setStatus('Picking up...');
                animateGripper(true, 200, () => {
                    animateZ(currentZ, 5.8, 600, () => {
                        animateGripper(false, 300, () => {
                            heldObject = obj; setStatus('Lifting...');
                            animateZ(currentZ, 2.5, 600, () => {
                                isAnimating = false; setStatus('✅ Holding object');
                                resolve();
                            });
                        });
                    });
                });
            });
        }
        function placeDown() {
            return new Promise(resolve => {
                if (!heldObject) {
                    setStatus('⚠️ Not holding anything');
                    appendMessage('assistant', '⚠️ Not holding any object — skipping place.');
                    resolve(); return;
                }
                isAnimating = true; setStatus('Placing...');
                animateZ(currentZ, 5.8, 600, () => {
                    heldObject.position.set(Math.round(currentX) + 0.5, 0.5, Math.round(currentY) + 0.5);
                    const sprite = objectSprites.get(heldObject);
                    if (sprite) { sprite.position.x = heldObject.position.x; sprite.position.z = heldObject.position.z; sprite.position.y = heldObject.position.y + 2.2; }
                    animateGripper(true, 300, () => {
                        heldObject = null;
                        animateZ(currentZ, 3.0, 500, () => { isAnimating = false; setStatus('✅ Object placed'); resolve(); });
                    });
                });
            });
        }
        function pourAction() {
            return new Promise(resolve => {
                const target = heldObject || getObjectAtCurrentCell();
                if (!target) { resolve(); return; }
                isAnimating = true; heldObject = target;
                animateTilt(0, 135, 600, () => {
                    setTimeout(() => {
                        animateTilt(135, 0, 500, () => {
                            target.rotation.x = 0; isAnimating = false;
                            setStatus('✅ Pour complete');
                            resolve();
                        });
                    }, 1000);
                });
            });
        }

        function dragTo(fromCol, fromRow, toCol, toRow) {
            return new Promise(async resolve => {
                await moveTo(fromCol, fromRow);
                const obj = getObjectAtCurrentCell();
                if (!obj) {
                    setStatus('⚠️ No object found at cell');
                    appendMessage('assistant', '⚠️ No object at source cell — skipping drag.');
                    resolve(); return;
                }
                const targetX = colLetterToX(toCol);
                const targetY = rowNumberToY(toRow);
                if (targetX === null || targetY === null) {
                    setStatus('⚠️ Invalid drag destination');
                    appendMessage('assistant', '⚠️ Invalid drag destination coordinate — skipping drag.');
                    resolve(); return;
                }
                if (isCellOccupied(targetX, targetY, obj)) {
                    setStatus('⚠️ Destination cell occupied');
                    appendMessage('assistant', `⚠️ ${toCol.toUpperCase()}${toRow} is already occupied by another object — skipping drag.`);
                    resolve(); return;
                }
                isAnimating = true; setStatus(`🖐️ Dragging to ${toCol.toUpperCase()}${toRow}...`);
                animateZ(currentZ, 5.8, 600, () => {
                    animateGripper(false, 250, () => {
                        draggingObject = obj;
                        animateXY(targetX, targetY, 750, () => {
                            animateGripper(true, 250, () => {
                                draggingObject = null;
                                animateZ(currentZ, 3.0, 500, () => {
                                    isAnimating = false;
                                    setStatus('✅ Drag complete');
                                    resolve();
                                });
                            });
                        });
                    });
                });
            });
        }

        // --- Generic object-state commands: open/close, power, cap, fill, pour_into, slice,
        //     set_state (escape hatch), check_state (sensing), wait_for, find (attribute search) ---
        const OPEN_RE = /^open\s*\(\s*([^)]+?)\s*\)$/i;
        const CLOSE_RE = /^close\s*\(\s*([^)]+?)\s*\)$/i;
        const TURN_ON_RE = /^turn_on\s*\(\s*([^)]+?)\s*\)$/i;
        const TURN_OFF_RE = /^turn_off\s*\(\s*([^)]+?)\s*\)$/i;
        const TWIST_CAP_RE = /^twist_cap\s*\(\s*([^,]+?)\s*,\s*(on|off)\s*\)$/i;
        const FILL_RE = /^fill\s*\(\s*([^,]+?)\s*,\s*(\d+)\s*\)$/i;
        const POUR_INTO_RE = /^pour_into\s*\(\s*([^)]+?)\s*\)$/i;
        const PLACE_INTO_RE = /^place_into\s*\(\s*([^)]+?)\s*\)$/i;
        const SLICE_RE = /^slice\s*\(\s*([^,]+?)\s*,\s*(\d+)\s*\)$/i;
        const SET_STATE_RE = /^set_state\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^)]+?)\s*\)$/i;
        const CHECK_STATE_RE = /^check_state\s*\(\s*([^)]+?)\s*\)$/i;
        const WAIT_FOR_RE = /^wait_for\s*\(\s*(\d+(?:\.\d+)?)\s*\)$/i;
        const FIND_RE = /^find\s*\(\s*([a-z_]+)\s*[=,]\s*([^)]+?)\s*\)$/i;
        const SWEEP_RE = /^sweep\s*\(\s*([A-T]\d+(?:\s*,\s*[A-T]\d+)*)\s*\)$/i;
        const MOP_RE = /^mop\s*\(\s*([A-T]\d+(?:\s*,\s*[A-T]\d+)*)\s*\)$/i;
        const SCRUB_RE = /^scrub\s*\(\s*([A-T]\d+(?:\s*,\s*[A-T]\d+)*)\s*\)$/i;
        const WASH_RE = /^wash\s*\(\s*([^)]+?)\s*\)$/i;
        const RUN_CYCLE_RE = /^run_cycle\s*\(\s*([^)]+?)\s*\)$/i;
        const IRON_RE = /^iron\s*\(\s*([^)]+?)\s*\)$/i;
        const FOLD_RE = /^fold\s*\(\s*([^)]+?)\s*\)$/i;
        const ROTATE_OBJECT_RE = /^rotate_object\s*\(\s*([^,]+?)\s*,\s*([+-][xyz]90)\s*\)$/i;

        // Helper to parse a comma-separated list of cell IDs e.g. "A1,B3,C4"
        function parseCellList(str) {
            return str.split(',').map(s => s.trim().toUpperCase()).filter(s => /^[A-T]\d+$/.test(s));
        }

        // Sweep: move broom/gripper across cells, reduce dust on objects there
        async function runSweep(raw) {
            const m = raw.match(SWEEP_RE);
            if (!m) { setStatus('⚠️ Invalid sweep command'); return; }
            const cells = parseCellList(m[1]);
            const hasBroom = objects.some(o => (objectTypes.get(o) || '').toLowerCase().includes('broom'));
            if (!hasBroom) { appendMessage('assistant', '⚠️ No broom on board — add one first.'); return; }
            setStatus(`🧹 Sweeping ${cells.length} cell(s)...`);
            for (const cell of cells) {
                const col = cell[0], row = cell.slice(1);
                await moveTo(col, row);
                isAnimating = true;
                const bx = currentX, by = currentY;
                await new Promise(res => animateXY(bx + 0.35, by, 120, () => animateXY(bx - 0.35, by, 120, () => animateXY(bx, by, 100, res))));
                isAnimating = false;
                reduceDirtAtCell(col, row, 0.45);
            }
            setStatus('✅ Sweep complete');
        }

        // Mop: wet-mop cells, needs disinfectant or bucket
        async function runMop(raw) {
            const m = raw.match(MOP_RE);
            if (!m) { setStatus('⚠️ Invalid mop command'); return; }
            const cells = parseCellList(m[1]);
            const hasMop = objects.some(o => (objectTypes.get(o) || '').toLowerCase().includes('mop'));
            if (!hasMop) { appendMessage('assistant', '⚠️ No mop on board — add one first.'); return; }
            const bucketObj = objects.find(o => (objectTypes.get(o) || '').toLowerCase().includes('bucket'));
            const hasSolution = bucketObj && (objectState.get(bucketObj) || {}).fillLevel > 0;
            if (!hasSolution) appendMessage('assistant', '⚠️ Bucket is empty or missing — fill with water + disinfectant for best results. Mopping dry anyway.');
            setStatus(`🧹 Mopping ${cells.length} cell(s)...`);
            for (const cell of cells) {
                const col = cell[0], row = cell.slice(1);
                await moveTo(col, row);
                isAnimating = true;
                const bx = currentX, by = currentY;
                await new Promise(res => {
                    animateXY(bx + 0.3, by + 0.3, 120, () =>
                    animateXY(bx - 0.3, by - 0.3, 120, () =>
                    animateXY(bx + 0.3, by - 0.3, 120, () =>
                    animateXY(bx - 0.3, by + 0.3, 120, () =>
                    animateXY(bx, by, 100, res)))));
                });
                isAnimating = false;
                reduceDirtAtCell(col, row, hasSolution ? 0.65 : 0.3);
            }
            if (hasSolution && bucketObj) {
                const st = objectState.get(bucketObj); st.fillLevel = Math.max(0, st.fillLevel - 0.05 * cells.length);
                objectState.set(bucketObj, st);
            }
            setStatus('✅ Mop complete');
            updateObjectPositionsDisplay();
        }

        // Scrub: heavy-duty scrubbing (bathroom, toilet, tiles)
        async function runScrub(raw) {
            const m = raw.match(SCRUB_RE);
            if (!m) { setStatus('⚠️ Invalid scrub command'); return; }
            const cells = parseCellList(m[1]);
            const hasBrush = objects.some(o => {
                const t = (objectTypes.get(o) || '').toLowerCase();
                return t.includes('scrub') || t.includes('toilet_brush');
            });
            if (!hasBrush) { appendMessage('assistant', '⚠️ No scrub brush or toilet brush on board — add one first.'); return; }
            setStatus(`🪥 Scrubbing ${cells.length} cell(s)...`);
            for (const cell of cells) {
                const col = cell[0], row = cell.slice(1);
                await moveTo(col, row);
                isAnimating = true;
                const bx = currentX, by = currentY;
                for (let i = 0; i < 3; i++) {
                    await new Promise(res => animateXY(bx + 0.2, by, 80, () => animateXY(bx - 0.2, by, 80, () => animateXY(bx, by, 60, res))));
                }
                isAnimating = false;
                reduceDirtAtCell(col, row, 0.85);
            }
            setStatus('✅ Scrub complete');
        }

        // Wash: wash an object (utensil, cloth, basket) to remove dirty state
        async function runWash(raw) {
            const m = raw.match(WASH_RE);
            if (!m) { setStatus('⚠️ Invalid wash command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const sinkObj = objects.find(o => (objectTypes.get(o) || '').toLowerCase().includes('sink'));
            const sinkFull = sinkObj && (objectState.get(sinkObj) || {}).fillLevel > 0;
            if (!sinkFull) appendMessage('assistant', '⚠️ Sink is empty — use {fill(sink, 100)} first for soapy water. Washing anyway.');
            const name = objectNames.get(obj) || objectTypes.get(obj) || 'object';
            const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
            const col = String.fromCharCode(65 + ox), row = String(oz + 1);
            await moveTo(col, row);
            isAnimating = true;
            setStatus(`🚿 Washing ${name}...`);
            await new Promise(res => {
                animateZ(currentZ, 5.2, 400, () => {
                    setTimeout(() => {
                        const st = objectState.get(obj) || {};
                        st.dirty = 0;
                        objectState.set(obj, st);
                        updateObjectPositionsDisplay();
                        animateZ(currentZ, 3.0, 350, res);
                    }, 700);
                });
            });
            isAnimating = false;
            setStatus(`✅ ${name} is now clean`);
            appendMessage('assistant', `✅ Washed "${name}" — dirty level reset to 0.`);
        }

        // run_cycle: run a machine cycle (washing_machine = clean clothes inside)
        async function runCycle(raw) {
            const m = raw.match(RUN_CYCLE_RE);
            if (!m) { setStatus('⚠️ Invalid run_cycle command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const name = objectNames.get(obj) || objectTypes.get(obj) || 'machine';
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('switchable')) { appendMessage('assistant', `⚠️ "${name}" is not a machine that runs cycles.`); return; }
            const st = objectState.get(obj) || {};
            if (st.isOpen) { appendMessage('assistant', `⚠️ ${name} door is open — close it first before running a cycle.`); return; }
            setStatus(`⚙️ Running ${name} cycle...`);
            appendMessage('assistant', `⚙️ ${name} cycle started. This will take a moment...`);
            st.cycleRunning = true; st.power = true;
            objectState.set(obj, st); updateObjectPositionsDisplay();
            await delay(4000);
            st.cycleRunning = false; st.cycleComplete = true; st.power = false;
            // find all clothes inside (any clothes_pile on same cell or adjacent)
            const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
            let washed = 0;
            for (const o of objects) {
                const t = (objectTypes.get(o) || '').toLowerCase();
                if (t.includes('clothes') || t.includes('towel')) {
                    const cx = Math.floor(o.position.x), cz = Math.floor(o.position.z);
                    if (Math.abs(cx - ox) <= 1 && Math.abs(cz - oz) <= 1) {
                        const cs = objectState.get(o) || {};
                        cs.dirty = 0; cs.wrinkled = true; // washed but now wrinkled
                        objectState.set(o, cs); washed++;
                    }
                }
            }
            objectState.set(obj, st); updateObjectPositionsDisplay();
            setStatus(`✅ ${name} cycle complete`);
            appendMessage('assistant', `✅ ${name} cycle finished — ${washed} item(s) washed clean (now wrinkled, needs ironing).`);
        }

        // iron: iron a cloth item to remove wrinkles
        async function runIron(raw) {
            const m = raw.match(IRON_RE);
            if (!m) { setStatus('⚠️ Invalid iron command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('ironable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot be ironed.`); return; }
            const ironObj = objects.find(o => (objectTypes.get(o) || '').toLowerCase() === 'iron');
            if (!ironObj) { appendMessage('assistant', '⚠️ No iron on board — add one first.'); return; }
            const ironSt = objectState.get(ironObj) || {};
            if (!ironSt.power) { appendMessage('assistant', '⚠️ Iron is not powered on — use {turn_on(iron)} and wait for it to heat first.'); return; }
            if (ironSt.temperature !== 'hot') { appendMessage('assistant', '⚠️ Iron is not hot yet — use {wait_for(3)} to let it heat up.'); return; }
            const name = objectNames.get(obj) || objectTypes.get(obj) || 'item';
            const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
            const col = String.fromCharCode(65 + ox), row = String(oz + 1);
            await moveTo(col, row);
            isAnimating = true;
            setStatus(`🪄 Ironing ${name}...`);
            const bx = currentX, by = currentY;
            for (let i = 0; i < 4; i++) {
                await new Promise(res => animateXY(bx + 0.4, by, 150, () => animateXY(bx - 0.4, by, 150, res)));
                await new Promise(res => animateXY(bx, by + 0.3, 100, res));
            }
            await new Promise(res => animateXY(bx, by, 120, res));
            isAnimating = false;
            const st = objectState.get(obj) || {};
            st.wrinkled = false; st.ironed = true;
            objectState.set(obj, st); updateObjectPositionsDisplay();
            setStatus(`✅ ${name} ironed`);
            appendMessage('assistant', `✅ "${name}" is now wrinkle-free and ironed.`);
        }

        // fold: fold a foldable item
        async function runRotateObject(raw) {
            const m = raw.match(ROTATE_OBJECT_RE);
            if (!m) { setStatus('⚠️ Invalid rotate_object command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const token = m[2].toLowerCase();
            const sign = token[0] === '+' ? 1 : -1;
            const axis = token[1];
            const rad = sign * Math.PI / 2;
            const axisVec = new THREE.Vector3(axis === 'x' ? 1 : 0, axis === 'y' ? 1 : 0, axis === 'z' ? 1 : 0);
            const delta = new THREE.Quaternion().setFromAxisAngle(axisVec, rad);
            const startQ = obj.quaternion.clone();
            const endQ = obj.quaternion.clone().premultiply(delta);
            const name = objectNames.get(obj) || objectTypes.get(obj) || m[1];
            setStatus(`🔄 Rotating ${name}...`);
            isAnimating = true;
            await new Promise(res => {
                const start = Date.now(), dur = 450;
                function step() {
                    const t = Math.min(1, (Date.now() - start) / dur);
                    const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
                    obj.quaternion.slerpQuaternions(startQ, endQ, e);
                    if (t < 1) requestAnimationFrame(step); else res();
                }
                step();
            });
            isAnimating = false;
            setStatus(`✅ ${name} rotated ${token.toUpperCase()}`);
            appendMessage('assistant', `✅ "${name}" rotated ${token.toUpperCase()} — new face is now accessible from above.`);
        }

        async function runFold(raw) {
            const m = raw.match(FOLD_RE);
            if (!m) { setStatus('⚠️ Invalid fold command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('foldable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot be folded.`); return; }
            const st = objectState.get(obj) || {};
            if (st.wrinkled) appendMessage('assistant', `⚠️ "${m[1]}" is still wrinkled — iron it first for a crisp neat fold.`);
            const name = objectNames.get(obj) || objectTypes.get(obj) || 'item';
            const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
            const col = String.fromCharCode(65 + ox), row = String(oz + 1);
            await moveTo(col, row);
            setStatus(`👕 Folding ${name}...`);
            isAnimating = true;
            const sx = obj.scale.x, sy = obj.scale.y, sz = obj.scale.z;
            const bx = currentX, by = currentY;
            // Phase 1: gripper sweeps to one edge, folds the garment along Z
            await new Promise(res => animateXY(bx - 0.45, by, 200, res));
            await new Promise(res => {
                const start = Date.now(), dur = 520;
                function step() {
                    const t = Math.min(1, (Date.now() - start) / dur);
                    const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
                    obj.scale.z = sz * (1 - e * 0.5);
                    obj.scale.y = sy * (1 + e * 0.5);
                    if (t < 1) requestAnimationFrame(step); else res();
                }
                step();
            });
            await new Promise(res => animateXY(bx, by, 150, res));
            await delay(100);
            // Phase 2: gripper sweeps front-to-back, folds along X
            await new Promise(res => animateXY(bx, by - 0.45, 200, res));
            await new Promise(res => {
                const start = Date.now(), dur = 520;
                function step() {
                    const t = Math.min(1, (Date.now() - start) / dur);
                    const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
                    obj.scale.x = sx * (1 - e * 0.45);
                    obj.scale.y = sy * (1 + e * 0.3);
                    if (t < 1) requestAnimationFrame(step); else res();
                }
                step();
            });
            await new Promise(res => animateXY(bx, by, 120, res));
            isAnimating = false;
            st.folded = true;
            objectState.set(obj, st);
            updateObjectPositionsDisplay();
            setStatus(`✅ ${name} folded neatly`);
            appendMessage('assistant', `✅ "${name}" folded — now compact and stack-ready.`);
        }

        async function runOpenClose(raw, open) {
            const m = raw.match(open ? OPEN_RE : CLOSE_RE);
            if (!m) { setStatus('⚠️ Invalid open/close command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('openable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot be opened/closed (not openable).`); return; }
            const st = objectState.get(obj) || {};
            st.isOpen = open;
            objectState.set(obj, st);
            updateObjectPositionsDisplay();
            setStatus(`✅ ${open ? 'Opened' : 'Closed'} ${m[1]}`);
        }

        async function runPower(raw, on) {
            const m = raw.match(on ? TURN_ON_RE : TURN_OFF_RE);
            if (!m) { setStatus('⚠️ Invalid power command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('switchable')) { appendMessage('assistant', `⚠️ "${m[1]}" has no power switch.`); return; }
            const st = objectState.get(obj) || {};
            st.power = on;
            if (on && cfg.affordances.includes('heatable')) {
                st.temperature = 'preheating';
                objectState.set(obj, st);
                setStatus(`🔌 ${m[1]} powering on — preheating...`);
                setTimeout(() => {
                    const cur = objectState.get(obj);
                    if (cur && cur.power) {
                        cur.temperature = 'hot'; objectState.set(obj, cur); updateObjectPositionsDisplay();
                        appendMessage('assistant', `🌡️ ${m[1]} has finished preheating and is now HOT.`);
                    }
                }, 4000);
            } else if (!on && cfg.affordances.includes('heatable')) {
                st.temperature = 'room';
            }
            objectState.set(obj, st);
            updateObjectPositionsDisplay();
            setStatus(`✅ ${m[1]} powered ${on ? 'ON' : 'OFF'}`);
        }

        async function runTwistCap(raw) {
            const m = raw.match(TWIST_CAP_RE);
            if (!m) { setStatus('⚠️ Invalid twist_cap command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('twistable_cap')) { appendMessage('assistant', `⚠️ "${m[1]}" has no twist-cap.`); return; }
            const st = objectState.get(obj) || {};
            st.capOn = (m[2].toLowerCase() === 'on');
            objectState.set(obj, st);
            updateObjectPositionsDisplay();
            setStatus(`✅ Cap ${st.capOn ? 'twisted on' : 'twisted off'} for ${m[1]}`);
        }

        async function runFill(raw) {
            const m = raw.match(FILL_RE);
            if (!m) { setStatus('⚠️ Invalid fill command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('fillable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot hold contents.`); return; }
            const pct = Math.max(0, Math.min(100, parseInt(m[2], 10)));
            const st = objectState.get(obj) || {};
            st.fillLevel = pct / 100;
            objectState.set(obj, st);
            updateObjectPositionsDisplay();
            setStatus(`✅ ${m[1]} filled to ${pct}%`);
        }

        function pourInto(targetName) {
            return new Promise(resolve => {
                const source = heldObject || getObjectAtCurrentCell();
                if (!source) { appendMessage('assistant', '⚠️ Nothing to pour from — pick up or position over a pourable object first.'); resolve(); return; }
                const target = findObjectByKey(targetName);
                if (!target) { appendMessage('assistant', `⚠️ No object named "${targetName}" found to pour into.`); resolve(); return; }
                const srcCfg = getObjectConfig(objectTypes.get(source));
                const tgtCfg = getObjectConfig(objectTypes.get(target));
                if (!srcCfg.affordances.includes('pourable')) { appendMessage('assistant', '⚠️ The held/current object cannot be poured.'); resolve(); return; }
                if (!tgtCfg.affordances.includes('fillable')) { appendMessage('assistant', `⚠️ "${targetName}" cannot receive contents.`); resolve(); return; }
                const srcState = objectState.get(source) || {};
                const tgtState = objectState.get(target) || {};
                if (srcCfg.affordances.includes('twistable_cap') && srcState.capOn) {
                    const label = objectNames.get(source) || objectTypes.get(source) || 'object';
                    appendMessage('assistant', `⚠️ Cap is still on — use {twist_cap(${label}, off)} before pouring.`);
                    resolve(); return;
                }
                isAnimating = true; heldObject = source;
                setStatus(`💧 Pouring into ${targetName}...`);
                animateTilt(0, 135, 600, () => {
                    setTimeout(() => {
                        const available = srcState.fillLevel ?? 0;
                        const room = 1 - (tgtState.fillLevel ?? 0);
                        const transfer = Math.min(available, room);
                        srcState.fillLevel = Math.max(0, available - transfer);
                        tgtState.fillLevel = Math.min(1, (tgtState.fillLevel ?? 0) + transfer);
                        objectState.set(source, srcState);
                        objectState.set(target, tgtState);
                        let msg = `✅ Poured ${(transfer * 100).toFixed(0)}% into ${targetName}.`;
                        if (transfer < available - 0.001) msg += ` ⚠️ ${targetName} is now full — ${((available - transfer) * 100).toFixed(0)}% remained in the source and may spill.`;
                        appendMessage('assistant', msg);
                        animateTilt(135, 0, 500, () => {
                            source.rotation.x = 0; isAnimating = false;
                            updateObjectPositionsDisplay();
                            setStatus('✅ Pour complete');
                            resolve();
                        });
                    }, 800);
                });
            });
        }

        function placeInto(targetName) {
            return new Promise(resolve => {
                const source = heldObject;
                if (!source) { appendMessage('assistant', '⚠️ Nothing to place — pick up an object first.'); resolve(); return; }
                const target = findObjectByKey(targetName);
                if (!target) { appendMessage('assistant', `⚠️ No object named "${targetName}" found.`); resolve(); return; }
                const tgtCfg = getObjectConfig(objectTypes.get(target));
                if (!tgtCfg.affordances.includes('fillable')) { appendMessage('assistant', `⚠️ "${targetName}" cannot hold contents.`); resolve(); return; }

                const srcLabel = objectNames.get(source) || objectTypes.get(source) || 'object';
                const tgtState = objectState.get(target) || {};

                // Count items already inside to stack them visually
                const itemsInside = objects.filter(o => (objectState.get(o) || {}).inContainer === targetName).length;
                const stackY = target.position.y + 0.15 + itemsInside * 0.12;

                const contents = tgtState.contents ? `${tgtState.contents}, ${srcLabel}` : srcLabel;
                tgtState.contents = contents;
                objectState.set(target, tgtState);

                const srcState = objectState.get(source) || {};
                srcState.inContainer = targetName;
                objectState.set(source, srcState);

                // Physically lower item into container
                isAnimating = true;
                setStatus(`📥 Placing ${srcLabel} into ${targetName}...`);
                const destX = target.position.x, destZ = target.position.z;
                animateXY(destX - 0.5, destZ - 0.5, 300, () => {
                    animateZ(currentZ, 5.5, 400, () => {
                        source.position.set(destX, stackY, destZ);
                        const sprite = objectSprites.get(source);
                        if (sprite) { sprite.position.x = destX; sprite.position.z = destZ; sprite.position.y = stackY + 2.2; }
                        animateGripper(true, 200, () => {
                            heldObject = null;
                            animateZ(currentZ, 2.5, 400, () => {
                                isAnimating = false;
                                appendMessage('assistant', `✅ Placed ${srcLabel} into ${targetName}. Contents: ${contents}`);
                                updateObjectPositionsDisplay();
                                setStatus('✅ Place complete');
                                resolve();
                            });
                        });
                    });
                });
            });
        }

        // Mutates an object's actual 3D geometry into N visibly separate flat pieces,
        // so slicing is a real visual change rather than only a state flag.
        function visualSlice(obj, n) {
            const meshes = [];
            obj.traverse(child => { if (child.isMesh) meshes.push(child); });
            if (meshes.length === 0) return;
            const pieces = [];
            for (let i = 0; i < n; i++) {
                const source = meshes[i % meshes.length];
                pieces.push(source.clone());
            }
            while (obj.children.length) obj.remove(obj.children[0]);
            const scale = Math.max(0.32, 1 / Math.sqrt(n));
            const ringRadius = 0.16 * Math.min(n + 1, 7);
            for (let i = 0; i < n; i++) {
                const piece = pieces[i];
                const angle = (i / n) * Math.PI * 2;
                piece.position.set(Math.cos(angle) * ringRadius, 0.05, Math.sin(angle) * ringRadius);
                piece.rotation.set(0, angle, 0);
                piece.scale.set(scale, scale, scale);
                obj.add(piece);
            }
        }

        async function runSlice(raw) {
            const m = raw.match(SLICE_RE);
            if (!m) { setStatus('⚠️ Invalid slice command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('sliceable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot be sliced.`); return; }
            const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
            const hasKnifeNearby = objects.some(o => {
                const t = (objectTypes.get(o) || '').toLowerCase();
                return t.includes('knife') && Math.floor(o.position.x) === ox && Math.floor(o.position.z) === oz;
            });
            const n = Math.max(2, parseInt(m[2], 10));
            const st = objectState.get(obj) || {};
            st.sliced = true; st.pieces = n;
            objectState.set(obj, st);
            visualSlice(obj, n);
            updateObjectPositionsDisplay();
            setStatus(`🔪 Sliced ${m[1]} into ${n} pieces`);
            appendMessage('assistant', `✅ Sliced "${m[1]}" into ${n} pieces.${hasKnifeNearby ? '' : ' (No knife detected at this cell — bring one to the same cell first for a realistic plan.)'}`);
        }

        async function runSetState(raw) {
            const m = raw.match(SET_STATE_RE);
            if (!m) { setStatus('⚠️ Invalid set_state command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const key = m[2].trim();
            const valueRaw = m[3].trim();
            let value;
            if (/^(true|false)$/i.test(valueRaw)) value = /^true$/i.test(valueRaw);
            else if (/^-?\d+(\.\d+)?$/.test(valueRaw)) value = parseFloat(valueRaw);
            else value = valueRaw.replace(/^["']|["']$/g, '');
            const st = objectState.get(obj) || {};
            st[key] = value;
            objectState.set(obj, st);

            // Auto-eject: when a pot/pan's contents are marked "ready", teleport all
            // solid items to a fixed cell adjacent to the stove (right side, or fallback
            // cells if that cell is off-grid). Items land stacked with a small offset.
            if (key === 'contents' && value === 'ready') {
                const objType = (objectTypes.get(obj) || '').toLowerCase();
                if (objType.includes('pot') || objType.includes('pan')) {
                    const containerName = objectNames.get(obj) || objectTypes.get(obj);
                    const inside = objects.filter(o => (objectState.get(o) || {}).inContainer === containerName
                                                    || (objectState.get(o) || {}).inContainer === m[1].trim());
                    if (inside.length) {
                        appendMessage('assistant', `🍽️ Cooking done — teleporting ${inside.length} item(s) from ${containerName}`);

                        // Determine target: cell to the right of the stove, else right of pot
                        const stoveObj = objects.find(o => (objectTypes.get(o) || '').toLowerCase().includes('stove'));
                        let baseX, baseZ;
                        if (stoveObj) {
                            // stoves are 2 wide; place items one cell to the right of the stove's right edge
                            const fp = objectFootprint.get(stoveObj) || { w: 2, h: 1 };
                            baseX = Math.max(0, Math.min(19, Math.round(stoveObj.position.x) + fp.w));
                            baseZ = Math.max(0, Math.min(10, Math.round(stoveObj.position.z)));
                        } else {
                            baseX = Math.max(0, Math.min(19, Math.round(obj.position.x) + 1));
                            baseZ = Math.max(0, Math.min(10, Math.round(obj.position.z)));
                        }

                        const cState = objectState.get(obj) || {};
                        cState.contents = 'ready';
                        objectState.set(obj, cState);
                        for (let i = 0; i < inside.length; i++) {
                            const item = inside[i];
                            // Stack items on the same cell with slight vertical separation
                            item.position.set(baseX + 0.5, 0.5 + i * 0.15, baseZ + 0.5);
                            const sprite = objectSprites.get(item);
                            if (sprite) { sprite.position.x = item.position.x; sprite.position.z = item.position.z; sprite.position.y = item.position.y + 2.2; }
                            const ist = objectState.get(item) || {};
                            ist.cooked = true;
                            delete ist.inContainer;
                            objectState.set(item, ist);
                            const col = String.fromCharCode(65 + baseX);
                            const label = objectNames.get(item) || objectTypes.get(item) || 'item';
                            appendMessage('assistant', `  ↳ ${label} → ${col}${baseZ + 1}`);
                            await new Promise(res => setTimeout(res, 100));
                        }
                        updateObjectPositionsDisplay();
                    }
                }
            }

            updateObjectPositionsDisplay();
            setStatus(`✅ Set ${m[1]}.${key} = ${value}`);
        }

        async function runCheckState(raw) {
            const m = raw.match(CHECK_STATE_RE);
            if (!m) { setStatus('⚠️ Invalid check_state command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const st = objectState.get(obj) || {};
            const cfg = getObjectConfig(objectTypes.get(obj));
            const weight = objectWeight.get(obj);
            const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
            const x = Math.floor(obj.position.x), z = Math.floor(obj.position.z);
            const touching = getTouchingCoordinates(x, z, fp.w, fp.h);
            const parts = [];
            parts.push(`position: ${String.fromCharCode(65 + x)}${z + 1}`);
            parts.push(`weight: ${weight}${weight > MAX_LIFT_WEIGHT ? ' (too heavy to lift directly — drag instead)' : ''}`);
            parts.push(`affordances: ${cfg.affordances.join(', ')}`);
            if ('isOpen' in st) parts.push(`open: ${st.isOpen}`);
            if ('power' in st) parts.push(`power: ${st.power}`);
            if ('temperature' in st) parts.push(`temperature: ${st.temperature}`);
            if ('fillLevel' in st) parts.push(`fill level: ${Math.round(st.fillLevel * 100)}%`);
            if ('capOn' in st) parts.push(`cap: ${st.capOn ? 'on' : 'off'}`);
            if ('dirty' in st) parts.push(`dirty: ${Math.round(st.dirty * 100)}%`);
            if ('sliced' in st) parts.push(`sliced: ${st.sliced} (${st.pieces || 1} pieces)`);
            parts.push(`touching: ${touching.join(', ')}`);
            const summary = `State of "${m[1]}": ${parts.join('; ')}.`;
            appendMessage('assistant', summary);
            chatHistory.push({ role: 'assistant', content: summary });
        }

        async function runWaitFor(raw) {
            const m = raw.match(WAIT_FOR_RE);
            if (!m) { setStatus('⚠️ Invalid wait_for command'); return; }
            const secs = Math.min(10, parseFloat(m[1])); // capped so a bad plan can't hang the UI
            setStatus(`⏳ Waiting ${secs}s...`);
            await delay(secs * 1000);
            setStatus('✅ Wait complete');
        }

        async function runFind(raw) {
            const m = raw.match(FIND_RE);
            if (!m) { setStatus('⚠️ Invalid find command'); return; }
            const key = m[1].trim().toLowerCase();
            const value = m[2].trim().toLowerCase();
            const matches = [];
            for (const obj of objects) {
                const name = objectNames.get(obj) || objectTypes.get(obj) || 'object';
                const type = (objectTypes.get(obj) || '').toLowerCase();
                const st = objectState.get(obj) || {};
                const cfg = getObjectConfig(objectTypes.get(obj));
                const weight = objectWeight.get(obj);
                const x = Math.floor(obj.position.x), z = Math.floor(obj.position.z);
                const coord = `${String.fromCharCode(65 + x)}${z + 1}`;
                let val;
                if (key === 'color') val = getObjectColor(obj).toLowerCase();
                else if (key === 'type') val = type;
                else if (key === 'name') val = name.toLowerCase();
                else if (key === 'weight') val = String(weight);
                else if (key === 'size') val = weight <= 1 ? 'small' : (weight <= 3 ? 'medium' : 'large');
                else if (key in st) val = String(st[key]).toLowerCase();
                else if (cfg.affordances.includes(key)) val = 'true';
                if (val !== undefined && (val === value || (key === 'color' && val.includes(value)))) {
                    matches.push(`${name} at ${coord}`);
                }
            }
            const summary = matches.length ? `Found matching ${key}=${value}: ${matches.join(', ')}.` : `No objects found matching ${key}=${value}.`;
            appendMessage('assistant', summary);
            chatHistory.push({ role: 'assistant', content: summary });
        }

        function reduceDirtAtCell(col, row, amount) {
            const colIdx = colLetterToX(col), rowIdx = rowNumberToY(row);
            if (colIdx === null || rowIdx === null) return;
            for (const obj of objects) {
                const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
                const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
                if (colIdx >= ox && colIdx < ox + fp.w && rowIdx >= oz && rowIdx < oz + fp.h) {
                    const st = objectState.get(obj);
                    if (st && 'dirty' in st && st.dirty > 0) {
                        st.dirty = Math.max(0, st.dirty - amount);
                        objectState.set(obj, st);
                        updateObjectPositionsDisplay();
                    }
                }
            }
        }

        function applySoapAtCoord(col, row) {
            return new Promise(async resolve => {
                await moveTo(col, row);
                isAnimating = true;
                setStatus(`🧼 Applying soap at ${col.toUpperCase()}${row}...`);
                animateZ(currentZ, 5.5, 400, () => {
                    setTimeout(() => {
                        animateZ(currentZ, 3.0, 350, () => {
                            isAnimating = false;
                            reduceDirtAtCell(col, row, 0.25);
                            resolve();
                        });
                    }, 300);
                });
            });
        }

        function applyClothAtCoord(col, row) {
            return new Promise(async resolve => {
                await moveTo(col, row);
                isAnimating = true;
                setStatus(`🧹 Wiping at ${col.toUpperCase()}${row}...`);
                animateZ(currentZ, 5.5, 400, () => {
                    const baseX = currentX, baseY = currentY;
                    const WIPE_STEPS = 4, WIPE_AMP = 0.3;
                    let wipeStep = 0;
                    function doWipe() {
                        if (wipeStep >= WIPE_STEPS) {
                            animateXY(baseX, baseY, 150, () => {
                                animateZ(currentZ, 3.0, 350, () => {
                                    isAnimating = false;
                                    reduceDirtAtCell(col, row, 0.35);
                                    resolve();
                                });
                            });
                            return;
                        }
                        const offset = (wipeStep % 2 === 0) ? WIPE_AMP : -WIPE_AMP;
                        animateXY(baseX + offset, baseY, 120, () => {
                            wipeStep++;
                            doWipe();
                        });
                    }
                    doWipe();
                });
            });
        }

        function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

        function getTaskDescription(raw) {
            const rawLower = raw.toLowerCase();
            if (rawLower.includes('goto_coordinate')) {
                const eqPart = raw.split('=').slice(1).join('=').trim();
                const parts = eqPart.split(',');
                const col = parts[0]?.trim().toUpperCase() || '?';
                const row = parts[1]?.trim() || '?';
                return `📍 Navigate to ${col}${row}`;
            } else if (rawLower === 'pickup') {
                return `🤲 Pick up object at current location`;
            } else if (rawLower === 'keep') {
                return `📦 Place object down`;
            } else if (rawLower === 'pour') {
                return `💧 Pour/tilt object`;
            } else if (rawLower.startsWith('apply_soap')) {
                const match = raw.match(/\[(.*?)\]/);
                const coordStr = match ? match[1] : 'multiple cells';
                return `🧼 Apply soap to ${coordStr}`;
            } else if (rawLower.startsWith('apply_cloth')) {
                const match = raw.match(/\[(.*?)\]/);
                const coordStr = match ? match[1] : 'multiple cells';
                return `🧹 Wipe/clean at ${coordStr}`;
            } else if (rawLower.includes('change_orientation')) {
                const token = raw.replace(/^[\{\s]*change_orientation\s*(?:=|\()\s*/i, '').replace(/[\)\}\s]*$/g, '').trim();
                const parsed = token.match(/([+-]?)([xyz])\s*(-?\d+)?/i);
                if (parsed) {
                    const sign = parsed[1] || '+';
                    const axis = parsed[2].toUpperCase();
                    const deg = parsed[3] || '90';
                    const dirMap = {
                        '+x': 'rotate left side to top',
                        '-x': 'rotate right side to top', 
                        '+y': 'rotate object clockwise',
                        '-y': 'rotate object counter-clockwise',
                        '+z': 'rotate back side to top',
                        '-z': 'rotate front side to top'
                    };
                    const desc = dirMap[sign + axis] || 'rotate';
                    return `🔄 Orientation: ${axis}-axis ${sign}${deg}° (${desc})`;
                }
                return `🔄 Rotate all objects: ${token}`;
            } else if (rawLower.includes('inspect_sides')) {
                const target = raw.includes('=') ? raw.split('=').slice(1).join('=') : raw.replace(/inspect_sides/i, '');
                const objName = target.replace(/[()=\s]/g, '').substring(0, 20);
                return `👁️ Inspect sides of "${objName}" to plan next moves`;
            } else if (rawLower.includes('drag_from_coordinate')) {
                const m = raw.match(/drag_from_coordinate\s*\(\s*([A-T])\s*,\s*(\d+)\s*\)\s*_to_coordinate\s*\(\s*([A-T])\s*,\s*(\d+)\s*\)/i);
                if (m) {
                    return `🖐️ Drag object from ${m[1].toUpperCase()}${m[2]} to ${m[3].toUpperCase()}${m[4]}`;
                }
                return `🖐️ Drag object across the board`;
            } else if (rawLower.startsWith('open(')) {
                const m = raw.match(OPEN_RE);
                return `🔓 Open ${m ? m[1] : 'object'}`;
            } else if (rawLower.startsWith('close(')) {
                const m = raw.match(CLOSE_RE);
                return `🔒 Close ${m ? m[1] : 'object'}`;
            } else if (rawLower.startsWith('turn_on(')) {
                const m = raw.match(TURN_ON_RE);
                return `🔌 Turn on ${m ? m[1] : 'object'}`;
            } else if (rawLower.startsWith('turn_off(')) {
                const m = raw.match(TURN_OFF_RE);
                return `🔌 Turn off ${m ? m[1] : 'object'}`;
            } else if (rawLower.startsWith('twist_cap(')) {
                const m = raw.match(TWIST_CAP_RE);
                return m ? `🔄 Twist cap ${m[2]} for ${m[1]}` : `🔄 Twist cap`;
            } else if (rawLower.startsWith('fill(')) {
                const m = raw.match(FILL_RE);
                return m ? `🧪 Fill ${m[1]} to ${m[2]}%` : `🧪 Fill object`;
            } else if (rawLower.startsWith('pour_into(')) {
                const m = raw.match(POUR_INTO_RE);
                return m ? `💧 Pour into ${m[1]}` : `💧 Pour into object`;
            } else if (rawLower.startsWith('place_into(')) {
                const m = raw.match(PLACE_INTO_RE);
                return m ? `🥕 Place into ${m[1]}` : `🥕 Place into container`;
            } else if (rawLower.startsWith('slice(')) {
                const m = raw.match(SLICE_RE);
                return m ? `🔪 Slice ${m[1]} into ${m[2]} pieces` : `🔪 Slice object`;
            } else if (rawLower.startsWith('set_state(')) {
                const m = raw.match(SET_STATE_RE);
                return m ? `⚙️ Set ${m[1]}.${m[2]} = ${m[3]}` : `⚙️ Set object state`;
            } else if (rawLower.startsWith('check_state(')) {
                const m = raw.match(CHECK_STATE_RE);
                return m ? `🔍 Check state of ${m[1]}` : `🔍 Check object state`;
            } else if (rawLower.startsWith('wait_for(')) {
                const m = raw.match(WAIT_FOR_RE);
                return m ? `⏳ Wait ${m[1]}s` : `⏳ Wait`;
            } else if (rawLower.startsWith('find(')) {
                const m = raw.match(FIND_RE);
                return m ? `🔎 Find objects where ${m[1]}=${m[2]}` : `🔎 Find object`;
            } else if (rawLower.startsWith('sweep(')) {
                return `🧹 Sweep floor cells`;
            } else if (rawLower.startsWith('mop(')) {
                return `🪣 Mop floor cells with disinfectant`;
            } else if (rawLower.startsWith('scrub(')) {
                return `🪥 Scrub surface cells hard`;
            } else if (rawLower.startsWith('wash(')) {
                const m = raw.match(WASH_RE);
                return m ? `🚿 Wash "${m[1]}" clean` : `🚿 Wash object`;
            } else if (rawLower.startsWith('run_cycle(')) {
                const m = raw.match(RUN_CYCLE_RE);
                return m ? `⚙️ Run ${m[1]} cycle` : `⚙️ Run machine cycle`;
            } else if (rawLower.startsWith('iron(')) {
                const m = raw.match(IRON_RE);
                return m ? `🪄 Iron "${m[1]}"` : `🪄 Iron item`;
            } else if (rawLower.startsWith('fold(')) {
                const m = raw.match(FOLD_RE);
                return m ? `👕 Fold "${m[1]}"` : `👕 Fold item`;
            } else if (rawLower.startsWith('rotate_object(')) {
                const m = raw.match(ROTATE_OBJECT_RE);
                return m ? `🔄 Rotate ${m[1]} ${m[2].toUpperCase()}` : `🔄 Rotate single object`;
            } else if (rawLower === 'task_completed') {
                return `✅ Finalize: restore original state & complete task`;
            }
            return `⚙️ Execute: ${raw.substring(0, 30)}`;
        }

        async function executeCommands(commands) {
            totalCommands = commands.length;
            completedCommands = 0;
            showExecLog(commands);
            updateProgress(0, totalCommands);

            // Store initial orientation state so we can restore it when task completes
            const initialRotations = objects.map(obj => ({
                rotation: { x: obj.rotation.x, y: obj.rotation.y, z: obj.rotation.z },
                quaternion: obj.quaternion.clone()
            }));

            for (let i = 0; i < commands.length; i++) {
                let raw = commands[i].trim();
                raw = raw.replace(/^\{+|\}+$/g, '').trim();
                markCmdActive(i);
                updateProgress(i, totalCommands);

                // Get human-readable task description
                const taskDesc = getTaskDescription(raw);
                console.log(`[TASK ${i + 1}/${totalCommands}] ${taskDesc}`);
                setStatus(`[${i + 1}/${totalCommands}] ${taskDesc}`);

                const rawLower = raw.toLowerCase();

                // --- New: change_orientation and inspect_sides commands ---
                if (rawLower.includes('change_orientation')) {
                    // format: {change_orientation = +z90} or {change_orientation(+z90)} or {change_orientation = z, 90}
                    const eq = raw.replace(/^[\{\s]*change_orientation\s*(?:=|\()\s*/i, '').replace(/[\)\}\s]*$/g, '').trim();
                    const token = eq.replace(/[()\s]/g, '');
                    console.log('� ORIENTATION COMMAND');
                    console.log('  Token:', token);
                    // Accept tokens like +z90, -z90, +x90, -x90, +y90, -y90 or z90/-z90
                    let axis = null, deg = 0;
                    const m = token.match(/([+-]?)([xyz])\s*(-?\d+)?/i);
                    if (m) {
                        const sign = m[1] || '+';
                        axis = m[2].toLowerCase();
                        deg = parseInt(m[3] || '90', 10);
                        if (sign === '-') deg = -Math.abs(deg);
                    }
                    if (!axis) {
                        console.error('❌ Invalid change_orientation token:', token);
                        setStatus('⚠️ Invalid change_orientation token');
                    } else {
                        console.log(`✓ Rotating all objects around ${axis.toUpperCase()}-axis by ${deg}°`);
                        window.rotateAllObjects(axis, deg);
                        // update sprites positions immediately
                        objects.forEach(obj => {
                            const sprite = objectSprites.get(obj);
                            if (sprite) sprite.position.set(obj.position.x, obj.position.y + 2.2, obj.position.z);
                        });
                        updateObjectPositionsDisplay();
                    }

                } else if (rawLower.includes('inspect_sides')) {
                    // format: {inspect_sides = oven} or {inspect_sides(oven)}
                    const eq = raw.includes('=') ? raw.split('=').slice(1).join('=').trim() : raw.replace(/inspect_sides/i, '').trim();
                    const targetName = eq.replace(/[()\s]/g, '').toLowerCase();
                    const summary = (() => {
                        function findObjectByKey(key) {
                            for (const obj of objects) {
                                const t = (objectNames.get(obj) || objectTypes.get(obj) || '').toLowerCase();
                                if (t === key) return obj;
                            }
                            return null;
                        }
                        const o = findObjectByKey(targetName);
                        if (!o) return `No object matching '${targetName}' found on board.`;
                        const sides = { top: [], bottom: [], left: [], right: [], front: [], back: [] };
                        const threshold = 1.1; // how close is "touching"
                        for (const other of objects) {
                            if (other === o) continue;
                            const dx = other.position.x - o.position.x;
                            const dy = other.position.y - o.position.y;
                            const dz = other.position.z - o.position.z;
                            const distXZ = Math.sqrt(dx*dx + dz*dz);
                            const name = objectNames.get(other) || objectTypes.get(other) || 'object';
                            const coord = `${String.fromCharCode(65 + Math.floor(other.position.x))}${Math.floor(other.position.z) + 1}`;
                            if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > Math.abs(dz)) {
                                if (dy > 0 && Math.abs(dy) < threshold) sides.top.push({ name, coord, pos: other.position });
                                if (dy < 0 && Math.abs(dy) < threshold) sides.bottom.push({ name, coord, pos: other.position });
                            } else {
                                if (dx > 0 && Math.abs(dx) >= Math.abs(dz) && Math.abs(dx) < threshold) sides.right.push({ name, coord, pos: other.position });
                                if (dx < 0 && Math.abs(dx) >= Math.abs(dz) && Math.abs(dx) < threshold) sides.left.push({ name, coord, pos: other.position });
                                if (dz > 0 && Math.abs(dz) > Math.abs(dx) && Math.abs(dz) < threshold) sides.front.push({ name, coord, pos: other.position });
                                if (dz < 0 && Math.abs(dz) > Math.abs(dx) && Math.abs(dz) < threshold) sides.back.push({ name, coord, pos: other.position });
                            }
                        }
                        function guessFeatures(typeStr) {
                            const t = (typeStr || '').toLowerCase();
                            if (t.includes('bottle') || t.includes('water_bottle')) return 'tall, hollow, graspable at neck — grab from top';
                            if (t.includes('soap_bottle')) return 'dispenser bottle, pump-top — grab from top, pump to dispense';
                            if (t.includes('mug')) return 'open-top, handle — pick up from handle (side)';
                            if (t.includes('plate')) return 'flat, shallow — grab from edge (top)';
                            if (t.includes('glass')) return 'hollow, delicate, graspable — grab from upper side';
                            if (t.includes('box') || t.includes('wooden_box')) return 'box-like, enclosed, lid possible — open from top or side';
                            if (t.includes('powder_box')) return 'container with lid — grab from side, or remove lid from top';
                            if (t.includes('oven')) return 'enclosed appliance with door — open door from side (right or left), insert items from front';
                            if (t.includes('cookies')) return 'stack of small items — grab from top, pick individually';
                            if (t.includes('cutting_board')) return 'flat work surface — grab from edge or side';
                            if (t.includes('knife')) return 'sharp tool — grasp handle from side';
                            if (t.includes('pot')) return 'container with handles — grab handle (left or right side), or fill from top';
                            if (t.includes('pan')) return 'shallow container with handle — grab handle (side), or work from top';
                            if (t.includes('spoon')) return 'utensil with handle — grab handle from side or top';
                            if (t.includes('bowl')) return 'hollow container — grab rim from side or fill from top';
                            if (t.includes('napkins')) return 'stack of thin sheets — pull from top';
                            if (t.includes('towel')) return 'folded cloth — grab from side or top corner';
                            if (t.includes('plant')) return 'potted plant — grab pot from side, or top';
                            if (t.includes('book')) return 'flat object — grab spine (side) or edge (top)';
                            if (t.includes('water_cup')) return 'small cup, filled — grab carefully from side';
                            return 'unknown features — inspect sides first';
                        }
                        function fmtArr(arr) { return arr.length ? arr.map(a => `${a.name} @ ${a.coord} (${guessFeatures(a.name)})`).join(', ') : 'none'; }
                        const cfg = getObjectConfig(objectTypes.get(o));
                        const st = objectState.get(o) || {};
                        const weight = objectWeight.get(o);
                        const stateBits = [];
                        if ('isOpen' in st) stateBits.push(st.isOpen ? 'open' : 'closed');
                        if ('power' in st) stateBits.push(st.power ? 'powered ON' : 'powered OFF');
                        if ('temperature' in st) stateBits.push(`temp:${st.temperature}`);
                        if ('fillLevel' in st) stateBits.push(`fill:${Math.round(st.fillLevel * 100)}%`);
                        if ('capOn' in st) stateBits.push(st.capOn ? 'cap ON' : 'cap OFF');
                        if ('dirty' in st && st.dirty > 0.05) stateBits.push(`dirty:${Math.round(st.dirty * 100)}%`);
                        if (st.sliced) stateBits.push(`sliced x${st.pieces}`);
                        const extra = ` Affordances: ${cfg.affordances.join(', ')}. Weight: ${weight}${weight > MAX_LIFT_WEIGHT ? ' (too heavy to lift — use drag instead)' : ''}.${stateBits.length ? ' State: ' + stateBits.join(', ') + '.' : ''}`;
                        const s = `Side inspection for '${targetName}': Top: ${fmtArr(sides.top)}; Bottom: ${fmtArr(sides.bottom)}; Left: ${fmtArr(sides.left)}; Right: ${fmtArr(sides.right)}; Front: ${fmtArr(sides.front)}; Back: ${fmtArr(sides.back)}.${extra}`;
                        return s;
                    })();
                    appendMessage('assistant', summary);
                    chatHistory.push({ role: 'assistant', content: summary });

                } else if (rawLower.includes('goto_coordinate')) {
                    const eqPart = raw.split('=').slice(1).join('=').trim();
                    const parts = eqPart.split(',');
                    if (parts.length >= 2) {
                        const col = parts[0].trim();
                        const row = parts[1].trim();
                        await moveTo(col, row);
                        console.log(`✓ Arrived at ${col}${row}`);
                    }

                } else if (rawLower === 'pickup') {
                    await pickup();
                    console.log(`✓ Pickup complete`);

                } else if (rawLower === 'keep') {
                    await placeDown();
                    console.log(`✓ Object placed`);

                } else if (rawLower === 'pour') {
                    await pourAction();
                    console.log(`✓ Pour action complete`);

                } else if (rawLower.startsWith('apply_soap')) {
                    const coordStr = raw.replace(/apply_soap/i, '')
                                       .replace(/[()=]/g, ' ')
                                       .trim();
                    const coordTokens = coordStr.split(',').map(s => s.trim()).filter(Boolean);
                    setStatus(`🧼 Starting soap pass — ${coordTokens.length} cell(s)...`);
                    console.log(`Starting soap application at: ${coordTokens.join(', ')}`);
                    for (const token of coordTokens) {
                        const parsed = parseCoord(token);
                        if (parsed) await applySoapAtCoord(parsed.col, parsed.row);
                    }
                    console.log(`✓ Soap pass complete`);
                    setStatus('✅ Soap pass complete');

                } else if (rawLower.startsWith('apply_cloth')) {
                    const coordStr = raw.replace(/apply_cloth/i, '')
                                       .replace(/[()=]/g, ' ')
                                       .trim();
                    const coordTokens = coordStr.split(',').map(s => s.trim()).filter(Boolean);
                    setStatus(`🧹 Starting wipe pass — ${coordTokens.length} cell(s)...`);
                    console.log(`Starting cloth wipe at: ${coordTokens.join(', ')}`);
                    for (const token of coordTokens) {
                        const parsed = parseCoord(token);
                        if (parsed) await applyClothAtCoord(parsed.col, parsed.row);
                    }
                    console.log(`✓ Wipe pass complete`);
                    setStatus('✅ Wipe pass complete');

                } else if (rawLower.includes('drag_from_coordinate')) {
                    const m = raw.match(/drag_from_coordinate\s*\(\s*([A-T])\s*,\s*(\d+)\s*\)\s*_to_coordinate\s*\(\s*([A-T])\s*,\s*(\d+)\s*\)/i);
                    if (m) {
                        const fromCol = m[1], fromRow = m[2], toCol = m[3], toRow = m[4];
                        await dragTo(fromCol, fromRow, toCol, toRow);
                        console.log(`✓ Dragged object from ${fromCol.toUpperCase()}${fromRow} to ${toCol.toUpperCase()}${toRow}`);
                    } else {
                        console.error('❌ Invalid drag command format:', raw);
                        setStatus('⚠️ Invalid drag command format');
                    }

                } else if (rawLower.startsWith('open(')) {
                    await runOpenClose(raw, true);
                } else if (rawLower.startsWith('close(')) {
                    await runOpenClose(raw, false);
                } else if (rawLower.startsWith('turn_on(')) {
                    await runPower(raw, true);
                } else if (rawLower.startsWith('turn_off(')) {
                    await runPower(raw, false);
                } else if (rawLower.startsWith('twist_cap(')) {
                    await runTwistCap(raw);
                } else if (rawLower.startsWith('fill(')) {
                    await runFill(raw);
                } else if (rawLower.startsWith('pour_into(')) {
                    const m = raw.match(POUR_INTO_RE);
                    if (m) { await pourInto(m[1]); } else { setStatus('⚠️ Invalid pour_into command'); }
                } else if (rawLower.startsWith('place_into(')) {
                    const m = raw.match(PLACE_INTO_RE);
                    if (m) { await placeInto(m[1]); } else { setStatus('⚠️ Invalid place_into command'); }
                } else if (rawLower.startsWith('slice(')) {
                    await runSlice(raw);
                } else if (rawLower.startsWith('set_state(')) {
                    await runSetState(raw);
                } else if (rawLower.startsWith('check_state(')) {
                    await runCheckState(raw);
                } else if (rawLower.startsWith('wait_for(')) {
                    await runWaitFor(raw);
                } else if (rawLower.startsWith('find(')) {
                    await runFind(raw);
                } else if (rawLower.startsWith('sweep(')) {
                    await runSweep(raw);
                } else if (rawLower.startsWith('mop(')) {
                    await runMop(raw);
                } else if (rawLower.startsWith('scrub(')) {
                    await runScrub(raw);
                } else if (rawLower.startsWith('wash(')) {
                    await runWash(raw);
                } else if (rawLower.startsWith('run_cycle(')) {
                    await runCycle(raw);
                } else if (rawLower.startsWith('iron(')) {
                    await runIron(raw);
                } else if (rawLower.startsWith('fold(')) {
                    await runFold(raw);
                } else if (rawLower.startsWith('rotate_object(')) {
                    await runRotateObject(raw);

                } else if (rawLower === 'task_completed') {
                    // Restore original orientation before marking task complete
                    console.log(`🔄 Restoring original object orientations...`);
                    setStatus('🔄 Restoring original orientation...');
                    objects.forEach((obj, idx) => {
                        if (initialRotations[idx]) {
                            obj.quaternion.copy(initialRotations[idx].quaternion);
                        }
                    });
                    objects.forEach(obj => {
                        const sprite = objectSprites.get(obj);
                        if (sprite) sprite.position.set(obj.position.x, obj.position.y + 2.2, obj.position.z);
                    });
                    updateObjectPositionsDisplay();
                    await delay(300);
                    console.log(`✓ Task finalized and state restored`);
                    setStatus('<span class="w-2 h-2 bg-emerald-400 rounded-full inline-block animate-pulse"></span>&nbsp;Task Complete!');
                    appendMessage('assistant', '✅ Task completed successfully! Orientation restored.');
                    markCmdDone(i);
                    updateProgress(totalCommands, totalCommands);
                    break;
                }

                markCmdDone(i);
                await delay(100);
            }
            console.log(`✅ ALL TASKS COMPLETED (${totalCommands}/${totalCommands})`);
            updateProgress(totalCommands, totalCommands);
            setTimeout(hideProgress, 2000);
        }

        const chatHistory = [];
        let pendingPlan = null;
        let pendingBoardState = '';
        let pendingUserText = '';

        // ── Robot Memory (persisted to localStorage) ──────────────────────────
        const MEMORY_KEY = 'k3d_robot_memory';
        function loadMemory() {
            try { return JSON.parse(localStorage.getItem(MEMORY_KEY) || '{}'); } catch { return {}; }
        }
        function saveMemory(mem) {
            try { localStorage.setItem(MEMORY_KEY, JSON.stringify(mem)); } catch {}
        }
        function getMemory() {
            const mem = loadMemory();
            if (!mem.completedTasks) mem.completedTasks = [];
            if (!mem.failedTasks) mem.failedTasks = [];
            if (!mem.notes) mem.notes = [];
            if (!mem.objectHistory) mem.objectHistory = {};
            return mem;
        }
        function rememberTask(text, plan, commandCount, success) {
            const mem = getMemory();
            const entry = {
                task: text,
                plan: plan.substring(0, 300),
                commands: commandCount,
                time: new Date().toLocaleString(),
                board: getBoardContext().substring(0, 200)
            };
            if (success) {
                mem.completedTasks.unshift(entry);
                if (mem.completedTasks.length > 15) mem.completedTasks.pop();
            } else {
                mem.failedTasks.unshift(entry);
                if (mem.failedTasks.length > 5) mem.failedTasks.pop();
            }
            saveMemory(mem);
        }
        function buildMemoryContext() {
            const mem = getMemory();
            const parts = [];
            if (mem.notes && mem.notes.length) parts.push(`User notes: ${mem.notes.join('; ')}.`);
            if (mem.completedTasks && mem.completedTasks.length) {
                const recent = mem.completedTasks.slice(0, 5).map(t => `"${t.task}" (${t.commands} steps, ${t.time})`).join('; ');
                parts.push(`Recently completed: ${recent}.`);
            }
            if (mem.failedTasks && mem.failedTasks.length) {
                const fails = mem.failedTasks.slice(0, 3).map(t => `"${t.task}"`).join(', ');
                parts.push(`Previously cancelled/failed: ${fails} — avoid repeating the same mistakes.`);
            }
            return parts.length ? '\n\nROBOT MEMORY:\n' + parts.join('\n') : '';
        }
        window.clearMemory = function() {
            localStorage.removeItem(MEMORY_KEY);
            appendMessage('assistant', '🧠 Memory cleared.');
        };
        window.addMemoryNote = function(note) {
            const mem = getMemory();
            mem.notes.push(note);
            if (mem.notes.length > 10) mem.notes.shift();
            saveMemory(mem);
            appendMessage('assistant', `🧠 Noted: "${note}"`);
        };
        window.showMemory = function() {
            const mem = getMemory();
            const lines = [];
            if (mem.notes && mem.notes.length) lines.push(`📝 Notes: ${mem.notes.join(' | ')}`);
            if (mem.completedTasks && mem.completedTasks.length) {
                lines.push(`✅ Completed (${mem.completedTasks.length}):`);
                mem.completedTasks.slice(0, 8).forEach(t => lines.push(`  • ${t.task} [${t.time}]`));
            }
            if (mem.failedTasks && mem.failedTasks.length) {
                lines.push(`❌ Cancelled/failed (${mem.failedTasks.length}):`);
                mem.failedTasks.forEach(t => lines.push(`  • ${t.task}`));
            }
            if (!lines.length) lines.push('(no memory yet)');
            appendMessage('assistant', `<div class="bg-zinc-700/50 border border-zinc-600 rounded-lg p-3">
                <div class="text-xs font-bold text-purple-300 mb-2">🧠 ROBOT MEMORY</div>
                <pre class="text-xs text-zinc-300 whitespace-pre-wrap">${lines.join('\n')}</pre>
                <button onclick="clearMemory()" class="mt-2 text-xs text-red-400 hover:text-red-300 underline">Clear memory</button>
            </div>`);
        };

        // ── PLANNING PROMPT ── high-level only, multi-task aware ──────────────
        const PLANNING_PROMPT = `You are K5D — an intelligent household robot planner.

Given a task request and the current board state, produce a HIGH-LEVEL plan that a human can read, understand, and approve in 10 seconds.

OUTPUT FORMAT:
- If the task is simple (1 thing): 3–4 bullet points max.
- If the task is multi-step or multi-task: use PHASES. Each phase is a bold label followed by 2–3 bullets. Max 3 phases.
- End with one line: ⚠️ NEEDS: [list any objects missing from board] — or omit this line if everything is present.
- NO commands, NO coordinates, NO curly braces. Plain human English only.
- Total length: under 12 lines.

MULTI-TASK EXAMPLE for "do the laundry then sweep the floor":
PHASE 1 — Laundry
• Tilt machine open
• load clothes
• add detergent
• close and run cycle

PHASE 2 — Retrieve & Finish
• Unload washed clothes into basket
• Iron each item
• fold each item
• stack all clothes neatly

SINGLE-TASK EXAMPLE for "cook dinner":
• Heat stove
• place pot
• Put vegetables into pot
• Simmer until cooked
• plate the food

Knife Rule:
When using knife is over, keep knife on A11 until next needed to minimize unnecessary movements.

MISSING-OBJECTS EXAMPLE:
⚠️ NEEDS: broom (to sweep), detergent (for washing machine)`;

          // ── SYSTEM PROMPT ── master execution intelligence ─────────────────
          const SYSTEM_PROMPT = `You are K5D — the intelligent controller of a Prolabs V12.2 Precision Cartesian Gantry robot. Given an approved plan and board state, generate the COMPLETE, CORRECT sequence of K5D commands to execute it.

BOARD: columns A–T (20 cols, left→right), rows 1–11 (11 rows, front→back). Grid cell = ColRow e.g. A1, T11.
Board state format: name at COORD [footprint] {state flags} (touching: adjacent cells).
Gripper approaches from above; Z-axis lowers to pick/interact. Path planner auto-routes around obstacles.

━━━ COMMANDS ━━━
{goto_coordinate = COL, ROW}               move above cell
{pickup}                                    lift object at cell (weight ≤ 8 only)
{keep}                                      place held object at current cell
{pour}                                      tilt animation (no volume tracking)
{pour_into(NAME)}                           real volume transfer held→named target (liquids only)
{place_into(NAME)}                          place held solid item (vegetable, ingredient, etc.) into container — tracks contents
{drag_from_coordinate(C,R)_to_coordinate(C,R)}  slide heavy object (no weight limit)
{change_orientation = TOKEN}                rotate ALL objects — tokens: +x90 -x90 +y90 -y90 +z90 -z90
{rotate_object(NAME, TOKEN)}                rotate ONE named object (same tokens)
{open(NAME)} / {close(NAME)}               toggle openable objects
{turn_on(NAME)} / {turn_off(NAME)}         toggle switchable appliances
{twist_cap(NAME, on|off)}                  twist bottle/jar cap
{fill(NAME, PERCENT)}                      set fillable object fill level 0–100
{slice(NAME, N)}                           cut sliceable into N pieces (knife must be same cell)
{set_state(NAME, KEY, VALUE)}              set any state key directly
{check_state(NAME)}                        read full state — use to verify results
{sweep(X1,X2,...)}                         broom sweep cells (requires broom on board)
{mop(X1,X2,...)}                           wet mop cells (requires mop + filled bucket)
{scrub(X1,X2,...)}                         hard scrub cells (requires scrub_brush or toilet_brush)
{Apply_soap(X1,X2,...)}                    soap cells — coordinates are ColRow no space e.g. A1
{Apply_cloth(X1,X2,...)}                   wipe cells
{wash(NAME)}                               wash object clean dirty→0 (needs filled sink)
{run_cycle(NAME)}                          run washing machine (door MUST be closed first)
{iron(NAME)}                               iron cloth item (iron MUST be hot)
{fold(NAME)}                               fold item (iron FIRST — never fold wrinkled)
{inspect_sides(NAME)}                      report what's adjacent to all 6 faces
{find(KEY=VALUE)}                          find objects by attribute
{wait_for(SECONDS)}                        pause up to 10s
{Task_Completed}                           always last

━━━ NON-NEGOTIABLE RULES ━━━
WEIGHT: objects with weight > 8 CANNOT be picked up. Use drag or rotate_object instead.
  Too heavy: oven(25), stove(20), sink(30), washing_machine(40)

WASHING MACHINE DOOR is on the +z face (front). To access:
  1. {rotate_object(washing_machine, -x90)}  ← tilts door face upward
  2. {open(washing_machine)}
  3. load / unload clothes
  4. {close(washing_machine)}
  5. {rotate_object(washing_machine, +x90)}  ← restore upright
  6. {run_cycle(washing_machine)}
  NEVER run_cycle with door open. NEVER skip the rotation steps.

DEPENDENCY ORDER (never break these):
  sweep → mop  (always sweep before wet mopping)
  wash clothes → iron → fold  (never skip or reorder)
  preheat → cook → plate → turn_off  (always turn off stove/oven/iron at end)
  fill(sink,100) → wash(object)  (sink must have water)
  fill(bucket,100) + disinfectant → mop  (bucket must have solution)
  twist_cap(off) → pour_into() → twist_cap(on)  (if cap is on, liquids only)
  place_into(pot/pan) for solid items (vegetables, ingredients) — no cap needed; call once per item to stack multiple items
  at a container's coordinate, {pickup} always grabs the container first (not its contents); to retrieve an item from inside, first move the container away, then {pickup} the item
  turn_on(iron) → wait_for(4) → check_state(iron) confirms hot → iron()

SLICING: bring knife to SAME CELL as target first. After {keep}, knife is AT TARGET cell.
  To return knife: {pickup} from TARGET (you're already there) → goto origin → {keep}.

APPLIANCES — ALWAYS turn off before Task_Completed:
  stove, oven, iron must be powered OFF at end. Washing machine door must be closed and upright.

━━━ EFFICIENCY ━━━
- BATCH surface ops: one {sweep(A1,B1,C1,...,T1)} per row, not 20 individual calls
- EXPLOIT WAITS: start other work immediately after run_cycle / turn_on — return later
- ZONE-FIRST: finish one area before moving to another
- RETURN ON THE WAY: carry next needed object when returning from a delivery
- VERIFY KEY RESULTS: use {check_state()} on important outputs before Task_Completed

━━━ MULTI-TASK: when plan has multiple phases ━━━
Execute in dependency order. Exploit machine wait times for parallel work:
  After run_cycle → immediately sweep/dust → come back to retrieve clothes
  After turn_on(oven) → prep other ingredients → return to check temp
Sequence commands as one continuous list — don't repeat moves already made.

━━━ OBJECTS QUICK REFERENCE ━━━
bottle/soap_bottle  wt:1  pourable fillable twistable_cap  (fill:100% cap:on)
mug/glass/bowl      wt:1  pourable fillable
pot/pan             wt:3  pourable fillable heatable
plate/spoon/book    wt:1  liftable
cookies             wt:1  sliceable
knife               wt:1  cutting_tool (must be at same cell as sliceable target)
broom               wt:1  sweeping_tool — needed for sweep()
dustpan             wt:1  collecting_tool
mop                 wt:2  mopping_tool — needed for mop()
bucket              wt:2  fillable pourable capacity:2.0
scrub_brush         wt:1  scrubbing_tool — needed for scrub()
toilet_brush        wt:1  scrubbing_tool — needed for scrub()
duster              wt:1  dusting_tool
disinfectant        wt:1  pourable spray_tool (fill:100% cap:on)
detergent           wt:2  pourable (pour into washing_machine before cycle)
clothes_pile        wt:2  foldable ironable (dirty:60% wrinkled:true)
shirt/pants         wt:1  foldable ironable (dirty:0% wrinkled:true)
towel               wt:1  foldable ironable cleaning_tool
iron                wt:2  switchable heatable (must reach temp:hot before iron())
ironing_board       wt:5  liftable 2×1 footprint
ingredient_jar      wt:1  pourable fillable twistable_cap
vegetable_basket    wt:4  openable
shopping_bag        wt:2  openable
carrot              wt:1  liftable sliceable  (use knife at same cell: {slice(carrot,N)})
cucumber            wt:1  liftable sliceable  (use knife at same cell: {slice(cucumber,N)})
tomato              wt:1  liftable sliceable  (use knife at same cell: {slice(tomato,N)})
onion               wt:1  liftable sliceable  (use knife at same cell: {slice(onion,N)})
potato              wt:1  liftable sliceable  (use knife at same cell: {slice(potato,N)})
bell_pepper         wt:1  liftable sliceable  (use knife at same cell: {slice(bell_pepper,N)})
broccoli            wt:1  liftable sliceable  (use knife at same cell: {slice(broccoli,N)})
box/wooden_box      wt:3  openable (isOpen:false)
oven                wt:25 openable switchable heatable 2×2 footprint
stove               wt:20 switchable heatable 2×1 footprint
sink                wt:30 fillable drainable 2×1 footprint
washing_machine     wt:40 openable switchable (door on +z — rotate -x90 to open from above)

━━━ TASK PLAYBOOKS ━━━

1. SWEEPING:
Pre-check: {find(type=broom)} — if no broom on board, report and stop.
           {find(dirty=true)} — identify which cells/objects need sweeping.
Zone: if user specifies area, resolve to cell list. If not, full board A1–T11.
Step 1 — Sweep row by row, one call per row:
  {sweep(A1,B1,C1,D1,E1,F1,G1,H1,I1,J1,K1,L1,M1,N1,O1,P1,Q1,R1,S1,T1)}
  Repeat for rows 2–11.
Step 2 — Second pass on any cell still showing dirty > 40%:
  {check_state(OBJECT)} on objects in those cells, re-sweep if needed.
Step 3 — Collect: {goto_coordinate = DUSTPAN_COL, DUSTPAN_ROW},
  simulate collecting by moving gripper over dustpan.
Step 4 — {check_state(broom)} — if dirty > 60%, {wash(broom)}.
NEVER mop before sweeping is fully complete.

2. MOPPING:
Pre-check: {find(type=mop)} — if missing, report and stop.
           {find(type=bucket)} — if missing, report and stop.
           Sweeping MUST be complete before mopping begins.
Step 1 — Prepare solution:
  {fill(bucket, 100)}
  {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup}
  {twist_cap(disinfectant, off)}
  {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)}
  {twist_cap(disinfectant, on)}, return disinfectant, {keep}
Step 2 — {set_state(mop, wet, true)}
Step 3 — Mop row by row:
  {mop(A1,B1,C1,...,T1)} — one call per row, all 20 columns.
  Repeat rows 2–11.
Step 4 — Monitor bucket: {check_state(bucket)} every 3 rows.
  If fillLevel < 20%: refill before continuing.
Step 5 — Return mop. Empty bucket:
  {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}, {fill(sink, 0)}.
Step 6 — {check_state(mop)} — confirm dirty level reduced.

3. WASHING UTENSILS:
Pre-check: {find(type=sink)} — must exist.
           {find(dirty=true)} — list all dirty utensils.
           Object priority order: pot/pan → plate/bowl → mug/glass → cutlery/spoon.
Step 1 — Fill sink: {fill(sink, 100)}
Step 2 — Add soap:
  {goto_coordinate = SOAP_COL, SOAP_ROW}, {pickup}
  {twist_cap(soap_bottle, off)}
  {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}
  {twist_cap(soap_bottle, on)}, return soap bottle, {keep}
Step 3 — For each dirty utensil (largest first):
  {goto_coordinate = UTENSIL_COL, UTENSIL_ROW}, {pickup}
  {goto_coordinate = SINK_COL, SINK_ROW}, {keep}
  {wash(UTENSIL_NAME)}
  {goto_coordinate = DRYING_COL, DRYING_ROW}, {pickup}, {keep}
Step 4 — Repeat Step 3 for all dirty utensils.
Step 5 — {fill(sink, 0)} — drain sink.
Step 6 — {check_state(plate)}, {check_state(mug)} etc. — confirm dirty:0.
NEVER use apply_soap/apply_cloth for utensils — use wash() which properly resets dirty state.

4. COOKING:
Pre-check: {find(type=stove)} or {find(type=oven)} — identify heat source.
           {find(type=pot)} or {find(type=pan)} — identify cookware.
           {find(type=ingredient_jar)} or {find(type=vegetable_basket)}.
PREP (always before heat):
  {goto_coordinate = KNIFE_COL, KNIFE_ROW}, {pickup}
  {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {keep}
  {slice(vegetable_basket, 4)}
  {twist_cap(ingredient_jar, off)}, measure spices ready to add.
HEAT:
  {turn_on(stove)}, {wait_for(3)}, {check_state(stove)} — confirm temp:hot.
COOK:
  {goto_coordinate = POT_COL, POT_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {keep}
  {fill(pot, 60)}
  {goto_coordinate = VEGETABLE1_COL, VEGETABLE1_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {place_into(pot)}
  {goto_coordinate = VEGETABLE2_COL, VEGETABLE2_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {place_into(pot)}
  {twist_cap(ingredient_jar, off)}
  {goto_coordinate = JAR_COL, JAR_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pot)}
  {twist_cap(ingredient_jar, on)}, return jar, {keep}
  {set_state(pot, contents, cooking)}, {wait_for(8)}
  {set_state(pot, contents, ready)}
PLATE:
  {set_state(pot, contents, ready)}         ← AUTO-EJECTS all solid items (vegetables etc.) from inside the pot to surrounding
                                               cells automatically — no manual pickup loop needed; items marked cooked:true
  {goto_coordinate = PLATE_COL, PLATE_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(plate)}   ← for liquid/sauce only
  Move plated food to serving area.
SHUTDOWN:
  {turn_off(stove)} — MANDATORY before Task_Completed.
  Return pot to storage. Return knife to rack.


5. WASHING CLOTHES:
Pre-check: {find(dirty=true)} filtered to foldable+ironable objects only.
           If nothing dirty → report "all clothes already clean", skip.
           {find(type=detergent)} — if missing, report ⚠️ NEEDS: detergent.
MACHINE WASH SEQUENCE (exact order, never deviate):
  1. {rotate_object(washing_machine, -x90)} ← door tilts upward
  2. {open(washing_machine)}
  3. For each dirty garment (shirt/pants/clothes_pile/towel) not anything apart from garments:
     {goto_coordinate = GARMENT_COL, GARMENT_ROW}, {pickup}
     {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {keep}
  4. {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {pickup}
     {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {pour_into(washing_machine)}
     {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {keep}
  5. {close(washing_machine)}
  6. {rotate_object(washing_machine, +x90)} ← MUST restore upright before cycle
  7. {run_cycle(washing_machine)} ← wait for cycle to complete fully
  8. {rotate_object(washing_machine, -x90)}, {open(washing_machine)}
  10. {close(washing_machine)}, {rotate_object(washing_machine, +x90)}
  11. {check_state(washing_machine)} — confirm door closed, upright.

6. IRONING & FOLDING:
Pre-check: {find(wrinkled=true)} — only process wrinkled items.
           {find(dirty=true)} on same objects — if still dirty, wash first.
           {find(type=iron)} — must exist on board.
SETUP:
  Position ironing_board on a clear cell.
  {turn_on(iron)}, {wait_for(4)}
  {check_state(iron)} — MUST confirm temperature:hot before proceeding.
  If not hot: {wait_for(3)}, {check_state(iron)} again.
PER GARMENT (one at a time):
  {goto_coordinate = GARMENT_COL, GARMENT_ROW}, {pickup}
  {goto_coordinate = BOARD_COL, BOARD_ROW}, {keep}
  {iron(GARMENT_NAME)} ← sets wrinkled:false, ironed:true
  {fold(GARMENT_NAME)} ← sets folded:true
  {goto_coordinate = BOARD_COL, BOARD_ROW}, {pickup}
  {goto_coordinate = STACK_COL, STACK_ROW}, {keep}
  Repeat for all wrinkled garments.
SHUTDOWN:
  {turn_off(iron)} — MANDATORY, never skip.
  {check_state(iron)} — confirm power:false before Task_Completed.
NEVER fold before ironing. NEVER iron with cold iron. NEVER leave iron on.

7. BUYING VEGETABLES:
Pre-check: {find(type=shopping_bag)} — if missing, report ⚠️ NEEDS: shopping_bag.
           {check_state(vegetable_basket)} — if filled:true, skip and report
           "vegetable_basket already stocked".
SEQUENCE:
  Step 1 — {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}
  Step 2 — Simulate market trip:
    {goto_coordinate = T, 11}, {keep}
    {open(shopping_bag)}
    {set_state(shopping_bag, contents, fresh_vegetables)}
    {set_state(shopping_bag, filled, true)}
  Step 3 — Return:
    {goto_coordinate = T, 11}, {pickup}
    {goto_coordinate = UNPACK_COL, UNPACK_ROW}, {keep}
  Step 4 — Unpack:
    {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}
    {goto_coordinate = BASKET_COL, BASKET_ROW}, {place_into(vegetable_basket)}
    {set_state(vegetable_basket, filled, true)}
  Step 5 — {close(shopping_bag)}, return bag to storage.
  Step 6 — {check_state(vegetable_basket)} — confirm filled:true.
After buying → vegetables ready for COOKING task.

8. BATHROOM CLEANING:
Pre-check: {find(type=toilet_brush)} — if missing, report ⚠️ NEEDS: toilet_brush.
           {find(type=scrub_brush)} — if missing, report ⚠️ NEEDS: scrub_brush.
           {find(type=disinfectant)} — check fillLevel > 0.
           {find(type=bucket)} — needed for mopping solution.
SEQUENCE (strict order):
  Step 1 — Prepare solution:
    {fill(bucket, 100)}
    {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup}
    {twist_cap(disinfectant, off)}
    {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)}
    {twist_cap(disinfectant, on)}, return disinfectant, {keep}
  Step 2 — Toilet scrub (2 passes minimum):
    {scrub(TOILET_COORD)}
    {scrub(TOILET_COORD)}
  Step 3 — Sink area:
    {scrub(SINK_COORD)}
  Step 4 — Tiles and floor:
    {Apply_soap(FLOOR_CELLS)}
    {scrub(FLOOR_CELLS)}
    {mop(FLOOR_CELLS)}
  Step 5 — Clean tools:
    {wash(toilet_brush)}, {wash(scrub_brush)}
    {check_state(toilet_brush)}, {check_state(scrub_brush)} — confirm dirty:0
  Step 6 — Dispose dirty water:
    {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}, {fill(sink, 0)}
NEVER skip tool cleaning — dirty tools spread contamination.

9. DUSTING:
Pre-check: {find(type=duster)} — if missing, report ⚠️ NEEDS: duster.
           {find(dirty=true)} — identify objects/surfaces needing dusting.
SEQUENCE (always high-to-low — dust falls downward):
  Step 1 — Large/heavy objects first (oven, stove, sink, washing_machine):
    {Apply_cloth(OBJ_COORD)}
    If dirty > 60%: second pass immediately.
  Step 2 — Medium objects (boxes, baskets):
    {Apply_cloth(OBJ_COORD)}
  Step 3 — Small objects (plates, mugs, bottles, jars):
    {Apply_cloth(OBJ_COORD)}
  Step 4 — Open surfaces and empty cells:
    {Apply_cloth(A1,B1,...)} for each surface row.
  Step 5 — {check_state(duster)} — if dirty > 50%:
    {wash(duster)}, {check_state(duster)} confirm clean.
  Step 6 — Follow with sweep pass to catch fallen dust:
    {sweep(ALL_CELLS)}
FULL CLEAN ORDER: dust → sweep → mop. Never break this sequence.

10. TIDYING:
Pre-check: Read full board state — note every object's current position.
           {find(type=all)} to get complete inventory.
ZONE MAP (always organize into these zones):
  A1–D4:  Cleaning tools (broom, mop, bucket, brushes, disinfectant)
  E1–H4:  Dining (plates, bowls, mugs, glasses, cutlery, napkins)
  I1–L4:  Kitchen (stove, pot, pan, ingredient jars, cutting_board, knife)
  M1–P4:  Laundry (washing_machine, basket, clothes, iron, ironing_board)
  Q1–T4:  Pantry (bottles, boxes, vegetable_basket, shopping_bag)
  A5–T11: Clear working area — nothing stored here permanently.
SEQUENCE:
  Step 1 — Heavy appliances first (drag, never pickup):
    {drag_from_coordinate(FROM)_to_coordinate(TO)} for stove, sink,
    washing_machine, oven to correct zones.
  Step 2 — Medium objects (ironing_board, bucket):
    {pickup} → {goto_coordinate = TARGET} → {keep}
  Step 3 — Light objects in bulk, nearest-first:
    Same-category items placed adjacent to each other.
  Step 4 — Wipe all surfaces:
    {Apply_cloth(ALL_SURFACE_CELLS)}
  Step 5 — Final verification:
    {check_state()} on 3–4 key objects to confirm positions.
    Confirm working area A5–T11 is clear.
GROUPING RULE: same category items must TOUCH each other.
  All bottles adjacent. All mugs adjacent. Never mix categories.
`;



        function copyFullPrompt() {
            const boardState = getBoardContext();

            // Build a full object state table
            const objLines = objects.map((o, i) => {
                const x = Math.floor(o.position.x), z = Math.floor(o.position.z);
                const name = objectNames.get(o) || objectTypes.get(o) || 'unknown';
                const coord = `${String.fromCharCode(65 + x)}${z + 1}`;
                const fp = objectFootprint.get(o) || { w: 1, h: 1 };
                const st = objectState.get(o) || {};
                const wt = objectWeight.get(o);
                const cfg = getObjectConfig(objectTypes.get(o));
                const touching = getTouchingCoordinates(x, z, fp.w, fp.h);
                const stParts = [];
                if ('isOpen' in st) stParts.push(st.isOpen ? 'open' : 'closed');
                if ('power' in st) stParts.push(st.power ? 'power:ON' : 'power:OFF');
                if ('temperature' in st) stParts.push(`temp:${st.temperature}`);
                if ('fillLevel' in st) stParts.push(`fill:${Math.round(st.fillLevel * 100)}%`);
                if ('capOn' in st) stParts.push(st.capOn ? 'cap:on' : 'cap:off');
                if ('dirty' in st) stParts.push(`dirty:${Math.round(st.dirty * 100)}%`);
                if (st.sliced) stParts.push(`sliced:${st.pieces}pcs`);
                if ('wrinkled' in st) stParts.push(st.wrinkled ? 'wrinkled' : 'pressed');
                if ('folded' in st) stParts.push(st.folded ? 'folded' : 'unfolded');
                const fpStr = (fp.w > 1 || fp.h > 1) ? ` [${fp.w}x${fp.h}]` : '';
                return `  • ${name} @ ${coord}${fpStr}  wt:${wt}  [${cfg.affordances.join(', ')}]  {${stParts.join(', ')}}  touching: ${touching.join(', ')}`;
            });

            const chatCtx = chatHistory.length
                ? `\n\n— CONVERSATION HISTORY (last ${Math.min(chatHistory.length, 6)} turns) —\n` +
                  chatHistory.slice(-6).map(m => `[${m.role.toUpperCase()}]: ${m.content.substring(0, 400)}${m.content.length > 400 ? '…' : ''}`).join('\n\n')
                : '';

            const full = `════════════════════════════════════════
K5D ROBOT — FULL PROMPT EXPORT
Exported: ${new Date().toLocaleString()}
════════════════════════════════════════

━━━ SYSTEM PROMPT (EXECUTION) ━━━
${SYSTEM_PROMPT}

━━━ PLANNING PROMPT ━━━
${PLANNING_PROMPT}

━━━ CURRENT BOARD STATE ━━━
Gripper: ${boardState.split('.')[0]}.
Holding: ${heldObject ? (objectNames.get(heldObject) || objectTypes.get(heldObject)) : 'nothing'}.
Dragging: ${draggingObject ? (objectNames.get(draggingObject) || objectTypes.get(draggingObject)) : 'nothing'}.

Objects on board (${objects.length} total):
${objLines.join('\n') || '  (none)'}
${chatCtx}

━━━ HOW TO USE ━━━
Paste the SYSTEM PROMPT into your AI's system/instruction field.
Then send this as the user message:
  "Task: [describe what you want the robot to do]
   Current board state: [paste the BOARD STATE section above]"
════════════════════════════════════════`;

            navigator.clipboard.writeText(full).then(() => {
                const btn = document.querySelector('button[onclick="copyFullPrompt()"]');
                const orig = btn.textContent;
                btn.textContent = '✅ COPIED!';
                btn.classList.add('bg-emerald-700');
                setTimeout(() => { btn.textContent = orig; btn.classList.remove('bg-emerald-700'); }, 2000);
            }).catch(() => {
                // Fallback: show in a textarea modal the user can manually copy
                const modal = document.createElement('div');
                modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;';
                modal.innerHTML = `<div style="background:#18181b;border:1px solid #3f3f46;border-radius:12px;padding:20px;width:90%;max-width:700px;max-height:80vh;display:flex;flex-direction:column;gap:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="color:#a1a1aa;font-size:12px;font-weight:bold;">📋 FULL PROMPT — select all and copy</span>
                        <button onclick="this.closest('div[style]').remove()" style="color:#71717a;font-size:18px;background:none;border:none;cursor:pointer;">✕</button>
                    </div>
                    <textarea readonly style="flex:1;background:#09090b;color:#d4d4d8;font-size:11px;font-family:monospace;border:1px solid #3f3f46;border-radius:8px;padding:12px;resize:none;min-height:400px;outline:none;">${full.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</textarea>
                    <div style="color:#71717a;font-size:11px;">Press Ctrl+A then Ctrl+C to copy everything</div>
                </div>`;
                document.body.appendChild(modal);
                modal.querySelector('textarea').focus();
                modal.querySelector('textarea').select();
            });
        }

        function setInputLocked(locked) {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('chat-send-btn');
            input.disabled = locked;
            btn.disabled = locked;
        }
        function showPlanApproval(planText, meta) {
            document.getElementById('plan-text').textContent = planText;
            document.getElementById('plan-approval').classList.remove('hidden');
        }
        function hidePlanApproval() {
            document.getElementById('plan-approval').classList.add('hidden');
        }

        window.approvePlan = async function() {
            if (!pendingPlan) return;
            hidePlanApproval();
            setInputLocked(true);
            executionActive = true;
            appendMessage('assistant', '✅ Plan approved — generating commands...');
            appendThinking();
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-blue-400 rounded-full animate-pulse';
            try {
                // Refresh board state at execution time (not stale planning-time snapshot)
                const currentBoardState = getBoardContext();
                const execPrompt = `Approved plan to execute:
${pendingPlan}

Current board state: ${currentBoardState}

OUTPUT FORMAT: respond with ONLY a list of K5D commands, one per line, each wrapped in curly braces like {goto_coordinate = A, 1} or {pickup}. No explanation text, no markdown, no phase headers — just the raw commands in order. End with {Task_Completed}.`;
                const execHistory = [...chatHistory, { role: 'user', content: execPrompt }];
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ system: SYSTEM_PROMPT + buildMemoryContext(), messages: execHistory, max_tokens: 4000 })
                });
                const data = await res.json();
                const reply = data.reply || data.error || '';
                chatHistory.push({ role: 'user', content: execPrompt });
                chatHistory.push({ role: 'assistant', content: reply });
                document.getElementById('thinking-bubble')?.remove();
                function extractCommands(text) {
                    const commands = [...text.matchAll(/\{([^}]+)\}/g)].map(m => m[1].trim());
                    if (commands.length > 0) return commands;
                    const fallback = Array.from(text.matchAll(/(?:goto_coordinate\s*=\s*[A-T]\s*,\s*\d+|pickup|keep|pour|apply_soap\s*\([^)]*\)|apply_cloth\s*\([^)]*\)|drag_from_coordinate\s*\([^)]*\)\s*_to_coordinate\s*\([^)]*\)|change_orientation\s*(?:=|\()\s*[+-]?\s*[xyz]\s*-?\s*\d+|inspect_sides\s*(?:=|\()\s*[A-Za-z_][A-Za-z0-9_]*\)?|open\s*\([^)]*\)|close\s*\([^)]*\)|turn_on\s*\([^)]*\)|turn_off\s*\([^)]*\)|twist_cap\s*\([^)]*\)|fill\s*\([^)]*\)|pour_into\s*\([^)]*\)|place_into\s*\([^)]*\)|slice\s*\([^)]*\)|set_state\s*\([^)]*\)|check_state\s*\([^)]*\)|wait_for\s*\([^)]*\)|find\s*\([^)]*\)|sweep\s*\([^)]*\)|mop\s*\([^)]*\)|scrub\s*\([^)]*\)|wash\s*\([^)]*\)|run_cycle\s*\([^)]*\)|iron\s*\([^)]*\)|fold\s*\([^)]*\)|rotate_object\s*\([^)]*\)|task_completed)/gi), m => m[0].trim());
                    return fallback;
                }
                const commands = extractCommands(reply);
                if (commands.length === 0) {
                    appendMessage('assistant', reply || '⚠️ No commands generated.');
                } else {
                    const planText = commands.map((c, i) => `${i + 1}. ${c}`).join('\n');
                    appendMessage('assistant', `<div class="bg-zinc-700/50 border border-zinc-600 rounded-lg p-3">
                        <div class="text-xs font-bold text-emerald-300 mb-2">🔧 EXECUTING ${commands.length} STEPS:</div>
                        <pre class="text-xs text-emerald-400 overflow-x-auto font-mono">${planText}</pre>
                    </div>`);
                    setStatus(`<span class="w-2 h-2 bg-blue-400 rounded-full inline-block animate-pulse"></span>&nbsp;Executing...`);
                    await executeCommands(commands);
                    rememberTask(pendingUserText, pendingPlan, commands.length, true);
                }
            } catch(e) {
                document.getElementById('thinking-bubble')?.remove();
                appendMessage('assistant', '❌ Command generation error: ' + e.message);
                rememberTask(pendingUserText, pendingPlan, 0, false);
            }
            pendingPlan = null;
            executionActive = false;
            setInputLocked(false);
            document.getElementById('chat-input').focus();
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-emerald-400 rounded-full';
        };

        window.editPlan = function() {
            hidePlanApproval();
            const input = document.getElementById('chat-input');
            input.value = pendingUserText;
            input.disabled = false;
            document.getElementById('chat-send-btn').disabled = false;
            input.focus();
            appendMessage('assistant', '✏️ Plan discarded — edit your request below and resend.');
            pendingPlan = null;
            executionActive = false;
        };

        window.rejectPlan = function() {
            hidePlanApproval();
            appendMessage('assistant', '✖ Plan cancelled.');
            rememberTask(pendingUserText, pendingPlan || '', 0, false);
            pendingPlan = null;
            executionActive = false;
            setInputLocked(false);
        };

        window.sendTask = async function() {
            const input = document.getElementById('chat-input');
            const text = input.value.trim();
            if (!text || executionActive) return;
            // Handle special memory commands typed in chat
            if (text.toLowerCase().startsWith('remember:')) {
                const note = text.slice(9).trim();
                input.value = '';
                if (note) addMemoryNote(note);
                return;
            }
            if (text.toLowerCase() === 'memory' || text.toLowerCase() === 'show memory') {
                input.value = ''; showMemory(); return;
            }
            if (text.toLowerCase() === 'clear memory') {
                input.value = ''; clearMemory(); return;
            }
            input.value = '';
            setInputLocked(true);
            executionActive = true;
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-yellow-400 rounded-full animate-pulse';
            appendMessage('user', text);
            appendThinking();
            pendingUserText = text;
            pendingBoardState = getBoardContext();
            const memCtx = buildMemoryContext();

            // ── PHASE 1: Planning ────────────────────────────────────────────
            try {
                const planUserContent = `Task: "${text}"\n\nCurrent board state: ${pendingBoardState}${memCtx}`;
                const planHistory = [{ role: 'user', content: planUserContent }];
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ system: PLANNING_PROMPT, messages: planHistory, max_tokens: 600 })
                });
                const data = await res.json();
                const planReply = (data.reply || data.error || '').trim();
                document.getElementById('thinking-bubble')?.remove();

                // Extract just the plan text (strip "PLAN:" header if present)
                const cleanPlan = planReply.replace(/^PLAN:\s*/i, '').trim();
                pendingPlan = cleanPlan;

                appendMessage('assistant', `<div class="bg-zinc-700/50 border border-blue-500/30 rounded-lg p-3">
                    <div class="text-xs font-bold text-blue-300 mb-2">📋 PLAN</div>
                    <pre class="text-xs text-zinc-200 whitespace-pre-wrap leading-relaxed">${cleanPlan}</pre>
                </div>`);

                showPlanApproval(cleanPlan, '');
                chatHistory.push({ role: 'user', content: planUserContent });
                chatHistory.push({ role: 'assistant', content: planReply });

                // Unlock input so user can type while reviewing (but send btn stays
                // pointing to the approval flow, not a new task)
                document.getElementById('chat-input').disabled = false;
                document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-yellow-400 rounded-full';
                // Leave executionActive = true so sendTask won't fire again during review

            } catch(e) {
                document.getElementById('thinking-bubble')?.remove();
                appendMessage('assistant', '❌ Planning error: ' + e.message);
                pendingPlan = null;
                executionActive = false;
                setInputLocked(false);
                document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-zinc-600 rounded-full';
            }
        };

        // ── Quick Task Popup ─────────────────────────────────────────────────
        const TASK_SUGGESTIONS = {
            'Sweeping': [
                { emoji: '🧹', name: 'Broom', note: 'required — sweeps the floor' },
                { emoji: '🗑️', name: 'Dustpan', note: 'optional — collects swept dust' },
            ],
            'Mopping': [
                { emoji: '🧻', name: 'Mop', note: 'required — wet-mops the floor' },
                { emoji: '🪣', name: 'Bucket', note: 'required — holds cleaning solution' },
                { emoji: '💜', name: 'Disinfectant', note: 'recommended — add to bucket' },
                { emoji: '🧹', name: 'Broom', note: 'recommended — sweep before mopping' },
            ],
            'Washing utensils': [
                { emoji: '🧼', name: 'Soap Bottle', note: 'required — apply soap to each utensil' },
                { emoji: '🧽', name: 'Cloth', note: 'recommended — wipe clean after soaping' },
                { emoji: '🍽️', name: 'Plate', note: 'add dirty utensils to wash' },
                { emoji: '🥣', name: 'Bowl', note: 'add dirty utensils to wash' },
                { emoji: '☕', name: 'Mug', note: 'add dirty utensils to wash' },
                { emoji: '🍲', name: 'Pot', note: 'add dirty utensils to wash' },
                { emoji: '🍳', name: 'Pan', note: 'add dirty utensils to wash' },
            ],
            'Cooking': [
                { emoji: '🔥', name: 'Stove / Hob', note: 'required — heat source' },
                { emoji: '🍲', name: 'Pot', note: 'required — place on stove' },
                { emoji: '🧺', name: 'Veg Basket', note: 'required — goes into the pot' },
                { emoji: '🍽️', name: 'Plate', note: 'required — cooked food plated here' },
            ],
            'Washing clothes': [
                { emoji: '🫧', name: 'Washing Machine', note: 'required — runs the wash cycle' },
                { emoji: '🧴', name: 'Detergent', note: 'required — add before cycle' },
                { emoji: '👕', name: 'Clothes Pile', note: 'add dirty clothes to wash' },
                { emoji: '👕', name: 'Shirt', note: 'optional — individual garment' },
                { emoji: '👖', name: 'Pants', note: 'optional — individual garment' },
            ],
            'Folding and ironing clothes': [
                { emoji: '🪄', name: 'Iron', note: 'required — must heat to hot' },
                { emoji: '📐', name: 'Ironing Board', note: 'required — ironing surface' },
                { emoji: '👕', name: 'Clothes Pile', note: 'add wrinkled clothes to iron' },
                { emoji: '👕', name: 'Shirt', note: 'optional — individual garment' },
                { emoji: '👖', name: 'Pants', note: 'optional — individual garment' },
            ],
            'Cutting vegetables': [
                { emoji: '🗡️', name: 'Knife', note: 'required — the cutting tool' },
                { emoji: '🔪', name: 'Cutting Board', note: 'required — prep surface' },
                { emoji: '🥕', name: 'Carrot', note: 'sliceable vegetable' },
                { emoji: '🥒', name: 'Cucumber', note: 'sliceable vegetable' },
                { emoji: '🍅', name: 'Tomato', note: 'sliceable vegetable' },
                { emoji: '🧅', name: 'Onion', note: 'sliceable vegetable' },
                { emoji: '🥔', name: 'Potato', note: 'sliceable vegetable' },
                { emoji: '🫑', name: 'Bell Pepper', note: 'sliceable vegetable' },
                { emoji: '🥦', name: 'Broccoli', note: 'sliceable vegetable' },
            ],
            'Cleaning the bathroom and toilet': [
                { emoji: '🚽', name: 'Toilet Brush', note: 'required — scrubs toilet' },
                { emoji: '🪥', name: 'Scrub Brush', note: 'required — scrubs tiles/sink' },
                { emoji: '💜', name: 'Disinfectant', note: 'required — sanitises surfaces' },
                { emoji: '🪣', name: 'Bucket', note: 'required — mopping solution' },
                { emoji: '🧻', name: 'Mop', note: 'recommended — mops the floor' },
                { emoji: '🚰', name: 'Sink', note: 'optional — represents bathroom sink' },
            ],
            'Dusting furniture and surfaces': [
                { emoji: '🪶', name: 'Duster', note: 'required — dusts all surfaces' },
                { emoji: '🧹', name: 'Broom', note: 'recommended — sweeps fallen dust' },
                { emoji: '📦', name: 'Box', note: 'add furniture/objects to dust' },
                { emoji: '🪵', name: 'Wooden Box', note: 'add furniture/objects to dust' },
            ],
            'Tidying up the board': [
                { emoji: '📦', name: 'Box', note: 'add any objects you want tidied' },
                { emoji: '🍼', name: 'Bottle', note: 'add objects from any category' },
                { emoji: '🧹', name: 'Broom', note: 'add cleaning tools to sort' },
                { emoji: '🔥', name: 'Stove / Hob', note: 'add appliances to zone' },
                { emoji: '🫧', name: 'Washing Machine', note: 'add laundry items to zone' },
            ],
        };

        let pendingTaskPrompt = '';
        window.showTaskPopup = function(name, prompt) {
            pendingTaskPrompt = prompt;
            document.getElementById('popup-title').textContent = name;

            // Build suggestions list
            const suggestions = TASK_SUGGESTIONS[name] || [];
            const container = document.getElementById('popup-suggestions');
            if (suggestions.length === 0) {
                container.innerHTML = '<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#52525b;">No specific requirements — add relevant objects from the library.</div>';
            } else {
                container.innerHTML = suggestions.map(s =>
                    `<div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:16px;width:22px;text-align:center;">${s.emoji}</span>
                        <div style="flex:1;">
                            <span style="font-family:'Syne',sans-serif;font-size:12px;font-weight:600;color:#e4e4e7;">${s.name}</span>
                            <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#52525b;margin-left:6px;">${s.note}</span>
                        </div>
                    </div>`
                ).join('');
            }

            const popup = document.getElementById('task-popup');
            popup.style.display = 'flex';
        };
        window.closeTaskPopup = function() {
            document.getElementById('task-popup').style.display = 'none';
        };
        window.confirmTaskPopup = function() {
            document.getElementById('task-popup').style.display = 'none';
            if (!pendingTaskPrompt) return;
            const input = document.getElementById('chat-input');
            input.value = pendingTaskPrompt;
            sendTask();
        };

        window.onload = function() { initThree(); animate(); };
    </script>
</body>
</html>"""

OPENAI_API_KEY = "ADD YOUR OPENAI API KEY HERE"

import urllib.request

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            system_prompt = body.get("system", "")
            messages = body.get("messages", [])
            max_tokens = body.get("max_tokens", 4000)
            oai_messages = [{"role": "system", "content": system_prompt}] + messages
            payload = json.dumps({
                "model": "gpt-4o",
                "messages": oai_messages,
                "max_tokens": max_tokens,
                "temperature": 0
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                reply = data["choices"][0]["message"]["content"]
                result = json.dumps({"reply": reply}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(result)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("K5D Simulator → http://localhost:8080")
    webbrowser.open("http://localhost:8080")
    server.serve_forever()
