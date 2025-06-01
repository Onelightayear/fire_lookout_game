# fire_lookout_parallax.py
# Fire Lookout Game with Reporting, Weather, Parallax, and UI Overlay

import pygame
import sys
import random
import math

# --- Constants ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
FOV = 150

# Colors
WHITE = (255, 255, 255)

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Fire Lookout - Osborne Tracker")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Arial", 18)

# --- Weather ---
weather_conditions = ["Clear", "Rainy", "Windy", "Hot"]
current_weather = random.randint(0, 3)
weather = weather_conditions[current_weather]

# --- Load Assets ---
def load_image(path, fallback_color=(50, 50, 50)):
    try:
        return pygame.image.load(path).convert_alpha()
    except:
        surface = pygame.Surface((800, 600))
        surface.fill(fallback_color)
        return surface

def load_mask(path, fallback_color=(255, 255, 255)):
    try:
        return pygame.image.load(path).convert()
    except:
        surface = pygame.Surface((800, 600))
        surface.fill(fallback_color)
        return surface

# Parallax layers for weather
background_far = load_image(f"assets/background_far_{weather.lower()}.png", (135, 206, 235))
background_mid = load_image(f"assets/background_mid_{weather.lower()}.png", (100, 155, 100))

background_mid_mask = load_mask("assets/mid_mask.png")
background_far_mask = load_mask("assets/far_mask.png")

haze_layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
haze_layer.fill((200, 200, 255, 30))  # bluish, 30 alpha

# Overlay and sprites
fire_image = load_image("assets/fire.png", (255, 100, 0))
smoke_image = load_image("assets/smoke.png", (128, 128, 128))
window_overlay = load_image("assets/osborne_overlay.png", (0, 0, 0, 0))
crosshair_image = load_image("assets/crosshair.png", (255, 255, 255))

# --- Classes ---
class Fire(pygame.sprite.Sprite):
    def __init__(self, azimuth, distance, base_lifetime):
        super().__init__()
        self.azimuth = azimuth
        self.distance = distance
        self.layer = 'far' if distance > 150 else 'mid'
        self.reported = False
        
        # Generate random terrain offset once at creation (positive = lower on hillside)
        self.terrain_offset = random.randint(0, 80)  # 0-80 pixels down from hilltop
        
        self.base_image = fire_image
        self.smoke_image = smoke_image

        # Scale based on layer
        if self.layer == 'far':
            scale = 0.5
        else:
            scale = 1.0
            
        self.image = pygame.transform.scale(
            self.base_image, 
            (int(self.base_image.get_width() * scale),
             int(self.base_image.get_height() * scale))
        )
        self.smoke = pygame.transform.scale(
            self.smoke_image, 
            (int(self.smoke_image.get_width() * scale),
             int(self.smoke_image.get_height() * scale))
        )

        # Weather effects on lifetime
        if weather == "Rainy":
            self.lifetime = base_lifetime * 0.5
        elif weather == "Windy":
            self.lifetime = base_lifetime * 1.5
        elif weather == "Hot":
            self.lifetime = base_lifetime * 2.0
        else:
            self.lifetime = base_lifetime

        self.spawn_time = pygame.time.get_ticks()

    def is_expired(self):
        return pygame.time.get_ticks() - self.spawn_time > self.lifetime

    def get_terrain_height_at_screen_x(self, screen_x, mask, player_azimuth):
        """Get the terrain height at a specific screen X position"""
        mask_width = mask.get_width()
        mask_height = mask.get_height()
        
        # Handle narrow masks (same logic as draw_parallax_layer)
        if mask_width <= SCREEN_WIDTH:
            # For narrow masks, direct screen-to-mask mapping
            mask_x = int((screen_x / SCREEN_WIDTH) * mask_width) % mask_width
        else:
            # For wide masks, calculate which part of the mask is visible at this screen position
            # This is the inverse of the parallax drawing logic
            parallax_offset = int((player_azimuth / 360) * mask_width * 1) % mask_width
            
            # Convert screen X to mask position, accounting for current parallax offset
            mask_x = (parallax_offset + screen_x) % mask_width
        
        # Scan from top to bottom to find the FIRST terrain pixel
        for y in range(mask_height):
            try:
                pixel = mask.get_at((mask_x, y))
                # Check if this is a terrain pixel
                brightness = (pixel[0] + pixel[1] + pixel[2]) / 3
                if brightness < 200:
                    # Convert mask Y to screen Y and add the fire's terrain offset
                    base_screen_y = int((y / mask_height) * SCREEN_HEIGHT)
                    screen_y = base_screen_y + self.terrain_offset
                    return screen_y
            except IndexError:
                continue
        
        # If no terrain found, return fallback based on layer (with offset)
        if self.layer == 'far':
            return int(SCREEN_HEIGHT * 0.7) + self.terrain_offset
        else:
            return int(SCREEN_HEIGHT * 0.85) + self.terrain_offset

    def get_screen_pos(self, player_azimuth):
        """Get the screen position of this fire relative to player view"""
        # Calculate relative angle to player's view
        relative_angle = (self.azimuth - player_azimuth + 180) % 360 - 180
        
        # Check if fire is within field of view
        if abs(relative_angle) > FOV / 2:
            return None

        # Calculate screen x position based on relative angle
        x = int((relative_angle + FOV / 2) / FOV * SCREEN_WIDTH)
        
        # Get terrain height at this screen position (not azimuth position)
        mask = background_far_mask if self.layer == 'far' else background_mid_mask
        screen_y = self.get_terrain_height_at_screen_x(x, mask, player_azimuth)
        
        return x, screen_y

    def draw(self, surface, player_azimuth):
        pos = self.get_screen_pos(player_azimuth)
        if pos:
            x, y = pos
            
            # Position fire sprite on the terrain surface
            fire_rect = self.image.get_rect()
            fire_rect.centerx = x
            fire_rect.bottom = y  # Bottom of fire sits on terrain
            
            # Draw fire
            surface.blit(self.image, fire_rect)
            
            # Position smoke above the fire
            smoke_rect = self.smoke.get_rect()
            smoke_rect.centerx = x
            smoke_rect.bottom = fire_rect.top - 5  # Small gap between fire and smoke
            
            # Draw smoke
            surface.blit(self.smoke, smoke_rect)

