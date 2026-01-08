#!/usr/bin/env python3
import os
import shutil
import argparse
from pathlib import Path
import re
import requests
import base64
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_saved_api_key():
    """Load saved API key from file."""
    try:
        with open('api_key.json', 'r') as f:
            data = json.load(f)
            return data.get('api_key', '')
    except (FileNotFoundError, json.JSONDecodeError):
        return ''

def save_api_key(api_key):
    """Save API key to file."""
    with open('api_key.json', 'w') as f:
        json.dump({'api_key': api_key}, f)

def encode_image(image_path):
    """Encode image to base64 string."""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def call_gemini_api(api_key, prompt, image_path=None):
    """Make API call to Gemini."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"

    headers = {
        'Content-Type': 'application/json'
    }

    parts = [{"text": prompt}]
    if image_path:
        image_data = encode_image(image_path)
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_data
            }
        })

    data = {
        "contents": [{
            "parts": parts
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {str(e)}")

def get_bird_info(bird_name, api_key):
    """Get detailed information about a bird using Gemini API."""
    try:
        prompt = f"""For the bird species '{bird_name}', provide the following information in this exact format:
        Scientific name: [Scientific name]
        Description: [100 words about the bird's appearance, habitat, behavior, and characteristics]
        Wikipedia link: [Wikipedia link]

        Be specific and accurate. The description should be less than 100 words.
        """

        response = call_gemini_api(api_key, prompt)
        return response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    except Exception as e:
        return None

def create_bird_info_file(bird_folder, bird_name, info_text):
    """Create an info file for a bird species."""
    info_file = bird_folder / "info.txt"
    with open(info_file, "w", encoding="utf-8") as f:
        f.write(f"Name: {bird_name}\n\n")
        f.write(info_text)

def get_new_filename(original_path, bird_name, is_blurred=False):
    """Generate a new filename with bird name as suffix."""
    name = original_path.stem
    ext = original_path.suffix
    new_name = f"{name} {bird_name}"
    if is_blurred:
        new_name += " blurred"
    new_name += ext
    return new_name

def identify_bird(image_path, api_key, loaded_birds, location):
    """Use Gemini API to identify if the image contains a bird and get its name."""
    try:
        prompt = f"""Analyze this image and tell me:
        1. Does this image contain a bird? (Yes/No)
        2. If yes, what is the name of the bird? (If you can identify it)
        3. Is the image blurred or out of focus? (Yes/No)
        Please respond in this exact format:
        Contains bird: [Yes/No]
        Bird name: [Name or N/A]
        Is blurred: [Yes/No]

        Be exact in the name of the bird. Qualify the exact species. Be specific. Don't use scientific names.
        {f"The probable location where the bird was shot is {location}. So it's likely to be a bird from that region." if location else ""}

        You have already identified the following birds: {', '.join(list(set(loaded_birds)))} already. Check if this bird is one of them. If yes, make sure to return the exact same name.
        The last bird you identified was {loaded_birds[-1]}. See if this bird is same as the last bird you identified.
        """

        response = call_gemini_api(api_key, prompt, image_path)
        response_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')

        # Parse the response
        contains_bird = "Contains bird: Yes" in response_text
        bird_name = None
        is_blurred = False

        for line in response_text.split('\n'):
            if line.startswith('Bird name:'):
                bird_name = line.replace('Bird name:', '').strip()
                bird_name = re.sub(r'[^a-zA-Z\s]', '', bird_name).strip()
                if bird_name.lower() == 'n/a':
                    bird_name = None
            elif line.startswith('Is blurred:'):
                is_blurred = "Is blurred: Yes" in line
        return contains_bird, bird_name, is_blurred
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        return False, None, False

def process_folder(input_folder, api_key, location=None):
    """Process all images in the input folder."""
    input_dir = Path(input_folder)

    if not input_dir.exists():
        print(f"Error: Input folder '{input_folder}' does not exist")
        return

    # Create output directory
    output_dir = input_dir / '0000-bird-folders'
    output_dir.mkdir(exist_ok=True)

    # Get list of images
    images = [f for f in input_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
    total_images = len(images)

    if total_images == 0:
        print("No images found in the folder")
        return

    print(f"Found {total_images} images to process")
    loaded_birds = ["None"]

    # Process each image
    for i, image_path in enumerate(images, 1):
        print(f"\n[{i}/{total_images}] Processing: {image_path.name}")

        contains_bird, bird_name, is_blurred = identify_bird(image_path, api_key, loaded_birds, location)

        status = f"  Result: "
        if bird_name and bird_name != "NA" and bird_name != "N/A" and bird_name != "Unidentified":
            status += f"✓ {bird_name}"
            if is_blurred:
                status += " (blurred)"
            new_filename = get_new_filename(image_path, bird_name, is_blurred)
            new_path = output_dir / new_filename
            shutil.copy2(str(image_path), str(new_path))
            loaded_birds.append(bird_name)
        else:
            status += "? Unidentified"
            if is_blurred:
                status += " (blurred)"
            new_filename = get_new_filename(image_path, "Unidentified", is_blurred)
            new_path = output_dir / new_filename
            shutil.copy2(str(image_path), str(new_path))
            loaded_birds.append("Unidentified")

        print(status)

    print(f"\n✓ Classification completed! Files saved to: {output_dir}")
    print("\nDistributing photos into folders...")
    distribute_photos(output_dir, api_key)

def distribute_photos(output_dir, api_key):
    """Distribute photos into folders based on their names."""
    images = [f for f in output_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
    total_images = len(images)

    if total_images == 0:
        print("No images found to distribute")
        return

    unique_birds = set()

    for i, image_path in enumerate(images, 1):
        print(f"[{i}/{total_images}] Organizing: {image_path.name}")

        # Extract bird name from filename
        name_parts = image_path.stem.split()
        if len(name_parts) > 1:
            bird_name = (" ".join(name_parts[1:])).split(".")[0]

            if bird_name.lower() == "unidentified" or not bird_name:
                continue

            unique_birds.add(bird_name)

            # Create bird folder
            bird_folder = output_dir / bird_name
            bird_folder.mkdir(exist_ok=True)

            # Move the file to the bird folder
            shutil.move(str(image_path), str(bird_folder / image_path.name))

            # Create info.txt file if it doesn't exist
            info_file = bird_folder / "info.txt"
            if not info_file.exists():
                print(f"  Creating info file for {bird_name}...")
                info_text = get_bird_info(bird_name, api_key)
                if info_text:
                    create_bird_info_file(bird_folder, bird_name, info_text)

    print(f"\n✓ Distribution completed! Organized {len(unique_birds)} unique bird species.")

def main():
    parser = argparse.ArgumentParser(
        description='Classify bird photos using Google Gemini AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/photos
  %(prog)s /path/to/photos --location "Kerala, India"
  %(prog)s /path/to/photos --api-key YOUR_API_KEY
        """
    )
    parser.add_argument('folder', help='Path to folder containing bird photos')
    parser.add_argument('--api-key', help='Google Gemini API key (will be saved for future use)')
    parser.add_argument('--location', help='Probable location where photos were taken')

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key
    if not api_key:
        api_key = load_saved_api_key()
        if not api_key:
            api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        print("Error: No API key provided.")
        print("Please provide an API key using one of these methods:")
        print("  1. Use --api-key flag: python classify_cli.py /path/to/folder --api-key YOUR_KEY")
        print("  2. Save it once: python classify_cli.py /path/to/folder --api-key YOUR_KEY")
        print("  3. Set GEMINI_API_KEY environment variable")
        print("\nGet your API key at: https://aistudio.google.com/apikey")
        return

    # Save API key if provided
    if args.api_key:
        save_api_key(api_key)
        print("API key saved for future use\n")

    # Process the folder
    process_folder(args.folder, api_key, args.location)

if __name__ == "__main__":
    main()
