import os
import shutil
from pathlib import Path
import google.genai as genai
from PIL import Image
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("Please set GOOGLE_API_KEY in the .env file")

client = genai.Client(api_key=GOOGLE_API_KEY)

def get_bird_info(bird_name):
    """Get detailed information about a bird using Gemini AI."""
    try:
        prompt = f"""For the bird species '{bird_name}', provide the following information in this exact format:
        Scientific name: [Scientific name]
        Description: [100 words about the bird's appearance, habitat, behavior, and characteristics]
        Fact 1: [280 character-length interesting fact about the bird]
        Fact 2: [280 character-length interesting fact about the bird]
        Fact 3: [280 character-length interesting fact about the bird]
        Fact 4: [280 character-length interesting fact about the bird]
        Fact 5: [280 character-length interesting fact about the bird]
        Fact 6: [280 character-length interesting fact about the bird]
        Fact 7: [280 character-length interesting fact about the bird]
        Fact 8: [280 character-length interesting fact about the bird]
        Fact 9: [280 character-length interesting fact about the bird]
        Fact 10: [280 character-length interesting fact about the bird]
        
        Be specific and accurate. The description should be exactly 100 words.
        The fact should be engaging and informative, under 280 characters.
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt])
        return response.text
    except Exception as e:
        print(f"Error getting bird info: {str(e)}")
        return None

def create_bird_info_file(bird_folder, bird_name, info_text):
    """Create an info file for a bird species."""
    info_file = bird_folder / "info.txt"
    with open(info_file, "w", encoding="utf-8") as f:
        f.write(f"Name: {bird_name}\n\n")
        f.write(info_text)

def get_new_filename(original_path, bird_name):
    """Generate a new filename with bird name as suffix."""
    # Get the original filename without extension
    name = original_path.stem
    # Get the extension
    ext = original_path.suffix
    # Create new filename with bird name as suffix
    new_name = f"{name}_{bird_name}{ext}"
    return new_name

def identify_bird(image_path):
    """Use Gemini AI to identify if the image contains a bird and get its name."""
    try:
        img = Image.open(image_path)
        prompt = """Analyze this image and tell me:
        1. Does this image contain a bird? (Yes/No)
        2. If yes, what is the name of the bird? (If you can identify it)
        Please respond in this exact format:
        Contains bird: [Yes/No]
        Bird name: [Name or N/A]
        
        Be exact in the name of the bird. Qualify the exact species. Be specific. Don't use scientific names.
        The bird is most likely to be shot in India, but might also have been shot in other countries.
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt, img])
        response_text = response.text
        print(response_text)
        
        # Parse the response
        contains_bird = "Contains bird: Yes" in response_text
        bird_name = None
        
        if contains_bird:
            for line in response_text.split('\n'):
                if line.startswith('Bird name:'):
                    bird_name = line.replace('Bird name:', '').strip()
                    if bird_name.lower() == 'n/a':
                        bird_name = None
                    break
        
        return contains_bird, bird_name
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        return False, None

def process_photos():
    # Create input and output directories if they don't exist
    input_dir = Path('input')
    output_dir = Path('output')
    unidentified_dir = output_dir / "Unidentified"
    output_dir.mkdir(exist_ok=True)
    unidentified_dir.mkdir(exist_ok=True)
    
    # Process each folder in input directory
    for folder in input_dir.iterdir():
        if not folder.is_dir():
            continue
            
        print(f"Processing folder: {folder.name}")
        
        # Process each image in the folder
        for image_path in folder.glob('*'):
            if not image_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                continue
                
            print(f"Processing image: {image_path.name}")
            contains_bird, bird_name = identify_bird(image_path)
            
            if contains_bird and bird_name:
                # Create bird folder if it doesn't exist
                bird_folder = output_dir / bird_name
                bird_folder.mkdir(exist_ok=True)
                
                # Create info file if it doesn't exist
                info_file = bird_folder / "info.txt"
                if not info_file.exists():
                    print(f"Getting information for {bird_name}...")
                    info_text = get_bird_info(bird_name)
                    if info_text:
                        create_bird_info_file(bird_folder, bird_name, info_text)
                        print(f"Created info file for {bird_name}")
                
                # Generate new filename with bird name as suffix
                new_filename = get_new_filename(image_path, bird_name)
                
                # Copy the image to the bird folder with new name
                shutil.copy2(image_path, bird_folder / new_filename)
                print(f"Copied {image_path.name} to {bird_name} folder as {new_filename}")
            else:
                # Move unidentified photos to the Unidentified folder
                shutil.copy2(image_path, unidentified_dir / image_path.name)
                print(f"Moved {image_path.name} to Unidentified folder")

if __name__ == "__main__":
    process_photos()
