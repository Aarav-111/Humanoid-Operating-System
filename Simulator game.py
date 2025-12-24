import pygame
import sys
import os
import math

pygame.init()

info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Robot Navigation - No Escape")

clock = pygame.time.Clock()

BG = (220, 240, 255)
BLACK = (0, 0, 0)
RED = (230, 60, 60)
WHITE = (255, 255, 255)
GRAY = (150, 150, 150)

font = pygame.font.SysFont("arial", 24, bold=True)
small_font = pygame.font.SysFont("arial", 20)

ROOM_COORDS = {
    "l": (WIDTH // 5, HEIGHT // 4),
    "k": (4 * WIDTH // 5, HEIGHT // 4),
    "be": (WIDTH // 5, 3 * HEIGHT // 4),
    "ba": (4 * WIDTH // 5, 3 * HEIGHT // 4)
}
CENTER = (WIDTH // 2, HEIGHT // 2)

robot_radius = 25
robot_x, robot_y = ROOM_COORDS["be"]

SPEED = 7
input_text = ""
target_queue = []

walls = [
    pygame.Rect(50, 50, WIDTH - 100, 15),
    pygame.Rect(50, HEIGHT - 100, WIDTH - 100, 15),
    pygame.Rect(50, 50, 15, HEIGHT - 150),
    pygame.Rect(WIDTH - 65, 50, 15, HEIGHT - 150),
    pygame.Rect(100, HEIGHT // 2 - 7, WIDTH // 3, 15), 
    pygame.Rect(2 * WIDTH // 3 - 50, HEIGHT // 2 - 7, WIDTH // 3, 15), 
]

def draw_dotted_line(surf, color, start_pos, end_pos, width=2, dash_length=15):
    x1, y1 = start_pos
    x2, y2 = end_pos
    dist = math.hypot(x2 - x1, y2 - y1)
    dashes = int(dist // dash_length)
    for i in range(dashes):
        start = (x1 + (x2 - x1) * i / dashes, y1 + (y2 - y1) * i / dashes)
        end = (x1 + (x2 - x1) * (i + 0.5) / dashes, y1 + (y2 - y1) * (i + 0.5) / dashes)
        if i % 2 == 0:
            pygame.draw.line(surf, color, start, end, width)

def draw_walls():
    for wall in walls:
        pygame.draw.rect(screen, BLACK, wall)

def draw_labels():
    labels = [
        ("Living Room (l)", (ROOM_COORDS["l"][0] - 80, ROOM_COORDS["l"][1] - 60)),
        ("Kitchen (k)", (ROOM_COORDS["k"][0] - 60, ROOM_COORDS["k"][1] - 60)),
        ("Bed Room (be)", (ROOM_COORDS["be"][0] - 80, ROOM_COORDS["be"][1] + 40)),
        ("Bathroom (ba)", (ROOM_COORDS["ba"][0] - 60, ROOM_COORDS["ba"][1] + 40))
    ]
    for text, pos in labels:
        screen.blit(font.render(text, True, BLACK), pos)

def draw_robot(x, y):
    pygame.draw.circle(screen, RED, (int(x), int(y)), robot_radius)

def set_destination(cmd):
    global target_queue
    if cmd not in ROOM_COORDS: return
    
    dest_pos = ROOM_COORDS[cmd]
    curr_room = None
    for room, pos in ROOM_COORDS.items():
        if math.hypot(robot_x - pos[0], robot_y - pos[1]) < 5:
            curr_room = room
    
    if curr_room == cmd: return

    is_diagonal = (curr_room == 'be' and cmd == 'k') or (curr_room == 'k' and cmd == 'be') or \
                  (curr_room == 'l' and cmd == 'ba') or (curr_room == 'ba' and cmd == 'l')
    
    if is_diagonal:
        target_queue = [dest_pos]
    else:
        target_queue = [CENTER, dest_pos]

def move_robot():
    global robot_x, robot_y, target_queue
    if target_queue:
        tx, ty = target_queue[0]
        dx, dy = tx - robot_x, ty - robot_y
        dist = math.hypot(dx, dy)
        if dist < SPEED:
            robot_x, robot_y = tx, ty
            target_queue.pop(0)
        else:
            robot_x += (dx / dist) * SPEED
            robot_y += (dy / dist) * SPEED

def render():
    screen.fill(BG)
    draw_dotted_line(screen, GRAY, ROOM_COORDS["k"], ROOM_COORDS["be"], 2)
    draw_dotted_line(screen, GRAY, ROOM_COORDS["l"], ROOM_COORDS["ba"], 2)
    draw_walls()
    draw_labels()
    draw_robot(robot_x, robot_y)
    
    pygame.draw.rect(screen, WHITE, (50, HEIGHT - 70, 300, 40))
    pygame.draw.rect(screen, BLACK, (50, HEIGHT - 70, 300, 40), 2)
    screen.blit(small_font.render(input_text, True, BLACK), (60, HEIGHT - 62))
    pygame.display.flip()

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                set_destination(input_text.lower().strip())
                input_text = ""
            elif event.key == pygame.K_BACKSPACE: input_text = input_text[:-1]
            else: input_text += event.unicode
    move_robot()
    render()
    clock.tick(60)

pygame.quit()
sys.exit()
