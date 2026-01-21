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
                bird_name = re.sub(r'[^a-zA-Z\s\'\-]', '', bird_name).strip()
                if bird_name.lower() == 'n/a':
                    bird_name = None
            elif line.startswith('Is blurred:'):
                is_blurred = "Is blurred: Yes" in line
        return contains_bird, bird_name, is_blurred
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        return False, None, False

def process_folder(input_folder, api_key, location=None, skip_review=False, classify_only=False, distribute_only=False):
    """Process all images in the input folder."""
    input_dir = Path(input_folder)

    if not input_dir.exists():
        print(f"Error: Input folder '{input_folder}' does not exist")
        return

    # Create output directory
    # Extract folder number from directory name (e.g., 0241D3300 -> 0241)
    folder_name = input_dir.name
    folder_number = folder_name.split('D3300')[0] if 'D3300' in folder_name.upper() else folder_name
    output_dir = input_dir / f'{folder_number} Birds'

    # If distribute-only mode, skip to distribution
    if distribute_only:
        if not output_dir.exists():
            print(f"Error: Output directory '{output_dir}' does not exist")
            print("Run classification first without --distribute-only flag")
            return

        print("\n" + "=" * 60)
        print("DISTRIBUTE-ONLY MODE")
        print("=" * 60)
        print(f"Distributing photos from: {output_dir}")
        print()

        # Manual review prompt (unless skipped)
        if not skip_review:
            manual_review_prompt(output_dir)

        print("\nDistributing photos into folders...")
        distribute_photos(output_dir, api_key)
        return

    output_dir.mkdir(exist_ok=True)

    # Get list of images (skip macOS metadata files starting with ._ )
    images = [f for f in input_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and not f.name.startswith('._') and not f.name.startswith('.')]
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

    # Verify photo counts and cleanup originals
    verify_and_cleanup(input_dir, output_dir)

    # Stop here if classify-only mode
    if classify_only:
        print("\n" + "=" * 60)
        print("CLASSIFY-ONLY MODE")
        print("=" * 60)
        print("Classification complete. Distribution skipped.")
        print(f"Photos saved to: {output_dir}")
        print()
        print("To distribute photos later, run:")
        print(f"  python3 classify_cli.py {input_folder} --distribute-only")
        print("=" * 60)
        return

    # Manual review prompt (unless skipped)
    if not skip_review:
        manual_review_prompt(output_dir)

    print("\nDistributing photos into folders...")
    distribute_photos(output_dir, api_key)

def manual_review_prompt(output_dir):
    """
    Prompt user to manually review all photos before distribution.
    User should delete poor quality/blurred photos and verify bird names.
    """
    print("\n" + "=" * 60)
    print("MANUAL REVIEW REQUIRED")
    print("=" * 60)
    print()
    print(f"Please review all photos in: {output_dir}")
    print()
    print("Tasks to complete:")
    print("  1. Delete photos that are:")
    print("     - Poor quality")
    print("     - Blurred or out of focus")
    print("     - Not needed")
    print()
    print("  2. Verify bird names are correct:")
    print("     - Rename files if bird is misidentified")
    print("     - Keep format: YYYY_XXXX Bird Name.JPG")
    print()
    print("  3. When finished, return here and press ENTER to continue")
    print()
    print("=" * 60)

    input("Press ENTER when manual review is complete...")

    print()
    print("✓ Manual review completed")
    print()


def verify_and_cleanup(input_dir, output_dir):
    """
    Verify that photos were classified and cleanup originals.
    Deletes only the parent photos that have corresponding classified versions in output directory.
    Keeps any unclassified photos in the parent directory.
    """
    print("\n" + "=" * 60)
    print("VERIFICATION: Checking photo counts")
    print("=" * 60)

    # Get photos in parent directory (originals)
    parent_photos = [f for f in input_dir.glob('*')
                    if f.suffix.lower() in ['.jpg', '.jpeg', '.png']
                    and not f.name.startswith('._')
                    and not f.name.startswith('.')
                    and f.is_file()]
    parent_count = len(parent_photos)

    # Get photos in output directory (classified)
    output_photos = [f for f in output_dir.glob('*')
                    if f.suffix.lower() in ['.jpg', '.jpeg', '.png']
                    and not f.name.startswith('._')
                    and not f.name.startswith('.')
                    and f.is_file()]
    output_count = len(output_photos)

    print(f"Photos in parent directory: {parent_count}")
    print(f"Photos in output directory: {output_count}")
    print()

    if output_count == 0:
        print("No classified photos found. Original photos kept.")
        print("=" * 60)
        print()
        return

    # Extract original filenames from classified photos
    # Classified format: "0241_0001 Black Kite.JPG"
    # Original format: "0241_0001.JPG"
    classified_originals = set()
    for output_photo in output_photos:
        # Extract the base filename (before the bird name)
        # Pattern: YYYY_XXXX Bird Name.ext -> YYYY_XXXX.ext
        filename = output_photo.stem  # Get filename without extension
        parts = filename.split()
        if len(parts) >= 1:
            base_name = parts[0]  # Get "0241_0001" part
            original_name = f"{base_name}{output_photo.suffix}"
            classified_originals.add(original_name)

    # Find which parent photos have been classified
    to_delete = []
    to_keep = []
    for photo in parent_photos:
        if photo.name in classified_originals:
            to_delete.append(photo)
        else:
            to_keep.append(photo)

    print(f"Successfully classified: {len(to_delete)} photos")
    print(f"Not classified (will keep): {len(to_keep)} photos")
    print()

    if len(to_delete) == 0:
        print("No photos to delete (none were classified)")
        print("=" * 60)
        print()
        return

    # Show summary
    if parent_count == output_count:
        print("✓ All photos were successfully classified!")
    else:
        print("⚠️  Some photos were not classified and will remain in parent directory")
        if to_keep:
            print("\nPhotos that will be kept:")
            for photo in to_keep[:5]:  # Show first 5
                print(f"  - {photo.name}")
            if len(to_keep) > 5:
                print(f"  ... and {len(to_keep) - 5} more")

    print()

    # Ask for confirmation before deleting
    response = input(f"Delete {len(to_delete)} classified photos from parent directory? (y/n): ")

    if response.lower() == 'y':
        print("\nDeleting classified photos from parent directory...")
        deleted_count = 0

        for photo in to_delete:
            try:
                os.remove(photo)
                print(f"  Deleted: {photo.name}")
                deleted_count += 1
            except Exception as e:
                print(f"  Error deleting {photo.name}: {e}")

        print()
        print(f"✓ Deleted {deleted_count} classified photos")
        if to_keep:
            print(f"✓ Kept {len(to_keep)} unclassified photos in parent directory")
        print(f"  Classified photos remain in: {output_dir}")
    else:
        print("\nAll original photos kept in parent directory")

    print("=" * 60)
    print()


def distribute_photos(output_dir, api_key):
    """Distribute photos into folders based on their names."""
    images = [f for f in output_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and not f.name.startswith('._') and not f.name.startswith('.')]
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
    parser.add_argument('--skip-review', action='store_true',
                       help='Skip manual review prompt (auto-proceed to distribution)')
    parser.add_argument('--classify-only', action='store_true',
                       help='Only classify photos, skip distribution (for manual review later)')
    parser.add_argument('--distribute-only', action='store_true',
                       help='Skip classification, only distribute already-classified photos')

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
    process_folder(args.folder, api_key, args.location, args.skip_review, args.classify_only, args.distribute_only)

if __name__ == "__main__":
    main()
