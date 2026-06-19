from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import webbrowser

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>K3D</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;600;700;800&display=swap');
        body { font-family: 'Syne', sans-serif; }
        #canvas-container {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 1;
            background: #000000;
        }
        .ui-overlay { position: absolute; z-index: 10; pointer-events: none; }
        .ui-overlay > * { pointer-events: auto; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        select { appearance: none; -webkit-appearance: none; }
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
<body class="bg-zinc-950 text-zinc-200 overflow-hidden">
    <div class="ui-overlay top-0 left-0 right-0 bg-black/90 backdrop-blur border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center gap-x-3">
            <div class="w-9 h-9 bg-blue-500 rounded-xl flex items-center justify-center text-white font-bold text-xl">K</div>
            <div>
                <h1 class="text-xl font-bold tracking-tight">K3D · Precision Cartesian Gantry</h1>
                <p class="text-xs text-zinc-400 mono">Prolabs V12.2 · AI-Controlled · XYZ-Axis</p>
            </div>
        </div>
        <div class="flex items-center gap-x-3">
            <div id="status" class="px-5 py-2 bg-emerald-900/50 text-emerald-400 rounded-full text-xs font-semibold mono flex items-center gap-x-2">
                <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                READY
            </div>
            <button onclick="takeTopDownScreenshot()"
                    class="px-5 py-2 bg-violet-700 hover:bg-violet-600 transition-colors rounded-full text-xs font-semibold">
                📸 SCREENSHOT (2D)
            </button>
            <button onclick="resetToHome()"
                    class="px-5 py-2 bg-zinc-800 hover:bg-zinc-700 transition-colors rounded-full text-xs font-semibold">
                RESET HOME (A1)
            </button>
        </div>
    </div>
    <div id="canvas-container"></div>
    <div class="ui-overlay top-20 left-6 bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl w-72 p-4" style="max-height: calc(100vh - 96px); overflow-y: auto;">
        <h2 class="text-xs font-bold mb-3 text-zinc-300 tracking-widest uppercase">Target Coordinate</h2>
        <div class="flex gap-2 mb-3">
            <div class="flex-1">
                <label class="text-xs text-zinc-500 mono mb-1 block">X AXIS</label>
                <select id="x-letter" class="w-full bg-zinc-800 border border-zinc-700 focus:border-blue-500 rounded-xl px-3 py-2 text-lg font-bold text-center mono cursor-pointer"></select>
            </div>
            <div class="flex items-end justify-center pb-2 text-xl text-zinc-600">×</div>
            <div class="flex-1">
                <label class="text-xs text-zinc-500 mono mb-1 block">Y AXIS</label>
                <select id="y-number" class="w-full bg-zinc-800 border border-zinc-700 focus:border-blue-500 rounded-xl px-3 py-2 text-lg font-bold text-center mono cursor-pointer"></select>
            </div>
        </div>
        <div class="mb-3">
            <label class="text-xs text-zinc-500 mono mb-1 flex justify-between"><span>Z AXIS HEIGHT</span><span id="z-label" class="text-blue-400">4.0</span></label>
            <input type="range" id="z-slider" min="0.5" max="7" step="0.1" value="4.0"
                   class="w-full h-2 bg-zinc-700 rounded-full outline-none cursor-pointer accent-blue-500"
                   oninput="onZSlider(this.value)">
            <div class="flex justify-between text-xs mono text-zinc-600 mt-1"><span>LOW</span><span>HIGH</span></div>
        </div>
        <button onclick="moveGripper()"
                class="w-full bg-blue-600 hover:bg-blue-500 py-2 rounded-xl text-white font-bold text-sm mb-2 transition-colors">
            MOVE GRIPPER
        </button>
        <div class="grid grid-cols-3 gap-2 mb-3">
            <button onclick="doPickup()"
                    class="bg-amber-600 hover:bg-amber-500 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                PICKUP
            </button>
            <button onclick="doKeep()"
                    class="bg-emerald-700 hover:bg-emerald-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                PLACE
            </button>
            <button onclick="doPour()"
                    class="bg-violet-700 hover:bg-violet-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                POUR
            </button>
        </div>
        <div class="bg-zinc-800/70 border border-zinc-700/40 rounded-xl p-3">
            <div class="text-xs mono text-zinc-500 mb-1">POSITION</div>
            <div id="current-position" class="mono text-2xl font-bold text-blue-400">A1</div>
            <div id="current-coords" class="mono text-xs text-zinc-400 mt-1">(0.0, 0.0, 4.0)</div>
            <div id="gripper-state" class="mono text-xs text-zinc-500 mt-1">Gripper: OPEN</div>
        </div>
    </div>

    <div class="ui-overlay top-20 right-6 bottom-6 w-80 flex flex-col gap-0">
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
                    <div class="text-xs font-bold text-zinc-200 tracking-widest uppercase">K3D Task Planner</div>
                    <div class="text-xs text-zinc-500 mono">Prolabs V12.2 · Claude</div>
                </div>
                <div id="ai-status-dot" class="ml-auto w-2 h-2 bg-zinc-600 rounded-full"></div>
            </div>
            <div id="exec-log" class="shrink-0 px-3 pt-2 pb-1 border-b border-zinc-800/50 overflow-y-auto" style="max-height: 120px; display:none;">
                <div class="text-xs mono text-zinc-500 mb-1 uppercase tracking-widest">Execution Plan</div>
                <div id="exec-log-entries"></div>
            </div>
            <div id="chat-messages" class="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
                <div class="flex gap-2">
                    <div class="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">AI</div>
                    <div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-300 leading-relaxed">Hi! I'm the K3D Task Planner. Tell me what to do — I'll plan and execute the moves automatically. Try: <span class="text-blue-400">"Move bottle to C3"</span>, <span class="text-blue-400">"Pick up the box and place it at F5"</span>, or <span class="text-blue-400">"Soap the plate"</span>.</div>
                </div>
            </div>
            <div class="px-3 pb-3 pt-2 border-t border-zinc-800 shrink-0">
                <div class="flex gap-2">
                    <input id="chat-input" type="text" placeholder="Describe a task to execute..."
                        class="flex-1 bg-zinc-800 border border-zinc-700 focus:border-blue-500 rounded-xl px-3 py-2 text-xs text-zinc-200 outline-none mono placeholder-zinc-600"
                        onkeydown="if(event.key==='Enter')sendTask()">
                    <button onclick="sendTask()" id="chat-send-btn" class="bg-blue-600 hover:bg-blue-500 transition-colors rounded-xl px-3 py-2 text-white text-xs font-bold">▶</button>
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

    <div class="ui-overlay bottom-6 left-6 bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl p-5 w-80" style="max-height: 48vh; overflow-y: auto;">
        <div class="mb-4 rounded-2xl bg-zinc-800/80 border border-zinc-700/50 p-3">
            <div class="flex items-center justify-between mb-2">
                <div class="text-xs font-bold uppercase tracking-widest text-zinc-300">Change Orientation</div>
                <div class="text-[10px] text-zinc-500 mono">All objects</div>
            </div>
            <div class="grid grid-cols-3 gap-2">
                <button onclick="rotateAllObjects('x', 90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    X +90
                </button>
                <button onclick="rotateAllObjects('x', -90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    X -90
                </button>
                <button onclick="rotateAllObjects('y', 90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    Y +90
                </button>
                <button onclick="rotateAllObjects('y', -90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    Y -90
                </button>
                <button onclick="rotateAllObjects('z', 90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    Z +90
                </button>
                <button onclick="rotateAllObjects('z', -90)"
                        class="bg-slate-700 hover:bg-slate-600 py-2 rounded-xl text-white font-bold text-xs transition-colors">
                    Z -90
                </button>
            </div>
        </div>
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
            <div class="obj-lib-wrap obj-lib-entry" onclick="addObject('laundry_basket')">
                <div class="text-3xl mb-1">🧺</div>
                <span class="text-xs text-zinc-400">Laundry Basket</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">laundry_basket</div><div>Carries dirty clothes to and from the machine.</div></div>
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
                <div class="text-3xl mb-1">🫧</div>
                <span class="text-xs text-zinc-400">Detergent</span>
                <div class="obj-lib-meta"><div class="font-bold text-zinc-200 mb-1">detergent</div><div>Laundry detergent. Pour into washing machine before cycle.</div></div>
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
        function setGripperState(s) { document.getElementById('gripper-state').textContent = 'Gripper: ' + s; }

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
            } else if (t.includes('laundry_basket')) {
                cfg.affordances = ['liftable', 'openable']; cfg.weight = 3;
                cfg.defaultState = { isOpen: true, dirty: 0 };
            } else if (t.includes('clothes_pile') || t.includes('clothes')) {
                cfg.affordances = ['liftable', 'foldable', 'ironable']; cfg.weight = 2;
                cfg.defaultState = { folded: false, ironed: false, wrinkled: true, dirty: 0.6 };
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
            for (const obj of objects) {
                const ox = Math.floor(obj.position.x), oz = Math.floor(obj.position.z);
                const fp = objectFootprint.get(obj) || { w: 1, h: 1 };
                if (cx >= ox && cx < ox + fp.w && cz >= oz && cz < oz + fp.h) return obj;
            }
            return null;
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
            const sprite = createNameLabel(type);
            sprite.position.set(rx, 2.7, ry);
            scene.add(sprite);
            objectSprites.set(obj, sprite);
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
            else if (type === 'laundry_basket') obj = createLaundryBasket();
            else if (type === 'clothes_pile') obj = createClothesPile();
            else if (type === 'iron') obj = createIron();
            else if (type === 'ironing_board') obj = createIroningBoard();
            else if (type === 'detergent') obj = createDetergent();
            else if (type === 'stove') obj = createStove();
            else if (type === 'ingredient_jar') obj = createIngredientJar();
            else if (type === 'vegetable_basket') obj = createVegetableBasket();
            else if (type === 'shopping_bag') obj = createShoppingBag();
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
        function createLaundryBasket() {
            const g = new THREE.Group();
            const mat = new THREE.MeshPhongMaterial({ color: 0xd97706, wireframe: false });
            const body = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.58, 1.4, 16), mat);
            body.position.y = 0.7; g.add(body);
            for (let i = 0; i < 16; i++) {
                const slot = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.55, 0.06), new THREE.MeshPhongMaterial({ color: 0x92400e }));
                const a = (i / 16) * Math.PI * 2;
                slot.position.set(Math.cos(a) * 0.71, 0.75, Math.sin(a) * 0.71); g.add(slot);
            }
            const rim = new THREE.Mesh(new THREE.TorusGeometry(0.73, 0.06, 6, 20), new THREE.MeshPhongMaterial({ color: 0xb45309 }));
            rim.rotation.x = Math.PI / 2; rim.position.y = 1.4; g.add(rim);
            const handle1 = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.04, 6, 12, Math.PI), new THREE.MeshPhongMaterial({ color: 0x78350f }));
            handle1.position.set(0.65, 1.55, 0); g.add(handle1);
            const handle2 = handle1.clone(); handle2.position.set(-0.65, 1.55, 0); handle2.rotation.y = Math.PI; g.add(handle2);
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

        function updateObjectPositionsDisplay() {
            const list = document.getElementById('objects-list');
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
                ctx.fillText('K3D Prolabs V12.2 · Top-Down View · ' + new Date().toLocaleString(), 16, GRID_PX_H + 32);
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
            const col = String.fromCharCode(65 + ox), row = String.fromCharCode(49 + oz);
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
            const col = String.fromCharCode(65 + ox), row = String.fromCharCode(49 + oz);
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
        async function runFold(raw) {
            const m = raw.match(FOLD_RE);
            if (!m) { setStatus('⚠️ Invalid fold command'); return; }
            const obj = findObjectByKey(m[1]);
            if (!obj) { appendMessage('assistant', `⚠️ No object named "${m[1]}" found.`); return; }
            const cfg = getObjectConfig(objectTypes.get(obj));
            if (!cfg.affordances.includes('foldable')) { appendMessage('assistant', `⚠️ "${m[1]}" cannot be folded.`); return; }
            const st = objectState.get(obj) || {};
            if (st.wrinkled) { appendMessage('assistant', `⚠️ "${m[1]}" is still wrinkled — iron it first for a neat fold.`); }
            const name = objectNames.get(obj) || objectTypes.get(obj) || 'item';
            isAnimating = true; setStatus(`👕 Folding ${name}...`);
            await delay(800);
            // Visually compress the object to look folded
            obj.scale.set(0.75, 0.55, 0.75);
            isAnimating = false;
            st.folded = true;
            objectState.set(obj, st); updateObjectPositionsDisplay();
            setStatus(`✅ ${name} folded`);
            appendMessage('assistant', `✅ "${name}" folded neatly.`);
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
          const SYSTEM_PROMPT = `You are K3D — an autonomous task planner for the Prolabs V12.2 Precision Cartesian Gantry robot.

The board is a grid with columns A-T (left to right, 20 columns) and rows 1-11 (front to back, 11 rows).

Each object reported in the board state includes its "touching" coordinates — up to 8 adjacent grid cells (orthogonal + diagonal neighbors), clipped at board edges. Use these to understand what's immediately around an object before moving, dragging, or placing something nearby.

Every object also reports a STATE block in curly braces (e.g. {open, power ON, fill:40%, weight:3}) and may report a "WxH footprint" if it occupies more than one cell (e.g. the oven is 2x2). Use these to reason about what's actually possible: an object that's "closed" can't have things put inside it, a "powered OFF" appliance won't heat, an empty bottle has nothing to pour, and an object whose weight exceeds the lift limit must be DRAGGED rather than picked up. The gantry also avoids driving straight through other objects — if a direct path is blocked it will automatically route around via a short detour, so plan paths sensibly but don't worry about exact collision math yourself.

**OUTPUT FORMAT:**
1. First, provide a DETAILED high-level plan (3-5 sentences) that includes:
   - What object(s) you'll manipulate
   - Where they are and where they're going
   - Any orientation changes needed and WHY
   - The overall strategy and reasoning
2. Then, output ONLY a sequence of commands — no explanations, no commentary, no punctuation outside the command format

Example output with orientation:
"I need to open the oven to insert the cookies. First, I'll inspect the oven's sides to understand how it opens. Then I'll rotate it +x90 degrees so the door faces up and is accessible. After that, I'll pick up the cookies from B2, move to the oven at D5, and insert them. Finally, I'll rotate the oven back to its original orientation and place the cookies inside.
{inspect_sides = oven}
{change_orientation = +x90}
{goto_coordinate = B, 2}
{pickup}
{goto_coordinate = D, 5}
{keep}
{change_orientation = -x90}
{Task_Completed}"

Valid commands:
{goto_coordinate = COL, ROW}
{pickup}
{keep}
{pour}
{Apply_soap(X1, X2, X3, ...)}
{Apply_cloth(X1, X2, X3, ...)}
{drag_from_coordinate(COL, ROW)_to_coordinate(COL, ROW)}
{change_orientation = +z90} or {change_orientation(+z90)}   # rotate all objects around axis (six allowed tokens: +x90, -x90, +y90, -y90, +z90, -z90)
{inspect_sides = OBJECT_NAME} or {inspect_sides(OBJECT_NAME)} # request a side-summary report for an object (top/bottom/left/right/front/back)
{open(OBJECT_NAME)}                          # open a door/lid — requires the "openable" affordance
{close(OBJECT_NAME)}                         # close a door/lid
{turn_on(OBJECT_NAME)}                       # power on a switchable appliance (e.g. oven) — requires "switchable"
{turn_off(OBJECT_NAME)}                      # power off a switchable appliance
{twist_cap(OBJECT_NAME, on)} or {twist_cap(OBJECT_NAME, off)}  # twist a bottle/container cap — requires "twistable_cap"
{fill(OBJECT_NAME, PERCENT)}                 # directly set a fillable object's contents to PERCENT (0-100)
{pour_into(OBJECT_NAME)}                     # pour the held/current pourable object's contents into the named fillable target — real volume transfer, can overflow
{slice(OBJECT_NAME, N)}                      # slice a sliceable object into N pieces — requires "sliceable"
{set_state(OBJECT_NAME, KEY, VALUE)}         # generic escape hatch — set ANY state key on an object directly (use this if no dedicated command fits, e.g. {set_state(towel, folded, true)})
{check_state(OBJECT_NAME)}                   # sensor-style report of an object's full current state (open/closed, power, temperature, fill level, cap, dirty %, sliced, weight, affordances, touching cells)
{wait_for(SECONDS)}                          # pause execution to simulate waiting (e.g. for preheating) — capped at 10s of real time
{find(KEY=VALUE)}                            # search all board objects by attribute: color, type, name, weight, size (small/medium/large), or any state key (e.g. {find(power=true)} or {find(color=#3355ff)})
{sweep(X1, X2, X3, ...)}                    # sweep floor cells with broom — reduces dust/dirty on any objects at those cells (broom must be on board)
{mop(X1, X2, X3, ...)}                      # wet-mop floor cells — reduces dirty more than sweep; needs bucket with disinfectant solution for full effect
{scrub(X1, X2, ...)}                         # heavy-duty scrub of surface cells (bathroom tiles, toilet) — requires scrub_brush or toilet_brush; reduces dirty by 85%
{wash(OBJECT_NAME)}                          # wash a specific object clean at its current cell (soapy water from sink or bucket); sets dirty:0
{run_cycle(OBJECT_NAME)}                     # run a full machine cycle (washing_machine) — door must be CLOSED; auto-cleans clothes nearby
{iron(OBJECT_NAME)}                          # iron a cloth/clothes item to remove wrinkles — iron must be powered on and hot
{fold(OBJECT_NAME)}                          # fold a foldable item (clothes_pile, towel) — iron FIRST for a crisp fold
{Task_Completed}

COORDINATE FORMAT inside Apply_soap / Apply_cloth: always ColRow with no space, e.g. A1, B3, T11.

Rules:
- Always go to the exact center of an object before picking it up
- Only pick up one object at a time
- After placing, output {Task_Completed} when done
- No text outside curly braces — commands only
- Always end with {Task_Completed}

Orientation helper:
CRITICAL: Use ONLY X-axis or Z-axis rotations. Y-axis rotations are NOT useful—they spin objects in place without exposing new interaction faces.

Valid rotation commands (only these):
  {change_orientation = +x90}  → Left face (−x) becomes TOP
  {change_orientation = -x90}  → Right face (+x) becomes TOP
  {change_orientation = +z90}  → Back face (−z) becomes TOP
  {change_orientation = -z90}  → Front face (+z) becomes TOP

Coordinate system:
  - X-axis: left (−x) ↔ right (+x)  [columns A-T]
  - Z-axis: back (−z) ↔ front (+z)  [rows 1-11]
  - Y-axis: bottom (−y) ↔ top (+y)  [vertical, always 0 to 3.0]

Examples:
  - Oven door is on the RIGHT side → use {change_orientation = -x90} to make right-side the new top, then access
  - Object's FRONT is facing you → use {change_orientation = -z90} to bring front-face to the top
  - Pick from object's LEFT side → use {change_orientation = +x90} to make left-face the new top

After rotating, grid coordinates (A1, B5, etc.) stay the same—only the object orientations change so a side face acts as the new TOP for grasping.

Inspection helper:
- Use {inspect_sides = OBJECT_NAME} to request a side-contact report for the named object.
- The runtime returns what is touching each of the 6 sides in world coordinates:
  * TOP (facing up, +y direction)
  * BOTTOM (facing down, −y direction)
  * LEFT (facing −x direction)
  * RIGHT (facing +x direction)
  * FRONT (facing +z direction)
  * BACK (facing −z direction)
- Example response: "Side inspection for 'oven': Top: none; Left: mug @ B3; Right: none; Front: plate @ H5; Back: none; Bottom: table"
- Use {inspect_sides = ...} FIRST to see what's touching each side. Then decide which side you need to access, and rotate to bring it to the top.

Example workflow — access the oven's right-side door to load cookies:
{inspect_sides = oven}         # see what's around it
{change_orientation = -x90}    # bring RIGHT side to top so the door-face is now graspable from top
{goto_coordinate = C, 4}       # move to the oven
{pickup}                       # grab the top (now the side-door)
...
{Task_Completed}

Drag helper:
- Use {drag_from_coordinate(COL, ROW)_to_coordinate(COL, ROW)} to SLIDE an object along the ground from one cell to another WITHOUT lifting it.
- The gripper moves to the source cell, lowers, contacts the object, drags it across the surface to the destination cell, then releases and retracts.
- Use this instead of {pickup} + {goto_coordinate} + {keep} when an object is too wide or heavy to cleanly lift, when you just need to push something out of the way, or when a sliding motion is more natural than a lift-and-place.
- Example: {drag_from_coordinate(B,3)_to_coordinate(F,3)}

Object inventory & default interaction methods:
- bottle (water_bottle): tall, graspable at neck — **grab from TOP** · weight 1 · pourable, fillable, twistable_cap (starts full, cap ON)
- soap_bottle: dispenser with pump — **grab from TOP**, pump to dispense · weight 1 · pourable, fillable, twistable_cap (starts full, cap ON)
- mug: open-top with handle — **grab HANDLE (side)** · weight 1 · pourable, fillable (starts empty)
- plate: flat, shallow — **grab from edge (TOP)** · weight 1 · liftable only
- glass: hollow, delicate — **grab from SIDE** · weight 1 · pourable, fillable (starts empty)
- box / wooden_box: enclosed with lid — **open from TOP or SIDE** · weight 3-4 · openable (starts closed) — use {open(...)}/{close(...)}, not change_orientation, to access contents
- powder_box: container with lid — **grab from SIDE or remove lid from TOP** · weight 2 · openable, pourable, fillable (starts full, closed)
- oven: appliance with door, 2x2 footprint — **open DOOR with {open(oven)}**, power with {turn_on(oven)}/{turn_off(oven)} · weight 25 (TOO HEAVY TO LIFT — never {pickup}; use {drag_from_coordinate...} if it must move) · openable, switchable, heatable (starts closed, off, room temp)
- cookies: stack of items — **grab from TOP** · weight 1 · sliceable (starts unsliced)
- cutting_board: flat work surface — **grab from SIDE or edge** · weight 2 · liftable only
- knife: sharp utensil — **grasp HANDLE (side)** · weight 1 · cutting_tool (bring to the same cell as a sliceable object before {slice(...)})
- pot: container with handles — **grab HANDLE (left/right SIDE) or fill from TOP** · weight 3 · pourable, fillable, heatable (starts empty, room temp)
- pan: shallow container with handle — **grab HANDLE (side) or work from TOP** · weight 3 · pourable, fillable, heatable (starts empty, room temp)
- spoon: utensil — **grab HANDLE (side or top)** · weight 1 · liftable only
- bowl: hollow container — **grab RIM (side) or fill from TOP** · weight 2 · pourable, fillable (starts empty)
- napkins: stack of sheets — **pull from TOP** · weight 1 · cleaning_tool
- towel: folded cloth — **grab from SIDE or TOP corner** · weight 1 · cleaning_tool, foldable (starts unfolded — use {set_state(towel, folded, true)})
- plant: potted — **grab pot from SIDE or TOP** · weight 2 · liftable only
- book: flat object — **grab spine (SIDE) or edge (TOP)** · weight 1 · liftable only
- water_cup: small filled cup — **grab carefully from SIDE** · weight 1 · pourable, fillable (starts empty)
- Custom / uploaded STL objects default to: weight 2, 1x1 footprint, liftable only (no special affordances) unless you {set_state(...)} them yourself.

Weight & lifting rule:
- Every object has a weight. The gripper's lift limit is ${MAX_LIFT_WEIGHT} — anything heavier (like the oven) CANNOT be picked up with {pickup}; attempting it will fail with a warning.
- For heavy objects, use {drag_from_coordinate(...)_to_coordinate(...)} to slide them along the ground instead — dragging has no weight limit.
- Use {check_state(OBJECT_NAME)} or read the board state's weight field if you're unsure whether an object can be lifted.

State & affordances helper:
- Objects only respond to commands that match their affordances (reported in board state and via {check_state}/{inspect_sides}). E.g. {open(...)} only works on "openable" objects, {pour_into(...)} requires the source to be "pourable" and the target "fillable".
- If you try a command an object doesn't support, you'll get a warning message back — read it and adjust your plan.
- {set_state(OBJECT_NAME, KEY, VALUE)} is a generic fallback for any custom state you need to track that doesn't have a dedicated command (booleans, numbers, or short text).

Opening & closing rule (doors, lids, boxes):
- Use {open(OBJECT_NAME)} / {close(OBJECT_NAME)} for any "openable" object (box, wooden_box, powder_box, oven). This is the correct way to access contents — do NOT use {change_orientation} for this purpose; orientation only re-exposes a side face for picking, it does not represent a door swinging open.
- Example — load something into the oven:
{open(oven)}
{goto_coordinate = B, 2}
{pickup}
{goto_coordinate = D, 5}
{keep}
{close(oven)}
{Task_Completed}

Power & heating rule:
- Switchable appliances (oven) are turned on/off with {turn_on(OBJECT_NAME)} / {turn_off(OBJECT_NAME)}.
- Heatable + switchable objects need time to heat up: after {turn_on(oven)}, its temperature becomes "preheating" then automatically becomes "hot" a few seconds later. Use {wait_for(SECONDS)} after turning it on if your task depends on it being hot, then {check_state(oven)} to confirm before proceeding.

Liquid & filling rule:
- Pourable objects (bottle, mug, glass, bowl, pot, pan, water_cup, soap_bottle, powder_box) track a real fill level (0-100%).
- To pour from a held/current object into a named container: {pour_into(OBJECT_NAME)} — this transfers liquid up to the target's remaining capacity; if the target is already full, excess remains in the source and may spill (you'll be told).
- A bottle/soap_bottle with its cap ON cannot be poured — use {twist_cap(OBJECT_NAME, off)} first, and {twist_cap(OBJECT_NAME, on)} afterward if it should be resealed.
- To set a fill level directly without animating a pour (e.g. "the mug should start half full" as a scenario setup), use {fill(OBJECT_NAME, PERCENT)}.
- The legacy {pour} command (no target) still works as a simple tilt animation when you don't need real volume transfer.

Slicing rule:
- Only "sliceable" objects (e.g. cookies) can be cut. Bring a knife to the same cell as the target first, then use {slice(OBJECT_NAME, N)} to mark it as cut into N pieces. The cut is tracked as state (reported via {check_state}) — it is not rendered as separate visual pieces.

Cleaning verification rule:
- Objects can carry a "dirty" percentage. {Apply_soap(...)} reduces dirtiness by ~25% per pass and {Apply_cloth(...)} by ~35% per pass for any object at that coordinate.
- For cleaning tasks, use {check_state(OBJECT_NAME)} afterward to confirm dirty% has actually reached 0 rather than assuming one pass is enough — repeat the soap/cloth coordinates if it hasn't.

Sensing & search rule:
- {check_state(OBJECT_NAME)} and {find(KEY=VALUE)} act as the robot's "sensors" — use them when you're unsure of an object's current condition or which object matches a vague description (e.g. "the heavy box" → {find(size=large)}, "the open container" → {find(isOpen=true)}).
- Because each chat turn executes a full plan in one pass, use {wait_for(...)} plus {check_state(...)} together when a task genuinely depends on something changing over time (like preheating); for tasks that depend on information you don't have yet, it's also fine to run a sensing command, see the reported result, and issue a follow-up message with the next steps.

Collision-awareness note:
- The gantry will not let itself be driven straight through another object's footprint — if a direct path is obstructed it automatically takes a short L-shaped detour. You don't need to manually route around obstacles, but be aware moves near cluttered areas may take a slightly longer path.

When interacting with an object, use {inspect_sides = OBJECT_NAME} first to see what's adjacent, then use {change_orientation = ...} to rotate that side into position as the new TOP if needed.

SOAP RULE:
1. Pick up the soap first with {pickup}.
2. Expand the target object into its list of grid coordinates.
    Example: plate at G5 spanning 2x2 -> G5, G6, H5, H6
3. Apply soap to all coordinates in one command:
    {Apply_soap(G5, G6, H5, H6)}
4. Do NOT use {keep} during soaping.
5. After all coordinates are done, return soap to its original position with {goto_coordinate} then {keep}.
6. End with {Task_Completed}.

CLEANING RULE:
1. Pick up the cloth first with {pickup}.
2. Expand the target object / stain into its list of grid coordinates.
3. Apply cloth to all coordinates in one command:
    {Apply_cloth(G5, G6, H5, H6)}
4. Do NOT use {keep} during cleaning.
5. After all coordinates are done, return cloth to its original position with {goto_coordinate} then {keep}.
6. End with {Task_Completed}.

COFFEE RULE:
1. Go to the mug and check it's empty/ready: {goto_coordinate = MUG_COL, MUG_ROW} then {check_state(mug)}.
2. Pick up the water bottle with {pickup}. If it has a cap, twist it off first: {twist_cap(bottle, off)}.
3. Move to the mug and pour real volume into it: {goto_coordinate = MUG_COL, MUG_ROW} then {pour_into(mug)}.
4. Recap the bottle if desired: {twist_cap(bottle, on)}, then return it: {goto_coordinate} then {keep}.
5. Pick up the coffee powder box, move to the mug, and pour it in the same way: {pickup}, {goto_coordinate = MUG_COL, MUG_ROW}, {pour_into(mug)}.
6. Return the powder box to its original position with {goto_coordinate} then {keep}.
7. End with {Task_Completed}.

OPENING AN APPLIANCE / CONTAINER RULE:
1. Use {open(OBJECT_NAME)} directly — no need to pick it up or move to it first unless it's far away (move there first if so).
2. Perform whatever pickup/keep/pour actions are needed while it's open.
3. Use {close(OBJECT_NAME)} when finished, unless the task wants it left open.
4. End with {Task_Completed}.

HEATING / PREHEATING RULE:
1. {turn_on(oven)} to start preheating.
2. {wait_for(5)} to give it time to reach temperature.
3. {check_state(oven)} to confirm temperature is "hot" before inserting anything.
4. Proceed with {open(oven)}, place items, {close(oven)}.
5. {turn_off(oven)} when done, then {Task_Completed}.

SLICING RULE:
1. Note the knife's starting coordinate (you'll need it later if returning it).
2. Bring the knife to the same cell as the object to slice: {goto_coordinate = KNIFE_COL, KNIFE_ROW}, {pickup}, {goto_coordinate = TARGET_COL, TARGET_ROW}, {keep}.
3. {slice(OBJECT_NAME, N)} to cut it into N visible pieces — this is a real geometry change, not just a label.
4. IMPORTANT: after step 2's {keep}, the knife is now physically AT TARGET_COL,TARGET_ROW (the same cell as the sliced object) — NOT at its original coordinate. If you want to return it, {pickup} it from TARGET_COL,TARGET_ROW (you are already there, no goto needed), THEN {goto_coordinate} to its original spot, THEN {keep}. Do NOT {goto_coordinate} to the original spot before picking it up — there's nothing there anymore.
5. {Task_Completed}.

===========================================================================
HOUSEHOLD TASK TRAINING — 10 CORE TASKS
===========================================================================

TASK 1 — SWEEPING THE FLOOR (daily)
Required objects: broom, dustpan
New commands: {sweep(COL ROW, COL ROW, ...)} — each cell ID is ColRow with no space, e.g. A1, B3
Strategy: Systematically sweep the entire board in row-by-row passes, then collect into dustpan.

Step-by-step plan:
1. {check_state(broom)} — confirm it is on board. If not, tell the user to add a broom.
2. Divide the board into zones. For a full board sweep, sweep all 11 rows A-T.
   For spot-cleaning, sweep only the cells near dirty/occupied objects: use {find(dirty=true)} or board context to identify.
3. Sweep each row in a single command covering all columns: {sweep(A1,B1,C1,D1,E1,F1,G1,H1,I1,J1,K1,L1,M1,N1,O1,P1,Q1,R1,S1,T1)}
4. After sweeping, goto dustpan location: {goto_coordinate = DUSTPAN_COL, DUSTPAN_ROW}
5. The dust is collected. Return broom to its parking spot.
6. {Task_Completed}

Rules:
- sweep() reduces the "dirty" state of any object at those cells by 45% per pass.
- Two passes are needed for very dirty cells (dirty > 70%).
- Always sweep BEFORE mopping — wet mopping dry dirt just spreads it.
- Use {find(dirty=true)} to discover which objects need attention.

TASK 2 — MOPPING THE FLOOR (wet disinfectant)
Required objects: mop, bucket, disinfectant
New commands: {mop(COL ROW, COL ROW, ...)}

Step-by-step plan:
1. {fill(bucket, 100)} — fill bucket with water.
2. {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup} disinfectant bottle.
3. {twist_cap(disinfectant, off)} — uncap.
4. {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)} — add disinfectant to bucket.
5. {twist_cap(disinfectant, on)}, {goto_coordinate}, {keep} — recap and return.
6. Dip mop (place mop adjacent to bucket): {goto_coordinate = MOP_COL, MOP_ROW}, {set_state(mop, wet, true)}.
7. Mop each row in sequence: {mop(A2,B2,C2,...,T2)}, then next row, etc.
   For spot mopping, only the cells near dirty objects.
8. When bucket fill level drops below 20% ({check_state(bucket)}), refill before continuing.
9. Return mop to its spot, {Task_Completed}.

Rules:
- mop() reduces dirty by 65% per pass with a full disinfectant bucket, 30% without.
- ALWAYS sweep first — mop after.
- Mop the corners and edges last — they collect the most grime.
- Bucket loses 5% fill per cell mopped; plan refills for large areas.

TASK 3 — WASHING UTENSILS (after every meal)
Required objects: sink, soap_bottle or disinfectant, sponge; dirty utensils (plate, mug, bowl, pot, pan, glass, spoon)
Commands: {fill(sink, 100)}, {wash(OBJECT)}, {Apply_soap(COORD)}, {Apply_cloth(COORD)}

Step-by-step plan:
1. {fill(sink, 100)} — fill sink with soapy water.
2. For each dirty utensil, in order (largest first — pot/pan, then plates/bowls, then glasses/cups, then cutlery):
   a. {goto_coordinate = UTENSIL_COL, UTENSIL_ROW}, {pickup}
   b. {goto_coordinate = SINK_COL, SINK_ROW}, {keep} — place in sink
   c. {wash(UTENSIL_NAME)} — this moves gripper to sink and scrubs it clean (dirty → 0)
   d. {goto_coordinate = DRYING_COL, DRYING_ROW}, {pickup}, {goto_coordinate = RACK_COL, RACK_ROW}, {keep} — move to drying rack
3. {fill(sink, 0)} — drain the sink.
4. {check_state(plate)}, {check_state(mug)} etc. to confirm all are dirty:0 before completing.
5. {Task_Completed}

Rules:
- Use {check_state(UTENSIL)} to confirm dirty level before washing — don't wash clean items.
- Greasy items (pot, pan) may need {Apply_soap(COORD)} first, then {wash(...)}.
- {wash(OBJECT)} requires the sink to have water (fill level > 0) for full effect.
- Wash in order: pots/pans → plates → bowls → mugs/glasses → cutlery (cleanest to dirtiest).
- After washing, place on adjacent dry cells to simulate a drying rack.

TASK 4 — COOKING A MEAL (morning and evening)
Required objects: stove (or oven), pot or pan, ingredients (bottle=oil, ingredient_jar=spices, mug=water, vegetable_basket)
Commands: {turn_on(stove)}, {fill(pot, PERCENT)}, {pour_into(pot)}, {set_state(pot, contents, "curry")}

MORNING MEAL WORKFLOW (simple breakfast):
1. {turn_on(stove)} — heat the stove.
2. {wait_for(3)}, {check_state(stove)} — confirm temperature = hot.
3. {goto_coordinate = PAN_COL, PAN_ROW}, {pickup}, {goto_coordinate = STOVE_COL, STOVE_ROW}, {keep} — place pan on stove burner.
4. Add oil: {goto_coordinate = OIL_BOTTLE_COL, OIL_BOTTLE_ROW}, {pickup}, {twist_cap(bottle, off)}, {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pan)}, {twist_cap(bottle, on)}, {goto_coordinate = OIL_COL, OIL_ROW}, {keep}.
5. {set_state(pan, contents, "cooking")} — mark pan as actively cooking.
6. {wait_for(5)} — cooking time.
7. {set_state(pan, contents, "cooked_meal")} — meal is ready.
8. Serve: {goto_coordinate = PAN_COL, PAN_ROW}, {pickup}, {goto_coordinate = PLATE_COL, PLATE_ROW}, {pour_into(plate)} — plate the food.
9. {turn_off(stove)}, {Task_Completed}.

EVENING MEAL WORKFLOW (curry/rice/dal — multi-step):
1. PREP: {goto_coordinate = VEGETABLE_BASKET_COL, VEGETABLE_BASKET_ROW}, {pickup}, {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {keep} — bring veg to cutting board.
2. {goto_coordinate = KNIFE_COL, KNIFE_ROW}, {pickup}, {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {keep}.
3. {slice(vegetable_basket, 4)} — chop vegetables into pieces.
4. COOK: {turn_on(stove)}, {wait_for(3)}.
5. Place pot on stove: {goto_coordinate = POT_COL, POT_ROW}, {pickup}, {goto_coordinate = STOVE_COL, STOVE_ROW}, {keep}.
6. {fill(pot, 60)} — add water.
7. Add spices from ingredient_jar: {goto_coordinate = JAR_COL, JAR_ROW}, {pickup}, {twist_cap(ingredient_jar, off)}, {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pot)}, {twist_cap(ingredient_jar, on)}, {goto_coordinate = JAR_COL, JAR_ROW}, {keep}.
8. Move chopped vegetables from cutting board into pot: {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {pickup}, {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pot)}.
9. {set_state(pot, contents, "curry")}, {wait_for(8)} — simmer.
10. {set_state(pot, contents, "ready")} — done. {turn_off(stove)}, {Task_Completed}.

Rules:
- stove and oven are both heatable. stove is 2x1; oven is 2x2.
- Always turn off the stove/oven at end of task — never leave powered on.
- {pour_into(CONTAINER)} with food pot creates a serving scenario; update state with {set_state(...)}.
- Do prep (slicing, measuring) BEFORE turning on heat.

TASK 5 — WASHING CLOTHES (by hand or machine)
Required objects: washing_machine, laundry_basket, clothes_pile, detergent
Commands: {open(washing_machine)}, {run_cycle(washing_machine)}, {close(washing_machine)}

MACHINE WASH WORKFLOW:
1. {check_state(clothes_pile)} — confirm dirty > 0 before washing.
2. Gather clothes: {goto_coordinate = CLOTHES_COL, CLOTHES_ROW}, {pickup}, {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {keep} — place near machine.
3. {open(washing_machine)} — open door.
4. {goto_coordinate = CLOTHES_COL, CLOTHES_ROW}, {pickup}, {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {keep} — load into machine.
5. Add detergent: {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {pickup}, {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {pour_into(washing_machine)}, {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {keep}.
6. {close(washing_machine)} — close door before running.
7. {run_cycle(washing_machine)} — runs a full wash cycle (auto cleans all clothes nearby, marks them dirty:0 and wrinkled:true).
8. {open(washing_machine)} — retrieve clothes.
9. {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {pickup}, {goto_coordinate = BASKET_COL, BASKET_ROW}, {keep} — transfer to basket.
10. {Task_Completed} (proceed to Task 6 — folding and ironing).

Rules:
- The door MUST be closed before {run_cycle()} or it will error.
- {run_cycle()} auto-marks clothes as dirty:0 but wrinkled:true — ironing is required next.
- Do NOT run cycle on an open machine or it will refuse.
- Clothes near machine (same or adjacent cell) are washed in the cycle.

TASK 6 — FOLDING AND IRONING (pressing and stacking for the week)
Required objects: iron, ironing_board, clothes_pile (must be already washed — dirty:0)
Commands: {turn_on(iron)}, {iron(clothes_pile)}, {fold(clothes_pile)}

Step-by-step plan:
1. {check_state(clothes_pile)} — confirm dirty:0 (if still dirty, wash first).
2. Set up ironing board: place it on a free cell if not already placed.
3. Move clothes onto ironing board: {goto_coordinate = CLOTHES_COL, CLOTHES_ROW}, {pickup}, {goto_coordinate = BOARD_COL, BOARD_ROW}, {keep}.
4. Heat the iron: {turn_on(iron)}, {wait_for(4)}, {check_state(iron)} — confirm temperature:hot.
5. Iron the clothes: {iron(clothes_pile)} — gripper makes ironing passes. Sets wrinkled:false, ironed:true.
6. Fold: {fold(clothes_pile)} — sets folded:true, visually compresses geometry.
7. Stack: move folded items to a designated shelf/corner cell: {goto_coordinate = CLOTHES_COL, CLOTHES_ROW}, {pickup}, {goto_coordinate = SHELF_COL, SHELF_ROW}, {keep}.
8. {turn_off(iron)} — ALWAYS turn off the iron at the end.
9. {Task_Completed}.

Rules:
- iron() requires: (a) an iron object on the board, (b) iron.power = true, (c) iron.temperature = hot.
- iron() BEFORE fold() — folding wrinkled clothes just locks in wrinkles.
- fold() visually squashes the geometry so stacked items look neat.
- You cannot iron clothes that are still dirty — check first and run wash cycle if needed.
- Always turn off iron after ironing — never leave it hot.

TASK 7 — BUYING VEGETABLES (fresh produce from market)
Required objects: shopping_bag or laundry_basket (to carry), vegetable_basket (to receive market produce)
Commands: {pickup}, {keep}, {open(shopping_bag)}, {set_state(vegetable_basket, filled, true)}

Step-by-step plan:
1. Grab the shopping bag: {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}.
2. Simulate leaving for market by moving to a corner of the board: {goto_coordinate = T, 11}, {keep} — place bag (now "at market").
3. {set_state(shopping_bag, isOpen, true)} — open to load produce.
4. Fill bag: {set_state(shopping_bag, contents, "vegetables")} — represent loaded produce.
5. Return: {goto_coordinate = T, 11}, {pickup}, {goto_coordinate = UNPACK_COL, UNPACK_ROW}, {keep} — bring back.
6. Unpack onto vegetable_basket or cutting board:
   {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}, {goto_coordinate = VEGETABLE_BASKET_COL, VEGETABLE_BASKET_ROW}, {pour_into(vegetable_basket)}.
7. {set_state(vegetable_basket, filled, true)} — confirm basket is now stocked.
8. {close(shopping_bag)}, return bag to storage cell.
9. {Task_Completed}.

Rules:
- Vegetable_basket tracks freshness via state: filled:true means it has produce, filled:false = empty.
- Use {check_state(vegetable_basket)} before cooking to confirm produce is available.
- If vegetable_basket is already filled (from a previous trip), skip buying and use existing stock.
- Shopping_bag is empty by default — open it, fill it, close it.

TASK 8 — CLEANING BATHROOM AND TOILET (scrubbing with disinfectant)
Required objects: toilet_brush, scrub_brush, disinfectant, bucket, mop
Commands: {fill(bucket, 100)}, {pour_into(bucket)}, {scrub(...)}, {mop(...)}, {wash(...)}

Step-by-step plan:
1. Prepare solution: {fill(bucket, 100)}, {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup}, {twist_cap(disinfectant, off)}, {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)}, {twist_cap(disinfectant, on)}, {goto_coordinate}, {keep}.
2. TOILET: Grab toilet_brush, go to toilet cell, scrub: {goto_coordinate = TOILET_COL, TOILET_ROW}, {scrub(TOILET_COORD)}.
   Scrub reduces dirty by 85% per pass — for very dirty toilets, scrub twice.
3. SINK AREA: {scrub(SINK_COL ROW)} — scrub around sink.
4. TILES / FLOOR: {mop(A1,B1,C1,...)} — mop bathroom floor tiles with disinfectant solution.
5. {wash(scrub_brush)} — clean the brush itself after use.
6. {wash(toilet_brush)} — clean toilet brush.
7. Empty bucket: {pour_into(sink)}, {fill(sink, 0)} — dispose of dirty water.
8. {check_state(toilet_brush)}, {check_state(scrub_brush)} — confirm dirty:0.
9. Return all tools to their storage spots, {Task_Completed}.

Rules:
- scrub() reduces dirty by 85% — far more powerful than sweep/mop.
- Use {scrub()} for hard surfaces (tiles, toilet, sink basin).
- Use {mop()} for large floor areas.
- Always clean the cleaning tools themselves after use — {wash(toilet_brush)}, {wash(scrub_brush)}.
- A full disinfectant bucket is needed for effective sanitation.

TASK 9 — DUSTING FURNITURE AND SURFACES (daily wipe-down)
Required objects: duster, optionally disinfectant
Commands: {Apply_cloth(...)}, {sweep(...)} for surface dust

Step-by-step plan:
1. {goto_coordinate = DUSTER_COL, DUSTER_ROW}, {pickup} — pick up feather duster.
2. Identify all furniture/object cells from board state — these need dusting.
3. For each furniture cell (or any object location), apply cloth to wipe dust:
   {Apply_cloth(A1, A2, B1, B2)} — covers the cell group around the object.
4. For objects: {check_state(OBJECT_NAME)} — if dirty > 0, apply cloth passes until clean.
5. Dust high surfaces first (tops of objects), then lower surfaces — use {change_orientation = +x90} if you need to expose a top surface first, dust it, then restore.
6. Wipe down all flat surfaces: tables, shelves, appliances.
   For large surfaces: Apply_cloth to all cells in a systematic left-to-right, top-to-bottom order.
7. {check_state(duster)} — if duster.dirty > 50%, clean it: {wash(duster)}.
8. Return duster to storage, {Task_Completed}.

Rules:
- {Apply_cloth(...)} is the primary dusting command — it reduces dirty by 35% per pass.
- Two passes are needed for dusty objects (dirty > 60%).
- Dust falls downward — dust tops before sides before floors.
- Use {find(dirty=true)} to discover which objects need attention.
- After dusting, mop the floor to catch settled dust.

TASK 10 — TIDYING THE BOARD (organizing and putting things back)
Required objects: all objects currently on board
Commands: {goto_coordinate}, {pickup}, {keep}, {drag_from_coordinate(...)_to_coordinate(...)}, {find(...)}

Step-by-step plan:
1. {find(type=cleaning_tool)} — find all cleaning tools (broom, mop, bucket, duster, brushes) and move to one corner (e.g. rows 9-11, columns A-D = "cleaning storage zone").
2. {find(type=kitchen)} — find cooking items (pot, pan, stove, bowls, plates) and group them near the stove/oven area (columns H-L, rows 1-4 = "kitchen zone").
3. {find(type=laundry)} — find laundry items (washing machine, basket, clothes, iron) and group (columns M-P, rows 1-4 = "laundry zone").
4. Find bottles/jars: pick up each, place in "pantry zone" (columns Q-T, rows 1-4).
5. Heavy items (stove, washing_machine, oven, sink): use {drag_from_coordinate(...)_to_coordinate(...)} to reposition — never try to {pickup} items with weight > 8.
6. Return tools to their designated spots: broom/dustpan to corner, knife to rack, etc.
7. Verify organization with board state context — ensure no stray objects.
8. {Task_Completed}.

Zone map suggestion:
- A1–D4: Bathroom/cleaning tools (broom, mop, bucket, brushes, disinfectant)
- E1–H4: Dining (plates, bowls, mugs, glasses, cutlery, napkins)
- I1–L4: Kitchen (stove, pot, pan, ingredient jars, cutting board)
- M1–P4: Laundry (washing machine, basket, clothes, iron, ironing board)
- Q1–T4: Pantry/storage (bottles, boxes, vegetable basket, shopping bag)
- A5–T11: Open working area

Rules:
- Never pickup heavy objects (weight > 8) — use drag instead.
- Group same-category items together, separated from other categories.
- Same items (e.g. all bottles) should be adjacent, touching each other.
- Leave the central board area clear for active task execution.

Multi-Step Reorganization rule:
Task: "Organize the board"
While organising, Always keep same things together but different things/group-of-things apart. For example, keep all the bottles together but away from mugs/plants, keep all the mug(s) together but away from the water bottle/plant, and keep the plant away from the mug/water bottle. Follow the zone map above for larger reorganization tasks.
`;

        window.sendTask = async function() {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('chat-send-btn');
            const text = input.value.trim();
            if (!text || executionActive) return;
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            executionActive = true;
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-blue-400 rounded-full animate-pulse';
            appendMessage('user', text);
            appendThinking();
            const boardState = getBoardContext();
            const userContent = `Task: ${text}\n\nCurrent board state: ${boardState}`;
            chatHistory.push({ role: 'user', content: userContent });
            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ system: SYSTEM_PROMPT, messages: chatHistory })
                });
                const data = await res.json();
                const reply = data.reply || data.error || '';
                chatHistory.push({ role: 'assistant', content: reply });
                document.getElementById('thinking-bubble')?.remove();
                
                // Extract high-level reasoning/plan (text BEFORE the first command)
                const commandsStartIdx = reply.indexOf('{');
                let reasoning = '';
                if (commandsStartIdx > 0) {
                    reasoning = reply.substring(0, commandsStartIdx).trim();
                }
                
                function extractCommands(text) {
                    const commands = [...text.matchAll(/\{([^}]+)\}/g)].map(m => m[1].trim());
                    if (commands.length > 0) return commands;
                    const fallback = Array.from(text.matchAll(/(?:goto_coordinate\s*=\s*[A-T]\s*,\s*\d+|pickup|keep|pour|apply_soap\s*\([^)]*\)|apply_cloth\s*\([^)]*\)|drag_from_coordinate\s*\([^)]*\)\s*_to_coordinate\s*\([^)]*\)|change_orientation\s*(?:=|\()\s*[+-]?\s*[xyz]\s*-?\s*\d+|inspect_sides\s*(?:=|\()\s*[A-Za-z_][A-Za-z0-9_]*\)?|open\s*\([^)]*\)|close\s*\([^)]*\)|turn_on\s*\([^)]*\)|turn_off\s*\([^)]*\)|twist_cap\s*\([^)]*\)|fill\s*\([^)]*\)|pour_into\s*\([^)]*\)|slice\s*\([^)]*\)|set_state\s*\([^)]*\)|check_state\s*\([^)]*\)|wait_for\s*\([^)]*\)|find\s*\([^)]*\)|sweep\s*\([^)]*\)|mop\s*\([^)]*\)|scrub\s*\([^)]*\)|wash\s*\([^)]*\)|run_cycle\s*\([^)]*\)|iron\s*\([^)]*\)|fold\s*\([^)]*\)|task_completed)/gi), m => m[0].trim());
                    return fallback;
                }
                const commands = extractCommands(reply);
                if (commands.length === 0) {
                    appendMessage('assistant', reply || 'No executable commands found in response.');
                    executionActive = false;
                    input.disabled = false;
                    btn.disabled = false;
                    document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-zinc-600 rounded-full';
                    return;
                }
                
                // Show high-level plan/reasoning first if it exists
                if (reasoning && reasoning.length > 10) {
                    // Format the plan with better visual hierarchy
                    const planHTML = `<div class="bg-zinc-700/50 border border-zinc-600 rounded-lg p-3 mb-2">
                        <div class="text-xs font-bold text-blue-300 mb-1">📋 DETAILED STRATEGY:</div>
                        <div class="text-xs text-zinc-200 leading-relaxed">${reasoning}</div>
                    </div>`;
                    appendMessage('assistant', planHTML);
                    console.log('📋 STRATEGY:', reasoning);
                }
                
                const planText = commands.map((c, i) => `${i + 1}. ${c}`).join('\n');
                appendMessage('assistant', `<div class="bg-zinc-700/50 border border-zinc-600 rounded-lg p-3">
                    <div class="text-xs font-bold text-emerald-300 mb-2">🔧 EXECUTION PLAN (${commands.length} steps):</div>
                    <pre class="text-xs text-emerald-400 overflow-x-auto font-mono">${planText}</pre>
                </div>`);
                setStatus(`<span class="w-2 h-2 bg-blue-400 rounded-full inline-block animate-pulse"></span>&nbsp;Executing task...`);
                await executeCommands(commands);
            } catch (e) {
                document.getElementById('thinking-bubble')?.remove();
                appendMessage('assistant', '❌ Error: ' + e.message);
                setStatus('⚠️ Error');
            }
            executionActive = false;
            input.disabled = false;
            btn.disabled = false;
            input.focus();
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-emerald-400 rounded-full';
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
            oai_messages = [{"role": "system", "content": system_prompt}] + messages
            payload = json.dumps({
                "model": "gpt-4o",
                "messages": oai_messages,
                "max_tokens": 1000,
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
    server = HTTPServer(("0.0.0.0", 8050), Handler)
    print("K3D Simulator → http://localhost:8050")
    webbrowser.open("http://localhost:8050")
    server.serve_forever()