# --- Game State ---
fires = []
reports = []
player_azimuth = 0
osborne_open = False
crosshair_pos = [SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2]
next_fire_time = pygame.time.get_ticks() + random.randint(3000, 6000)

# --- Functions ---
def draw_parallax_layer(image, scroll_factor):
    bg_width = image.get_width()
    if bg_width <= SCREEN_WIDTH:
        screen.blit(pygame.transform.scale(image, (SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
        return

    offset = int((player_azimuth / 360) * bg_width * scroll_factor) % bg_width
    screen.blit(image, (-offset, 0))
    screen.blit(image, (-offset + bg_width, 0))

def has_terrain_at_azimuth(azimuth, mask, player_azimuth=0):
    """Check if there's terrain at a specific azimuth in the given mask"""
    mask_width = mask.get_width()
    mask_height = mask.get_height()
    
    # Handle narrow masks vs wide masks (same logic as get_terrain_height_at_azimuth)
    if mask_width <= SCREEN_WIDTH:
        # For narrow masks, use direct azimuth mapping
        x = int((azimuth / 360) * mask_width) % mask_width
    else:
        # For wide masks, account for parallax offset
        parallax_offset = int((player_azimuth / 360) * mask_width * 1) % mask_width
        base_x = int((azimuth / 360) * mask_width)
        x = (base_x + parallax_offset) % mask_width
    
    # Scan from top to bottom looking for terrain
    for y in range(mask_height):
        try:
            pixel = mask.get_at((x, y))
            # More flexible terrain detection
            brightness = (pixel[0] + pixel[1] + pixel[2]) / 3
            if brightness < 200:  # Found terrain (darker pixel)
                return True
        except IndexError:
            continue
    
    return False

def generate_fire():
    """Generate a new fire at a random location with terrain"""
    max_attempts = 20  # Increase attempts to find terrain
    attempts = 0
    
    while attempts < max_attempts:
        azimuth = random.randint(0, 359)
        distance = random.choice([100, 200])  # 100 = mid, 200 = far
        
        # Choose correct mask for terrain verification
        mask = background_mid_mask if distance == 100 else background_far_mask
        
        # Check if there's terrain at this azimuth
        if has_terrain_at_azimuth(azimuth, mask):
            base_lifetime = random.randint(10000, 50000)
            fire = Fire(azimuth, distance, base_lifetime)
            
            fires.append(fire)
            layer_name = "far" if distance > 150 else "mid"
            # print(f"Generated {layer_name} fire at azimuth {azimuth}°")
            return
        
        attempts += 1
    
    print(f"Could not find suitable terrain after {max_attempts} attempts")

def draw_far():
    draw_parallax_layer(background_far, 1)

    # Draw far layer fires
    fires_to_remove = []
    for fire in fires:
        if fire.layer == 'far':
            if fire.is_expired():
                fires_to_remove.append(fire)
            else:
                fire.draw(screen, player_azimuth)
    
    # Remove expired fires
    for fire in fires_to_remove:
        fires.remove(fire)
    
    screen.blit(haze_layer, (0, 0))

def draw_mid():
    draw_parallax_layer(background_mid, 1)

    # Draw mid layer fires
    fires_to_remove = []
    for fire in fires:
        if fire.layer == 'mid':
            if fire.is_expired():
                fires_to_remove.append(fire)
            else:
                fire.draw(screen, player_azimuth)
    
    # Remove expired fires
    for fire in fires_to_remove:
        fires.remove(fire)

def draw_osborne_ui():
    screen.blit(window_overlay, (0, 0))
    screen.blit(crosshair_image, (crosshair_pos[0] - crosshair_image.get_width()//2, 
                                  crosshair_pos[1] - crosshair_image.get_height()//2))
    
    cross_azimuth = int((crosshair_pos[0] / SCREEN_WIDTH) * FOV + (player_azimuth - FOV // 2)) % 360
    cross_elevation = int((300 - crosshair_pos[1]) / (600 / 90))
    
    info = f"Target Azimuth: {cross_azimuth}°, Declination: {cross_elevation}°, Weather: {weather}"
    text = font.render(info, True, WHITE)
    screen.blit(text, (20, SCREEN_HEIGHT - 30))

def check_report():
    cross_azimuth = int((crosshair_pos[0] / SCREEN_WIDTH) * FOV + (player_azimuth - FOV // 2)) % 360
    cross_x, cross_y = crosshair_pos

    for fire in fires:
        pos = fire.get_screen_pos(player_azimuth)
        if not pos:
            continue
        fire_x, fire_y = pos

        angle_diff = abs((fire.azimuth - cross_azimuth + 180) % 360 - 180)
        distance_diff = math.sqrt((fire_x - cross_x)**2 + (fire_y - cross_y)**2)
        
        if not fire.reported and angle_diff < 15 and distance_diff < 50:
            fire.reported = True
            reports.append((cross_azimuth, cross_y))
            fire_declination = int((300-cross_y)/(600/90))
            print(f"Fire reported at Azimuth {cross_azimuth}°, Declination {fire_declination}°")
            break

# --- Main Loop ---
running = True
print(f"Current weather: {weather}")

while running:
    dt = clock.tick(FPS)
    current_time = pygame.time.get_ticks()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_o:
                osborne_open = not osborne_open
            elif event.key == pygame.K_SPACE and osborne_open:
                check_report()
        elif event.type == pygame.MOUSEMOTION and osborne_open:
            crosshair_pos = list(pygame.mouse.get_pos())

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        player_azimuth = (player_azimuth - 1) % 360
    if keys[pygame.K_RIGHT]:
        player_azimuth = (player_azimuth + 1) % 360

    # Generate new fires
    if current_time >= next_fire_time:
        # print(f"Attempting to generate fire at time {current_time}")
        generate_fire()
        # Set next fire time (reduced for testing - change back to longer intervals)
        waiting_time_scale = 1
        if weather == 'Hot':
            waiting_time_scale = 2
        elif weather == 'Windy':
            waiting_time_scale = 1.5
        elif weather == 'Rainy':
            waiting_time_scale = 0.5
        next_fire_time = current_time + random.randint(4000,8000)/waiting_time_scale  # Change to random.randint(4000, 8000) for normal gameplay
        print(f"Next fire time set to {next_fire_time}")
    
    # Draw layers in correct order
    screen.fill((0, 0, 0))  # Clear screen
    draw_far()
    draw_mid()

    if osborne_open:
        draw_osborne_ui()

    pygame.display.flip()

pygame.quit()
sys.exit()