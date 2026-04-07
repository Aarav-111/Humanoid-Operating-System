from http.server import HTTPServer, BaseHTTPRequestHandler

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha Sim HOS</title>
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
    </style>
</head>
<body class="bg-zinc-950 text-zinc-200 overflow-hidden">

    <div class="ui-overlay top-0 left-0 right-0 bg-black/90 backdrop-blur border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center gap-x-3">
            <div class="w-9 h-9 bg-blue-500 rounded-xl flex items-center justify-center text-white font-bold text-xl">G</div>
            <div>
                <h1 class="text-xl font-bold tracking-tight">Precision Cartesian Gantry</h1>
                <p class="text-xs text-zinc-400 mono">Prolabs V12.2 · LLM-Controlled · XYZ-Axis</p>
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

    <!-- Right Side: Single unified panel top-to-bottom -->
    <div class="ui-overlay top-20 right-6 bottom-6 w-80 flex flex-col gap-0" style="">

        <!-- Object Positions -->
        <div class="bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl p-4 mb-3 shrink-0" style="max-height: 38vh; overflow-y: auto;">
            <h2 class="text-xs font-bold mb-3 text-zinc-300 tracking-widest uppercase">Object Positions</h2>
            <div id="objects-list" class="space-y-2">
                <div class="text-xs text-zinc-500 italic">No objects on board</div>
            </div>
        </div>

        <!-- AI Chatbot — fills remaining space -->
        <div class="bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl flex flex-col flex-1 min-h-0">
            <div class="flex items-center gap-2 px-4 pt-3 pb-3 border-b border-zinc-700/60 shrink-0">
                <div class="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">AI</div>
                <div>
                    <div class="text-xs font-bold text-zinc-200 tracking-widest uppercase">Gantry Assistant</div>
                    <div class="text-xs text-zinc-500 mono">Prolabs V12.2 · Claude</div>
                </div>
                <div id="ai-status-dot" class="ml-auto w-2 h-2 bg-zinc-600 rounded-full"></div>
            </div>
            <div id="chat-messages" class="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
                <div class="flex gap-2">
                    <div class="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">AI</div>
                    <div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-300 leading-relaxed">Hi! I know the full board state. Try: <span class="text-blue-400">"Move to F5"</span>, <span class="text-blue-400">"What\'s on the board?"</span>, or <span class="text-blue-400">"Pick up the bottle"</span>.</div>
                </div>
            </div>
            <div class="px-3 pb-3 pt-2 border-t border-zinc-800 shrink-0">
                <div class="flex gap-2">
                    <input id="chat-input" type="text" placeholder="Ask the gantry AI..."
                        class="flex-1 bg-zinc-800 border border-zinc-700 focus:border-blue-500 rounded-xl px-3 py-2 text-xs text-zinc-200 outline-none mono placeholder-zinc-600"
                        onkeydown="if(event.key==='Enter')sendChat()">
                    <button onclick="sendChat()" id="chat-send-btn" class="bg-blue-600 hover:bg-blue-500 transition-colors rounded-xl px-3 py-2 text-white text-xs font-bold">→</button>
                </div>
            </div>
        </div>

    </div>

    <div class="ui-overlay bottom-6 left-6 bg-zinc-900/95 backdrop-blur border border-zinc-700/60 rounded-2xl p-5 w-80" style="max-height: 48vh; overflow-y: auto;">
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
        <div class="lib-section-title">Custom Image Object</div>
        <label class="flex items-center gap-3 bg-zinc-800 hover:bg-zinc-700 transition-colors rounded-xl px-4 py-3 cursor-pointer border border-zinc-700 border-dashed">
            <span class="text-2xl">🖼️</span>
            <div>
                <div class="text-xs font-bold text-zinc-300">Upload Image</div>
                <div class="text-xs text-zinc-500 mono">PNG / JPG / WEBP</div>
            </div>
            <input type="file" id="img-upload" accept="image/*" class="hidden" onchange="handleImageUpload(event)">
        </label>
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
        let isAnimating = false;
        let selectedObject = null;
        let objects = [];
        const objectTypes = new Map();
        const objectNames = new Map();
        const objectSprites = new Map();

        const RAIL_TOP_Y = 8.5, RAIL_LENGTH = 8.0;

        let ctxTarget = null;

        function setStatus(html) { document.getElementById('status').innerHTML = html; }
        function setGripperState(s) { document.getElementById('gripper-state').textContent = 'Gripper: ' + s; }

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
            const darkMat   = new THREE.MeshPhongMaterial({ color: 0x1a1f2e });
            const midMat    = new THREE.MeshPhongMaterial({ color: 0x2d3748 });
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
            gripperLeftJaw  = makeJaw(-1);
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
            if (gripperLeftJaw)  gripperLeftJaw.position.x  = -spread;
            if (gripperRightJaw) gripperRightJaw.position.x =  spread;
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
            const railMat     = new THREE.MeshPhongMaterial({ color: 0x374151 });
            const carriageMat = new THREE.MeshPhongMaterial({ color: 0x1e3a5f });
            const accentMat   = new THREE.MeshPhongMaterial({ color: 0x2563eb });
            const silverMat   = new THREE.MeshPhongMaterial({ color: 0x94a3b8 });
            const darkMat     = new THREE.MeshPhongMaterial({ color: 0x111827 });
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
                menu.style.left = left + 'px';
                menu.style.top  = top + 'px';
            }
        }

        function hideContextMenu() {
            document.getElementById('context-menu').style.display = 'none';
        }

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
            const sprite = objectSprites.get(ctxTarget);
            if (sprite) scene.remove(sprite);
            objectSprites.delete(ctxTarget);
            scene.remove(ctxTarget);
            objects = objects.filter(o => o !== ctxTarget);
            objectTypes.delete(ctxTarget);
            objectNames.delete(ctxTarget);
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

        window.closeRenameModal = function() {
            document.getElementById('rename-modal').classList.remove('active');
        };

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
                    selectedObject.position.y = selectedObject.userData.flatImage ? 0 : 0.5;
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
            const cx = Math.round(currentX) + 0.5, cy = Math.round(currentY) + 0.5;
            for (const obj of objects) {
                if (Math.abs(obj.position.x - cx) < 0.9 && Math.abs(obj.position.z - cy) < 0.9) return obj;
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
            const baseY = obj.userData.flatImage ? 0 : 0.5;
            obj.position.set(rx, baseY, ry);
            scene.add(obj);
            objects.push(obj);
            objectTypes.set(obj, type);
            const sprite = createNameLabel(type);
            sprite.position.set(rx, 2.7, ry);
            scene.add(sprite);
            objectSprites.set(obj, sprite);
            updateObjectPositionsDisplay();
        }

        window.addObject = function(type) {
            let obj;
            if (type === 'bottle')     obj = createWaterBottle();
            else if (type === 'box')   obj = createGreyBox();
            else if (type === 'mug')   obj = createCoffeeMug();
            else if (type === 'book')  obj = createBook();
            else if (type === 'plant') obj = createPottedPlant();
            else if (type === 'wooden_box')  obj = createWoodenBox();
            else if (type === 'water_cup')   obj = createWaterCup();
            else if (type === 'powder_box')  obj = createPowderBox();
            else if (type === 'plate')       obj = createPlate();
            else if (type === 'glass')       obj = createGlass();
            if (obj) { spawnObject(obj, type); setStatus(`✅ Added ${type}`); }
        };

        window.handleImageUpload = function(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 256; canvas.height = 256;
                    const ctx = canvas.getContext('2d');
                    const aspect = img.width / img.height;
                    let sw = 256, sh = 256;
                    if (aspect > 1) sh = 256 / aspect; else sw = 256 * aspect;
                    ctx.drawImage(img, (256 - sw) / 2, (256 - sh) / 2, sw, sh);
                    const texture = new THREE.CanvasTexture(canvas);
                    const mat = new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide });
                    const geo = new THREE.PlaneGeometry(1.8, 1.8);
                    const mesh = new THREE.Mesh(geo, mat);
                    mesh.rotation.x = -Math.PI / 2;
                    mesh.position.y = 0.06;
                    const border = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.06, 1.9), new THREE.MeshPhongMaterial({ color: 0x1e40af }));
                    border.position.y = 0.0;
                    const group = new THREE.Group();
                    group.add(border);
                    group.add(mesh);
                    const typeName = file.name.replace(/\.[^/.]+$/, '').substring(0, 18);
                    group.userData.flatImage = true;
                    spawnObject(group, typeName);
                    setStatus(`🖼️ Added image: ${typeName}`);
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
            event.target.value = '';
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
                else colorClass = 'text-purple-400';
                html += `<div class="bg-zinc-800/50 border border-zinc-700/40 rounded-lg p-3 flex items-center justify-between hover:bg-zinc-800 transition-colors">
                    <div>
                        <div class="text-sm font-bold ${colorClass}">${displayName}</div>
                        <div class="text-xs text-zinc-500 mono">ID: ${idx} · ${type}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-bold text-blue-400 mono">${coord}</div>
                        <div class="text-xs text-zinc-500 mono">(${obj.position.x.toFixed(1)}, ${obj.position.z.toFixed(1)})</div>
                    </div>
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
                -(cx + PAD), cx + PAD,
                cz + PAD, -(cz + PAD),
                0.1, 300
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
            canvas2d.width = TOTAL_W;
            canvas2d.height = TOTAL_H;
            const ctx = canvas2d.getContext('2d');

            ctx.fillStyle = '#09090b';
            ctx.fillRect(0, 0, TOTAL_W, TOTAL_H);

            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, 0, 0, GRID_PX_W, GRID_PX_H);

                const px = GRID_PX_W, pw = PANEL_W;
                ctx.fillStyle = '#18181b';
                ctx.fillRect(px, 0, pw, GRID_PX_H);
                ctx.strokeStyle = '#3f3f46';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, GRID_PX_H); ctx.stroke();

                ctx.fillStyle = '#ffffff';
                ctx.font = 'bold 13px monospace';
                ctx.letterSpacing = '0.1em';
                ctx.fillText('OBJECT POSITIONS', px + 20, 36);

                ctx.strokeStyle = '#27272a';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(px + 12, 48); ctx.lineTo(px + pw - 12, 48); ctx.stroke();

                const colorMap = {
                    bottle: '#60a5fa', box: '#fbbf24', mug: '#fcd34d', book: '#818cf8',
                    plant: '#4ade80', wooden_box: '#ea580c', wooden: '#ea580c',
                    water_cup: '#22d3ee', powder_box: '#ca8a04', powder: '#ca8a04',
                    plate: '#d4d4d8', glass: '#67e8f9'
                };
                function objColor(type) {
                    for (const k of Object.keys(colorMap)) { if (type.includes(k)) return colorMap[k]; }
                    return '#c084fc';
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

                    ctx.fillStyle = col;
                    ctx.font = 'bold 24px monospace';
                    ctx.textAlign = 'right';
                    ctx.fillText(coord, px + pw - 20, rowY + 26);
                    ctx.textAlign = 'left';

                    ctx.fillStyle = '#71717a';
                    ctx.font = '11px monospace';
                    ctx.fillText('ID: ' + idx + ' · ' + type.substring(0, 14), px + 20, rowY + 44);

                    ctx.fillStyle = '#52525b';
                    ctx.font = '11px monospace';
                    ctx.textAlign = 'right';
                    ctx.fillText('(' + obj.position.x.toFixed(1) + ', ' + obj.position.z.toFixed(1) + ')', px + pw - 20, rowY + 44);
                    ctx.textAlign = 'left';

                    rowY += 80;
                });

                if (objects.length === 0) {
                    ctx.fillStyle = '#52525b';
                    ctx.font = 'italic 13px monospace';
                    ctx.fillText('No objects on board', px + 20, 80);
                }

                ctx.fillStyle = '#09090b';
                ctx.fillRect(0, GRID_PX_H, TOTAL_W, FOOTER_H);
                ctx.strokeStyle = '#27272a';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(0, GRID_PX_H); ctx.lineTo(TOTAL_W, GRID_PX_H); ctx.stroke();

                ctx.fillStyle = '#93c5fd';
                ctx.font = 'bold 16px monospace';
                ctx.fillText('Prolabs V12.2  ·  Top-Down View  ·  ' + new Date().toLocaleString(), 16, GRID_PX_H + 32);

                ctx.fillStyle = '#52525b';
                ctx.font = '12px monospace';
                let summary = objects.map(o => {
                    const n = objectNames.get(o) || objectTypes.get(o) || '?';
                    const x = Math.floor(o.position.x), z = Math.floor(o.position.z);
                    return n + '@' + String.fromCharCode(65 + x) + (z + 1);
                }).join('   ');
                ctx.fillText((summary || 'No objects on board').substring(0, 180), 16, GRID_PX_H + 60);

                const a = document.createElement('a');
                a.href = canvas2d.toDataURL('image/png');
                a.download = 'prolabs_gantry_' + Date.now() + '.png';
                a.click();
                shotRenderer.dispose();
                setStatus('📸 Screenshot saved');
            };
            img.src = shotRenderer.domElement.toDataURL('image/png');
        };

        function roundRect(ctx, x, y, w, h, r) {
            ctx.beginPath();
            ctx.moveTo(x + r, y);
            ctx.lineTo(x + w - r, y);
            ctx.quadraticCurveTo(x + w, y, x + w, y + r);
            ctx.lineTo(x + w, y + h - r);
            ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
            ctx.lineTo(x + r, y + h);
            ctx.quadraticCurveTo(x, y + h, x, y + h - r);
            ctx.lineTo(x, y + r);
            ctx.quadraticCurveTo(x, y, x + r, y);
            ctx.closePath();
        }

        const chatHistory = [];

        function getBoardContext() {
            const objs = objects.map((o, i) => {
                const x = Math.floor(o.position.x), z = Math.floor(o.position.z);
                const name = objectNames.get(o) || objectTypes.get(o) || 'unknown';
                return name + ' at ' + String.fromCharCode(65 + x) + (z + 1);
            });
            return 'Gantry is at ' + String.fromCharCode(65 + Math.round(currentX)) + (Math.round(currentY) + 1) +
                ', Z=' + currentZ.toFixed(1) + '. Gripper: ' + (gripperOpen ? 'OPEN' : 'CLOSED') +
                '. Objects on board: ' + (objs.length ? objs.join(', ') : 'none') + '.';
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
                '<div class="bg-zinc-800 rounded-xl rounded-tl-sm px-3 py-2 text-xs text-zinc-500 italic">Thinking...</div>';
            box.appendChild(wrap);
            box.scrollTop = box.scrollHeight;
        }

        window.sendChat = async function() {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('chat-send-btn');
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-blue-400 rounded-full animate-pulse';

            appendMessage('user', text);
            appendThinking();

            chatHistory.push({ role: 'user', content: text });

            const systemPrompt = `You are an AI assistant for the Prolabs V12.2 Precision Cartesian Gantry robot. ` +
                `Current board state: ${getBoardContext()} ` +
                `The grid is 20 columns (A-T) by 11 rows (1-11). ` +
                `You can answer questions about object positions, explain what the gantry can do, and give movement instructions. ` +
                `Keep responses concise and technical. If the user asks to move the gripper, describe the move command clearly.`;

            try {
                const res = await fetch('https://api.anthropic.com/v1/messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: 'claude-sonnet-4-20250514',
                        max_tokens: 1000,
                        system: systemPrompt,
                        messages: chatHistory
                    })
                });
                const data = await res.json();
                const reply = data.content?.[0]?.text || 'No response.';
                chatHistory.push({ role: 'assistant', content: reply });
                document.getElementById('thinking-bubble')?.remove();
                appendMessage('assistant', reply);
            } catch (e) {
                document.getElementById('thinking-bubble')?.remove();
                appendMessage('assistant', 'Error: ' + e.message);
            }

            input.disabled = false;
            btn.disabled = false;
            input.focus();
            document.getElementById('ai-status-dot').className = 'ml-auto w-2 h-2 bg-emerald-400 rounded-full';
        };

        window.onload = function() { initThree(); animate(); };
    </script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("Prolabs V12.2 Simulator → http://localhost:8080")
    server.serve_forever()
