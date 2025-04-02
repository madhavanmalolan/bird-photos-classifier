from PIL import Image, ImageDraw

def create_icon():
    # Create a 256x256 image with a transparent background
    size = 256
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw a simple bird shape
    # Body
    draw.ellipse([size//4, size//3, 3*size//4, 2*size//3], fill=(52, 152, 219))
    # Head
    draw.ellipse([3*size//4, size//3, 7*size//8, size//2], fill=(52, 152, 219))
    # Beak
    draw.polygon([(7*size//8, size//2), (size, size//2), (7*size//8, 3*size//8)], fill=(241, 196, 15))
    # Wing
    draw.ellipse([size//2, size//2, 3*size//4, 2*size//3], fill=(41, 128, 185))
    
    # Save as ICO and ICNS
    image.save('icon.ico', format='ICO')
    image.save('icon.icns', format='ICNS')

if __name__ == "__main__":
    create_icon() 