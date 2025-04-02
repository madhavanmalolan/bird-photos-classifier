from PIL import Image, ImageDraw
import os

def create_icon(size, output_path):
    # Create a new image with a transparent background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a simple bird shape
    # Body
    draw.ellipse([size*0.2, size*0.2, size*0.8, size*0.8], fill='#4CAF50')
    # Head
    draw.ellipse([size*0.6, size*0.1, size*0.9, size*0.4], fill='#4CAF50')
    # Beak
    draw.polygon([(size*0.9, size*0.25), (size*0.95, size*0.25), (size*0.9, size*0.3)], fill='#FFC107')
    # Eye
    draw.ellipse([size*0.7, size*0.15, size*0.75, size*0.2], fill='white')
    draw.ellipse([size*0.72, size*0.17, size*0.73, size*0.18], fill='black')
    
    # Save the icon
    img.save(output_path)

# Create icons directory if it doesn't exist
os.makedirs('icons', exist_ok=True)

# Generate icons in different sizes
sizes = [16, 32, 48, 64, 128, 256, 512, 1024]

# Generate PNG icons
for size in sizes:
    create_icon(size, f'icons/icon_{size}.png')

# Save the main icon
create_icon(1024, 'icon.png')

print("Icons generated successfully!") 