import pygame
import sys

# --- Initialization ---
pygame.init()

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("HOS Version 2: Fixed Target System")

# --- Colors ---
BG_COLOR = (220, 240, 255)
BLACK = (0, 0, 0)
RED = (235, 80, 80)
PURPLE = (130, 100, 255)
GREEN = (100, 200, 100)
ORANGE = (255, 140, 50)

font = pygame.font.SysFont("Arial", 22)

# --- Dimensions & Scaling ---
MAX_X_CM = 50
MAX_Y_CM = 25
STEP_CM = 5 

track_length_px = 800
pixels_per_cm = track_length_px / MAX_X_CM
max_y_px = MAX_Y_CM * pixels_per_cm

# Screen positions
rail_start_x = (SCREEN_WIDTH - track_length_px) // 2
rail_y = SCREEN_HEIGHT // 2 + 100 

# Initial positions
arm_x_cm = 10 
dot_y_cm = 0   

# Fixed Target Positions
target_x_cm = 45 # Fixed near the right (45cm mark)
target_y_cm = 20 # Fixed higher up (20cm mark)

clock = pygame.time.Clock()

# --- Helper Functions ---
def draw_dotted_line(surface, color, start_pos, end_pos, width=2, dash_length=6):
    x1, y1 = start_pos
    x2, y2 = end_pos
    if x1 == x2: # Vertical
        start, end = min(y1, y2), max(y1, y2)
        for y in range(int(start), int(end), dash_length * 2):
            pygame.draw.line(surface, color, (x1, y), (x1, min(y + dash_length, end)), width)
    elif y1 == y2: # Horizontal
        start, end = min(x1, x2), max(x1, x2)
        for x in range(int(start), int(end), dash_length * 2):
            pygame.draw.line(surface, color, (x, y1), (min(x + dash_length, end), y1), width)

def draw_arrow_ends(surface, color, start_pos, end_pos, direction="horizontal"):
    size = 8
    x1, y1 = start_pos
    x2, y2 = end_pos
    if direction == "horizontal":
        pygame.draw.polygon(surface, color, [(x1, y1), (x1 + size, y1 - size//2), (x1 + size, y1 + size//2)])
        pygame.draw.polygon(surface, color, [(x2, y2), (x2 - size, y2 - size//2), (x2 - size, y2 + size//2)])
    else:
        pygame.draw.polygon(surface, color, [(x1, y1), (x1 - size//2, y1 + size), (x1 + size//2, y1 + size)])
        pygame.draw.polygon(surface, color, [(x2, y2), (x2 - size//2, y2 - size), (x2 + size//2, y2 - size)])

# --- Main Loop ---
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RIGHT:
                arm_x_cm += STEP_CM
            elif event.key == pygame.K_LEFT:
                arm_x_cm -= STEP_CM
            elif event.key == pygame.K_UP:
                dot_y_cm += STEP_CM
            elif event.key == pygame.K_DOWN:
                dot_y_cm -= STEP_CM

    # Logic Constraints
    arm_x_cm = max(0, min(arm_x_cm, MAX_X_CM))
    dot_y_cm = max(0, min(dot_y_cm, MAX_Y_CM))

    screen.fill(BG_COLOR)

    # -- X-Axis Labeling --
    scale_y_pos = rail_y + 60
    draw_dotted_line(screen, BLACK, (rail_start_x, scale_y_pos), (rail_start_x + track_length_px, scale_y_pos))
    draw_arrow_ends(screen, BLACK, (rail_start_x, scale_y_pos), (rail_start_x + track_length_px, scale_y_pos), "horizontal")
    x_text = font.render(f"{MAX_X_CM} Cms (x)", True, BLACK)
    x_rect = x_text.get_rect(center=(SCREEN_WIDTH // 2, scale_y_pos + 25))
    screen.blit(x_text, x_rect)

    # -- Y-Axis Labeling --
    scale_x_pos = rail_start_x - 60
    rail_top_y = rail_y - int(max_y_px)
    draw_dotted_line(screen, BLACK, (scale_x_pos, rail_y), (scale_x_pos, rail_top_y))
    draw_arrow_ends(screen, BLACK, (scale_x_pos, rail_y), (scale_x_pos, rail_top_y), "vertical")
    y_text = font.render(f"{MAX_Y_CM} Cms (y)", True, BLACK)
    y_rect = y_text.get_rect(center=(scale_x_pos - 45, (rail_y + rail_top_y) // 2))
    screen.blit(y_text, y_rect)

    # -- Green Rail --
    pygame.draw.line(screen, GREEN, (rail_start_x, rail_y), (rail_start_x + track_length_px, rail_y), 3)
    pygame.draw.rect(screen, GREEN, (rail_start_x - 6, rail_y - 6, 12, 12))
    pygame.draw.rect(screen, GREEN, (rail_start_x + track_length_px - 6, rail_y - 6, 12, 12))

    # -- Orange Fixed Target Line --
    fixed_target_x_px = rail_start_x + (target_x_cm * pixels_per_cm)
    fixed_target_y_px = rail_y - (target_y_cm * pixels_per_cm)
    pygame.draw.line(screen, ORANGE, (fixed_target_x_px - 25, fixed_target_y_px), (fixed_target_x_px + 25, fixed_target_y_px), 4)

    # -- Purple Arm --
    current_arm_x_px = rail_start_x + (arm_x_cm * pixels_per_cm)
    arm_height_px = MAX_Y_CM * pixels_per_cm
    pygame.draw.line(screen, PURPLE, (current_arm_x_px, rail_y), (current_arm_x_px, rail_y - arm_height_px), 3)
    pygame.draw.rect(screen, PURPLE, (current_arm_x_px - 6, rail_y - 6, 12, 12)) 
    pygame.draw.rect(screen, PURPLE, (current_arm_x_px - 6, rail_y - arm_height_px - 6, 12, 12)) 

    # -- Red Dot --
    current_dot_y_px = rail_y - (dot_y_cm * pixels_per_cm)
    pygame.draw.circle(screen, RED, (int(current_arm_x_px), int(current_dot_y_px)), 20)

    # -- Position Text (Bottom Right) --
    debug_text = font.render(f"Pos: X={arm_x_cm}cm, Y={dot_y_cm}cm", True, BLACK)
    debug_rect = debug_text.get_rect(bottomright=(SCREEN_WIDTH - 20, SCREEN_HEIGHT - 20))
    screen.blit(debug_text, debug_rect)

    pygame.display.flip()
    clock.tick(60)
