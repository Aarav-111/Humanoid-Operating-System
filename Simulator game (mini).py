import pygame
import sys

pygame.init()

# Window setup (bigger for more space)
WIDTH, HEIGHT = 1100, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Robot Navigation Game")

clock = pygame.time.Clock()

# Colors
BG = (220, 240, 255)
BLACK = (0, 0, 0)
RED = (230, 60, 60)

# Font
font = pygame.font.SysFont("arial", 28, bold=True)

# Robot settings
robot_radius = 18
robot_x = WIDTH // 2 - 250
robot_y = HEIGHT - 100
speed = 4

# Walls (more spread out)
walls = [
    # Outer walls
    pygame.Rect(20, 20, WIDTH - 40, 12),
    pygame.Rect(20, HEIGHT - 32, WIDTH - 40, 12),
    pygame.Rect(20, 20, 12, HEIGHT - 40),
    pygame.Rect(WIDTH - 32, 20, 12, HEIGHT - 40),

    # Horizontal walls
    pygame.Rect(40, 240, 420, 14),
    pygame.Rect(640, 240, 420, 14),

    # Vertical wall
    pygame.Rect(WIDTH // 2 - 7, 40, 14, 180),
]

def draw_walls():
    for wall in walls:
        pygame.draw.rect(screen, BLACK, wall)

def draw_labels():
    screen.blit(font.render("Living Room", True, BLACK), (120, 80))
    screen.blit(font.render("Kitchen", True, BLACK), (760, 80))
    screen.blit(font.render("Bed Room", True, BLACK), (140, 300))
    screen.blit(font.render("Bathroom", True, BLACK), (760, 300))

def draw_robot(x, y):
    pygame.draw.circle(screen, RED, (x, y), robot_radius)
    # Front arrow (always facing up)
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
    robot_rect = pygame.Rect(
        x - robot_radius,
        y - robot_radius,
        robot_radius * 2,
        robot_radius * 2,
    )
    for wall in walls:
        if robot_rect.colliderect(wall):
            return True
    return False

# Main loop
running = True
while running:
    clock.tick(60)
    screen.fill(BG)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()

    new_x, new_y = robot_x, robot_y

    if keys[pygame.K_UP]:
        new_y -= speed
    if keys[pygame.K_DOWN]:
        new_y += speed
    if keys[pygame.K_LEFT]:
        new_x -= speed
    if keys[pygame.K_RIGHT]:
        new_x += speed

    if not check_collision(new_x, new_y):
        robot_x, robot_y = new_x, new_y

    draw_walls()
    draw_labels()
    draw_robot(robot_x, robot_y)

    pygame.display.flip()

pygame.quit()
sys.exit()
