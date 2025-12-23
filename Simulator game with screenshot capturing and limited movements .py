import pygame
import sys
import os
import pyautogui
import time

pygame.init()

WIDTH, HEIGHT = 1100, 650
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Robot Navigation Game")

clock = pygame.time.Clock()

BG = (220, 240, 255)
BLACK = (0, 0, 0)
RED = (230, 60, 60)
WHITE = (255, 255, 255)

font = pygame.font.SysFont("arial", 24, bold=True)
small_font = pygame.font.SysFont("arial", 20)

robot_radius = 18
robot_x = WIDTH // 2 - 250
robot_y = HEIGHT - 140

CM_TO_PX = 4
MOVE_CM = 5
MOVE_PX = MOVE_CM * CM_TO_PX

DOCS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
IMG_DIR = os.path.join(DOCS_DIR, "imgs")
os.makedirs(IMG_DIR, exist_ok=True)

img_counter = 1

walls = [
    pygame.Rect(20, 20, WIDTH - 40, 12),
    pygame.Rect(20, HEIGHT - 80, WIDTH - 40, 12),
    pygame.Rect(20, 20, 12, HEIGHT - 100),
    pygame.Rect(WIDTH - 32, 20, 12, HEIGHT - 100),
    pygame.Rect(40, 260, 420, 14),
    pygame.Rect(640, 260, 420, 14),
    pygame.Rect(WIDTH // 2 - 7, 40, 14, 200),
]

input_box = pygame.Rect(40, HEIGHT - 55, 300, 35)
input_text = ""

def draw_walls():
    for wall in walls:
        pygame.draw.rect(screen, BLACK, wall)

def draw_labels():
    screen.blit(font.render("Living Room", True, BLACK), (120, 90))
    screen.blit(font.render("Kitchen", True, BLACK), (760, 90))
    screen.blit(font.render("Bed Room", True, BLACK), (140, 330))
    screen.blit(font.render("Bathroom", True, BLACK), (760, 330))

def draw_robot(x, y):
    pygame.draw.circle(screen, RED, (int(x), int(y)), robot_radius)
    pygame.draw.polygon(
        screen,
        BLACK,
        [
            (x, y - robot_radius - 12),
            (x - 7, y - robot_radius + 2),
            (x + 7, y - robot_radius + 2),
        ],
    )

def check_collision(x, y):
    rect = pygame.Rect(
        x - robot_radius,
        y - robot_radius,
        robot_radius * 2,
        robot_radius * 2,
    )
    if x - robot_radius < 0 or x + robot_radius > WIDTH or y - robot_radius < 0 or y + robot_radius > HEIGHT:
        return True
    for wall in walls:
        if rect.colliderect(wall):
            return True
    return False

def save_screenshot():
    global img_counter
    file_path = os.path.join(IMG_DIR, f"img_{img_counter:04d}.png")
    
    try:
        pos = pygame.display.get_window_position()
        if pos:
            x, y = pos
            img = pyautogui.screenshot(region=(x, y, WIDTH, HEIGHT))
            img.save(file_path)
        else:
            pygame.image.save(screen, file_path)
    except:
        pygame.image.save(screen, file_path)
        
    img_counter += 1

def execute_command(cmd):
    global robot_x, robot_y
    dx, dy = 0, 0
    if cmd == "f": dy = -MOVE_PX
    elif cmd == "b": dy = MOVE_PX
    elif cmd == "l": dx = -MOVE_PX
    elif cmd == "r": dx = MOVE_PX
    elif cmd == "s": return

    new_x = robot_x + dx
    new_y = robot_y + dy

    if not check_collision(new_x, new_y):
        robot_x, robot_y = new_x, new_y
        # Render the move before taking screenshot
        render_frame() 
        save_screenshot()

def render_frame():
    screen.fill(BG)
    draw_walls()
    draw_labels()
    draw_robot(robot_x, robot_y)
    pygame.draw.rect(screen, WHITE, input_box)
    pygame.draw.rect(screen, BLACK, input_box, 2)
    txt_surface = small_font.render(input_text, True, BLACK)
    screen.blit(txt_surface, (input_box.x + 8, input_box.y + 7))
    screen.blit(
        small_font.render(f"Command: f b l r s | Step = {MOVE_CM} cm", True, BLACK),
        (360, HEIGHT - 48),
    )
    pygame.display.flip()

running = True
while running:
    clock.tick(60)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if input_text:
                    execute_command(input_text.lower().strip())
                input_text = ""
            elif event.key == pygame.K_BACKSPACE:
                input_text = input_text[:-1]
            else:
                if len(input_text) < 5:
                    input_text += event.unicode
    render_frame()

pygame.quit()
sys.exit()
