import pygame
import threading
from bytez import Bytez

# --- Configuration ---
BYTEZ_KEY = "YOUR BYTEZ API, if you don't have one, get it from: www.bytez.com"
client = Bytez(BYTEZ_KEY)
model = client.model("Qwen/Qwen2.5-7B-Instruct")

# --- Pygame Setup ---
pygame.init()
WIDTH, HEIGHT = 800, 400
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Prolabs Robotics - AI Home Navigator")
font = pygame.font.SysFont("Consolas", 18)

# Colors
BLUE = (30, 144, 255)
BLACK = (20, 20, 20)
WOOD_BROWN = (101, 67, 33)
RED = (255, 50, 50)
WHITE = (255, 255, 255)

# --- Global State ---
player_x = 400.0
target_x = 400.0
user_input = ""
status_msg = "Awaiting command..."

# Local synonym dictionary for robust fallback
SYNONYMS = {
    "kitchen": ["food", "cook", "hungry", "eat", "chef"],
    "living_room": ["tv", "sofa", "relax", "living", "couch"],
    "bathroom": ["shower", "wash", "toilet", "bath"],
    "bedroom": ["sleep", "bed", "tired", "nap"]
}


def get_coordinates(location_name):
    mapping = {
        "kitchen": 100,
        "bathroom": 400,
        "bedroom": 400,
        "living_room": 700
    }
    return mapping.get(location_name, 400)


def call_bytez_ai(query):
    global target_x, status_msg
    query_clean = query.lower().strip()
    print(f"\n[PROLABS DEBUG] User Query: {query_clean}")

    prompt = f"Map the query to one room: kitchen, bathroom, bedroom, living_room. Query: {query_clean}. Answer with ONLY the room name."

    decision = None
    try:
        print("[PROLABS DEBUG] Calling Bytez API...")
        result = model.run(prompt)
        if result and (output_text := getattr(result, 'output', None)):
            decision = output_text.strip().lower()
            print(f"[PROLABS DEBUG] AI Decision: {decision}")
    except Exception as e:
        print(f"[ERROR] API Call failed: {e}")

    # --- Robust Extraction & Fallback ---
    found = False
    rooms = ["kitchen", "living_room", "bathroom", "bedroom"]

    # 1. Check AI decision first
    if decision:
        for r in rooms:
            if r.replace("_", " ") in decision or r in decision:
                target_x = get_coordinates(r)
                status_msg = f"AI: Moving to {r.replace('_', ' ').title()}"
                found = True
                break

    # 2. If AI failed, use local Keyword + Synonym Fallback
    if not found:
        print("[PROLABS DEBUG] AI failed/None. Checking synonyms...")
        for room_key, words in SYNONYMS.items():
            if any(word in query_clean for word in words) or room_key.replace("_", " ") in query_clean:
                target_x = get_coordinates(room_key)
                status_msg = f"Fallback: Moving to {room_key.replace('_', ' ').title()}"
                found = True
                break

    if found:
        print(f"[SUCCESS] Target set to x={target_x}")
    else:
        status_msg = "AI: Destination unknown."
        print("[FAILED] No match found in AI or Fallback.")


# --- Main Game Loop ---
running = True
clock = pygame.time.Clock()
print("[SYSTEM] Cuda.py active. Using Python 3.13.2")

while running:
    screen.fill(BLUE)

    # 1. Draw Wooden Line
    pygame.draw.rect(screen, WOOD_BROWN, (45, 193, 710, 14))
    pygame.draw.rect(screen, BLACK, (50, 197, 700, 6))

    # 2. Draw Stops
    stops = [(100, "Kitchen"), (400, "Bed/Bath"), (700, "Living Room")]
    for sx, name in stops:
        pygame.draw.circle(screen, BLACK, (sx, 200), 10)
        is_here = abs(player_x - sx) < 15
        color = (255, 255, 0) if is_here else WHITE
        lbl = font.render(name, True, color)
        screen.blit(lbl, (sx - lbl.get_width() // 2, 225))

    # 3. Input Handling
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if user_input.strip():
                    status_msg = "AI: Thinking..."
                    threading.Thread(target=call_bytez_ai, args=(user_input,), daemon=True).start()
                    user_input = ""
            elif event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_BACKSPACE:
                user_input = user_input[:-1]
            else:
                user_input += event.unicode

    # 4. Manual Arrow Controls
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT] and player_x > 55:
        player_x -= 5
        target_x = player_x
    if keys[pygame.K_RIGHT] and player_x < 745:
        player_x += 5
        target_x = player_x

    # 5. Smooth Movement
    if abs(player_x - target_x) > 1:
        player_x += (target_x - player_x) * 0.1

    # 6. Draw Player
    pygame.draw.circle(screen, WHITE, (int(player_x), 200), 12)
    pygame.draw.circle(screen, RED, (int(player_x), 200), 9)

    # 7. UI
    pygame.draw.rect(screen, WHITE, (50, 330, 700, 40), border_radius=8)
    txt_surf = font.render(user_input + "|", True, BLACK)
    screen.blit(txt_surf, (65, 340))
    status_surf = font.render(status_msg, True, WHITE)
    screen.blit(status_surf, (50, 40))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
