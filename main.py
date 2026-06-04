import os
import shutil
import argparse
from pathlib import Path
import sys
import re
import requests
import base64
from io import BytesIO
from PIL import Image, ImageTk, ImageEnhance, ImageFilter, ImageDraw, ImageFont
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dotenv import load_dotenv
import threading
from queue import Queue, Empty
import json
import tempfile

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

# Load environment variables from .env file
load_dotenv()

# Try to load saved API key
def load_saved_api_key():
    try:
        with open('api_key.json', 'r') as f:
            data = json.load(f)
            return data.get('api_key', '')
    except (FileNotFoundError, json.JSONDecodeError):
        return ''

# Save API key
def save_api_key(api_key):
    with open('api_key.json', 'w') as f:
        json.dump({'api_key': api_key}, f)

# Progress tracking functions
def load_progress(progress_file):
    """Load progress from a JSON file"""
    try:
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                return json.load(f)
        return {'processed': []}
    except (FileNotFoundError, json.JSONDecodeError):
        return {'processed': []}

def save_progress(progress_file, processed_items):
    """Save progress to a JSON file"""
    try:
        with open(progress_file, 'w') as f:
            json.dump({'processed': processed_items}, f, indent=2)
    except Exception as e:
        print(f"Error saving progress: {e}")

def clear_progress(progress_file):
    """Clear progress file"""
    try:
        if os.path.exists(progress_file):
            os.remove(progress_file)
    except Exception as e:
        print(f"Error clearing progress: {e}")

def encode_image(image_path):
    """Encode image to base64 string."""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_image_mime_type(image_path):
    """Return a Gemini-compatible MIME type for supported image files."""
    suffix = Path(image_path).suffix.lower()
    if suffix == '.png':
        return 'image/png'
    return 'image/jpeg'

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
                "mime_type": get_image_mime_type(image_path),
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

def call_gemini_image_api(api_key, prompt, image_path=None, watermark_path=None, aspect_ratio=None):
    """Make API call to Gemini for image generation/editing."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

    headers = {
        'x-goog-api-key': api_key,
        'Content-Type': 'application/json'
    }

    parts = [{"text": prompt}]

    # Add main image
    if image_path:
        image_data = encode_image(image_path)
        parts.append({
            "inline_data": {
                "mime_type": get_image_mime_type(image_path),
                "data": image_data
            }
        })

    # Add watermark image
    if watermark_path:
        watermark_data = encode_image(watermark_path)
        parts.append({
            "inline_data": {
                "mime_type": get_image_mime_type(watermark_path),
                "data": watermark_data
            }
        })

    generation_config = {
        "responseModalities": ["IMAGE"]
    }
    if aspect_ratio:
        generation_config["imageConfig"] = {
            "aspectRatio": aspect_ratio,
            "imageSize": "1K",
        }

    data = {
        "contents": [{
            "parts": parts
        }],
        "generationConfig": generation_config,
    }

    try:
        print(f"Calling Gemini Image API with prompt length: {len(prompt)}")
        print(f"Sending {len(parts)} parts (text + {len(parts)-1} images)")
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        print(f"Image API Response status: {response.status_code}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Image API Request Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response text: {e.response.text[:500]}")
        raise Exception(f"Image API request failed: {str(e)}")

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
    # Get the original filename without extension
    name = original_path.stem
    # Get the extension
    ext = original_path.suffix
    # Create new filename with bird name as suffix
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
                # Filter out non-alphabet characters (allow apostrophes and hyphens)
                bird_name = re.sub(r'[^a-zA-Z\s\'\-]', '', bird_name).strip()
                if bird_name.lower() == 'n/a':
                    bird_name = None
            elif line.startswith('Is blurred:'):
                is_blurred = "Is blurred: Yes" in line
        return contains_bird, bird_name, is_blurred
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        return False, None, False

def get_location_from_exif(image_path):
    """Extract location from image EXIF data and return a human-readable location."""
    return None
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        if not exif:
            return None
            
        # Get GPS info
        gps_info = {}
        for tag_id in exif:
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                for gps_tag in exif[tag_id]:
                    sub_tag = GPSTAGS.get(gps_tag, gps_tag)
                    gps_info[sub_tag] = exif[tag_id][gps_tag]
        
        if not gps_info:
            return None
            
        # Convert GPS coordinates to decimal degrees
        lat = gps_info.get('GPSLatitude')
        lat_ref = gps_info.get('GPSLatitudeRef')
        lon = gps_info.get('GPSLongitude')
        lon_ref = gps_info.get('GPSLongitudeRef')
        
        if lat and lon:
            lat = float(lat[0] + lat[1]/60 + lat[2]/3600)
            lon = float(lon[0] + lon[1]/60 + lon[2]/3600)
            
            if lat_ref == 'S':
                lat = -lat
            if lon_ref == 'W':
                lon = -lon
                
            # Get location name from coordinates using reverse geocoding
            try:
                import requests
                response = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}")
                if response.status_code == 200:
                    data = response.json()
                    # Extract city, state, and country
                    address = data.get('address', {})
                    city = address.get('city') or address.get('town') or address.get('village')
                    state = address.get('state')
                    country = address.get('country')
                    
                    location_parts = []
                    if city:
                        location_parts.append(city)
                    if state:
                        location_parts.append(state)
                    if country:
                        location_parts.append(country)
                    
                    return " ".join(location_parts) if location_parts else None
            except Exception as e:
                print(f"Error getting location name: {str(e)}")
                
            # If reverse geocoding fails, return coordinates
            return f"{lat:.6f}, {lon:.6f}"
    except Exception as e:
        print(f"Error extracting EXIF location: {str(e)}")
    return None

class BirdClassifierGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Bird Photo Classifier")
        self.root.geometry("800x600")

        # Configure root window grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # API Key frame (common to all tabs)
        api_frame = ttk.Frame(main_frame)
        api_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(api_frame, text="Google API Key:").pack(side=tk.LEFT, padx=5)
        self.api_key_var = tk.StringVar(value=load_saved_api_key())
        self.api_key_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=50, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=5)

        # Create notebook (tabs)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Create Classifier tab
        classifier_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(classifier_frame, text="Classifier")

        # Create Distributor tab
        distributor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(distributor_frame, text="Distributor")

        # Create Editing tab
        editing_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(editing_frame, text="Editing")

        # Configure grid weights for main frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Setup Classifier tab
        self.setup_classifier_tab(classifier_frame)

        # Setup Distributor tab
        self.setup_distributor_tab(distributor_frame)

        # Setup Editing tab
        self.setup_editing_tab(editing_frame)

        # Queue for thread communication
        self.queue = Queue()

        # Store the input directory path
        self.input_dir = None

        # Start GUI update loop
        self.bind_app_scroll_events()
        self.update_gui()

    def setup_classifier_tab(self, parent):
        """Setup the Classifier tab content"""
        # Folder selection
        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(folder_frame, text="Input Folder:").pack(side=tk.LEFT, padx=5)
        self.folder_path = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).pack(side=tk.LEFT, padx=5)

        # Location input
        location_frame = ttk.Frame(parent)
        location_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(location_frame, text="Probable Location:").pack(side=tk.LEFT, padx=5)
        self.location_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.location_var, width=50).pack(side=tk.LEFT, padx=5)

        # Buttons frame
        buttons_frame = ttk.Frame(parent)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        # Start button
        self.start_button = ttk.Button(buttons_frame, text="Start Classification", command=self.start_classification)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Distribute button (initially disabled)
        self.distribute_button = ttk.Button(buttons_frame, text="Distribute into Folders", command=self.distribute_photos, state='disabled')
        self.distribute_button.pack(side=tk.LEFT, padx=5)

        # Progress frame
        progress_frame = ttk.LabelFrame(parent, text="Progress", padding="5")
        progress_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Last processed image frame
        image_frame = ttk.LabelFrame(parent, text="Last Processed Image", padding="5")
        image_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.image_label = ttk.Label(image_frame)
        self.image_label.grid(row=0, column=0, padx=5, pady=5)
        
        # Bird name label
        self.bird_name_label = ttk.Label(image_frame, text="", font=('Arial', 12, 'bold'))
        self.bird_name_label.grid(row=1, column=0, padx=5, pady=5)

        # Configure grid weights for classifier tab
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(4, weight=1)

    def setup_distributor_tab(self, parent):
        """Setup the Distributor tab content"""
        # Input folder selection
        input_frame = ttk.Frame(parent)
        input_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(input_frame, text="Input Folder (from Classifier):").pack(side=tk.LEFT, padx=5)
        self.dist_input_path = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.dist_input_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_dist_input_folder).pack(side=tk.LEFT, padx=5)

        # Output folder selection
        output_frame = ttk.Frame(parent)
        output_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(output_frame, text="Output Folder (organized):").pack(side=tk.LEFT, padx=5)
        self.dist_output_path = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.dist_output_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(output_frame, text="Browse", command=self.browse_dist_output_folder).pack(side=tk.LEFT, padx=5)

        # Buttons frame
        dist_buttons_frame = ttk.Frame(parent)
        dist_buttons_frame.grid(row=2, column=0, columnspan=2, pady=10)

        # Start distribution button
        self.dist_start_button = ttk.Button(dist_buttons_frame, text="Start Distribution", command=self.start_distribution)
        self.dist_start_button.pack(side=tk.LEFT, padx=5)

        # Progress frame
        dist_progress_frame = ttk.LabelFrame(parent, text="Progress", padding="5")
        dist_progress_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.dist_progress_var = tk.DoubleVar()
        self.dist_progress_bar = ttk.Progressbar(dist_progress_frame, variable=self.dist_progress_var, maximum=100)
        self.dist_progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        self.dist_status_label = ttk.Label(dist_progress_frame, text="Ready")
        self.dist_status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Log frame
        log_frame = ttk.LabelFrame(parent, text="Distribution Log", padding="5")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        # Add scrollbar and text widget for logs
        self.dist_log_text = tk.Text(log_frame, height=15, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.dist_log_text.yview)
        self.dist_log_text.configure(yscrollcommand=scrollbar.set)

        self.dist_log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Configure grid weights for distributor tab
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(4, weight=1)

    def setup_editing_tab(self, parent):
        """Setup the Editing tab content"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        scroll_canvas = tk.Canvas(parent, highlightthickness=0)
        scroll_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        v_scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=scroll_canvas.yview)
        h_scrollbar = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=scroll_canvas.xview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        scroll_canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        content = ttk.Frame(scroll_canvas)
        content_window = scroll_canvas.create_window((0, 0), window=content, anchor=tk.NW)

        def update_scroll_region(event=None):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox(tk.ALL))

        def fit_content_width(event):
            scroll_canvas.itemconfigure(content_window, width=max(event.width, content.winfo_reqwidth()))

        content.bind("<Configure>", update_scroll_region)
        scroll_canvas.bind("<Configure>", fit_content_width)
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)

        left_column = ttk.Frame(content, padding=(0, 0, 10, 0))
        left_column.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.E))

        right_column = ttk.Frame(content, padding=(10, 0, 0, 0))
        right_column.grid(row=0, column=1, sticky=(tk.N, tk.EW))
        right_column.columnconfigure(0, weight=1)

        # Image selection frame
        image_frame = ttk.LabelFrame(left_column, text="Image", padding="5")
        image_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        image_frame.columnconfigure(0, weight=1)

        ttk.Label(image_frame, text="Select Image").grid(row=0, column=0, sticky=tk.W, padx=5, pady=(0, 2))
        self.edit_image_path = tk.StringVar()
        self.edit_image_entry = ttk.Entry(image_frame, textvariable=self.edit_image_path, width=50)
        self.edit_image_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Button(image_frame, text="Browse", command=self.browse_edit_image).grid(row=1, column=1, padx=5, pady=2)

        # Bird name input
        bird_name_frame = ttk.LabelFrame(left_column, text="Bird Name", padding="5")
        bird_name_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        bird_name_frame.columnconfigure(0, weight=1)

        ttk.Label(bird_name_frame, text="Bird Name (optional):").pack(side=tk.LEFT, padx=5)
        self.edit_bird_name = tk.StringVar()
        ttk.Entry(bird_name_frame, textvariable=self.edit_bird_name, width=50).pack(side=tk.LEFT, padx=5)

        # Watermark selection (optional)
        watermark_frame = ttk.LabelFrame(left_column, text="Watermark", padding="5")
        watermark_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        watermark_frame.columnconfigure(0, weight=1)

        ttk.Label(watermark_frame, text="Watermark (optional)").grid(row=0, column=0, sticky=tk.W, padx=5, pady=(0, 2))
        self.edit_watermark_path = tk.StringVar()
        ttk.Entry(watermark_frame, textvariable=self.edit_watermark_path, width=50).grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Button(watermark_frame, text="Browse", command=self.browse_watermark_image).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(watermark_frame, text="Clear", command=lambda: self.edit_watermark_path.set("")).grid(row=1, column=2, padx=5, pady=2)

        # Aspect ratio selection
        aspect_frame = ttk.LabelFrame(left_column, text="Aspect Ratio", padding="5")
        aspect_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)

        self.aspect_ratio_var = tk.StringVar(value="square")
        ttk.Radiobutton(aspect_frame, text="Square (1:1)", variable=self.aspect_ratio_var, value="square").grid(row=0, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Radiobutton(aspect_frame, text="Vertical (9x16)", variable=self.aspect_ratio_var, value="vertical").grid(row=1, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Radiobutton(aspect_frame, text="Horizontal (16x9)", variable=self.aspect_ratio_var, value="horizontal").grid(row=2, column=0, sticky=tk.W, padx=8, pady=2)

        # Edit options
        options_frame = ttk.LabelFrame(left_column, text="Edit Options", padding="5")
        options_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)

        self.fix_lighting_color_var = tk.BooleanVar(value=True)
        self.fix_blur_var = tk.BooleanVar(value=False)
        self.focus_on_bird_var = tk.BooleanVar(value=True)
        self.add_bird_name_var = tk.BooleanVar(value=True)
        self.bird_name_text_color_var = tk.StringVar(value="white")
        self.bird_name_text_size_var = tk.StringVar(value="small")
        ttk.Checkbutton(
            options_frame,
            text="Fix lighting and color",
            variable=self.fix_lighting_color_var,
        ).grid(row=0, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Fix blur",
            variable=self.fix_blur_var,
        ).grid(row=1, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Focus on bird",
            variable=self.focus_on_bird_var,
        ).grid(row=2, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Add name",
            variable=self.add_bird_name_var,
        ).grid(row=3, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Label(options_frame, text="Text color").grid(row=4, column=0, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Radiobutton(
            options_frame,
            text="White",
            variable=self.bird_name_text_color_var,
            value="white",
        ).grid(row=5, column=0, sticky=tk.W, padx=18, pady=2)
        ttk.Radiobutton(
            options_frame,
            text="Black",
            variable=self.bird_name_text_color_var,
            value="black",
        ).grid(row=6, column=0, sticky=tk.W, padx=18, pady=2)
        ttk.Label(options_frame, text="Text size").grid(row=7, column=0, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Radiobutton(
            options_frame,
            text="Small",
            variable=self.bird_name_text_size_var,
            value="small",
        ).grid(row=8, column=0, sticky=tk.W, padx=18, pady=2)
        ttk.Radiobutton(
            options_frame,
            text="Medium",
            variable=self.bird_name_text_size_var,
            value="medium",
        ).grid(row=9, column=0, sticky=tk.W, padx=18, pady=2)
        ttk.Radiobutton(
            options_frame,
            text="Large",
            variable=self.bird_name_text_size_var,
            value="large",
        ).grid(row=10, column=0, sticky=tk.W, padx=18, pady=2)

        # Additional instructions and main edit button
        additional_frame = ttk.LabelFrame(left_column, text="Additional editing instructions", padding="5")
        additional_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=5)
        additional_frame.columnconfigure(0, weight=1)

        ttk.Label(additional_frame, text="Additional editing instructions:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=(0, 2))
        self.additional_edit_instructions_text = tk.Text(additional_frame, width=42, height=4, wrap=tk.WORD)
        self.additional_edit_instructions_text.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=2)

        # Main edit button
        edit_button_frame = ttk.Frame(right_column)
        edit_button_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        edit_button_frame.columnconfigure(0, weight=1)

        self.edit_button = ttk.Button(
            edit_button_frame,
            text="Apply AI Editing",
            command=self.apply_ai_edit,
        )
        self.edit_button.grid(row=0, column=1, sticky=tk.E, padx=5)

        # Progress frame
        edit_progress_frame = ttk.LabelFrame(right_column, text="Progress", padding="5")
        edit_progress_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)

        self.edit_progress_var = tk.DoubleVar()
        self.edit_progress_bar = ttk.Progressbar(edit_progress_frame, variable=self.edit_progress_var, maximum=100)
        self.edit_progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        self.edit_status_label = ttk.Label(edit_progress_frame, text="Ready")
        self.edit_status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Fixed-size preview. Double-click opens the full-screen zoomable viewer.
        display_frame = ttk.LabelFrame(right_column, text="Edited Preview", padding="5")
        display_frame.grid(row=1, column=0, sticky=tk.N, pady=5)

        self.preview_width = 240
        self.preview_height = 240
        self.edit_preview_canvas = tk.Canvas(
            display_frame,
            width=self.preview_width,
            height=self.preview_height,
            bg="#222222",
            highlightthickness=0,
        )
        self.edit_preview_canvas.grid(row=0, column=0, padx=5, pady=5)
        self.edit_preview_canvas.create_text(
            self.preview_width // 2,
            self.preview_height // 2,
            text="Edited image preview",
            fill="#dddddd",
        )
        self.edit_preview_canvas.bind("<Double-Button-1>", self.open_fullscreen_preview)

        # Save button
        save_button_frame = ttk.Frame(right_column)
        save_button_frame.grid(row=3, column=0, sticky=tk.W, pady=10)

        self.save_edit_button = ttk.Button(save_button_frame, text="Save Edited Image", command=self.save_edited_image, state='disabled')
        self.save_edit_button.pack(side=tk.LEFT, padx=5)

        left_column.columnconfigure(0, weight=1)

        # Store original and edited images
        self.original_edit_image = None
        self.current_edited_image = None
        self.current_edited_photo = None
        self.current_preview_photo = None
        self.selected_preview_image = None
        self.zoom_level = 1.0
        self.fullscreen_canvas = None
        self.fullscreen_photo = None
        self.fullscreen_image_id = None
        self.fullscreen_viewers = []

        self.setup_edit_drag_and_drop(parent, content)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            # If folder name starts with "0000", use its parent folder
            folder_path = Path(folder)
            if folder_path.name.startswith("0000"):
                folder = str(folder_path.parent)
            
            self.folder_path.set(folder)
            # Enable both start and distribute buttons when folder is selected
            self.start_button.state(['!disabled'])
            self.distribute_button.state(['!disabled'])

    def browse_dist_input_folder(self):
        """Browse for input folder in distributor tab"""
        folder = filedialog.askdirectory()
        if folder:
            self.dist_input_path.set(folder)

    def browse_dist_output_folder(self):
        """Browse for output folder in distributor tab"""
        folder = filedialog.askdirectory()
        if folder:
            self.dist_output_path.set(folder)

    def dist_log(self, message):
        """Add a message to the distributor log"""
        self.dist_log_text.insert(tk.END, message + "\n")
        self.dist_log_text.see(tk.END)

    def update_gui(self):
        """Update GUI elements from the queue"""
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg['type'] == 'progress':
                    self.progress_var.set(msg['value'])
                    self.status_label.config(text=msg['text'])
                elif msg['type'] == 'image':
                    self.image_label.configure(image=msg['image'])
                    self.bird_name_label.config(text=msg['text'])
                elif msg['type'] == 'error':
                    messagebox.showerror("Error", msg['text'])
                    self.start_button.state(['!disabled'])
                elif msg['type'] == 'messagebox_info':
                    messagebox.showinfo(msg.get('title', 'Info'), msg['text'])
                elif msg['type'] == 'messagebox_error':
                    messagebox.showerror(msg.get('title', 'Error'), msg['text'])
                elif msg['type'] == 'dist_progress':
                    self.dist_progress_var.set(msg['value'])
                    self.dist_status_label.config(text=msg['text'])
                elif msg['type'] == 'dist_log':
                    self.dist_log(msg['text'])
                elif msg['type'] == 'edit_progress':
                    self.edit_progress_var.set(msg['value'])
                    self.edit_status_label.config(text=msg['text'])
                elif msg['type'] == 'edit_image':
                    self.update_edited_image_display()
                elif msg['type'] == 'edit_button_ready':
                    self.edit_button.state(['!disabled'])
                elif msg['type'] == 'edit_complete':
                    self.save_edit_button.state(['!disabled'])
                    self.edit_button.state(['!disabled'])
        except Empty:
            pass
        finally:
            self.root.after(100, self.update_gui)

    def reset_editing_context(self):
        """Reset all editing context when a new image is selected"""
        # Clear all stored images
        self.original_edit_image = None
        self.current_edited_image = None
        self.current_edited_photo = None
        self.current_preview_photo = None
        self.selected_preview_image = None
        self._last_api_text_response = None

        # Reset zoom
        self.zoom_level = 1.0

        self.edit_preview_canvas.delete(tk.ALL)
        self.edit_preview_canvas.create_text(
            self.preview_width // 2,
            self.preview_height // 2,
            text="Edited image preview",
            fill="#dddddd",
        )

        # Reset progress
        self.edit_progress_var.set(0)
        self.edit_status_label.config(text="Ready")

        # Disable save button
        self.save_edit_button.state(['disabled'])

        # Clear additional instructions
        self.additional_edit_instructions_text.delete("1.0", tk.END)

    def show_selected_image_preview(self, image_path):
        """Load and display the selected source image in the preview area."""
        try:
            with Image.open(image_path) as image:
                self.selected_preview_image = image.copy()
            self.original_edit_image = self.selected_preview_image.copy()
            self.update_preview_display(self.selected_preview_image, "Original image selected")
        except Exception as e:
            self.selected_preview_image = None
            self.original_edit_image = None
            self.edit_status_label.config(text=f"Could not preview selected image: {e}")

    def zoom_in(self):
        """Zoom in on the edited image"""
        if self.current_edited_image:
            self.zoom_level *= 1.25
            self.update_fullscreen_image_display()

    def zoom_out(self):
        """Zoom out on the edited image"""
        if self.current_edited_image:
            self.zoom_level /= 1.25
            self.update_fullscreen_image_display()

    def zoom_reset(self):
        """Reset zoom to 100%"""
        if self.current_edited_image:
            self.zoom_level = 1.0
            self.update_fullscreen_image_display()

    def update_edited_image_display(self):
        """Update the fixed in-tab preview."""
        if not self.current_edited_image:
            return

        self.update_preview_display(self.current_edited_image, "Double-click for split screen")

    def update_preview_display(self, image, footer_text):
        """Update the in-tab preview with the supplied image."""
        width, height = image.size
        scale = min(self.preview_width / width, self.preview_height / height)
        preview_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        display_image = image.resize(preview_size, Image.Resampling.LANCZOS)
        self.current_preview_photo = ImageTk.PhotoImage(display_image)

        self.edit_preview_canvas.delete(tk.ALL)
        x = (self.preview_width - preview_size[0]) // 2
        y = (self.preview_height - preview_size[1]) // 2
        self.edit_preview_canvas.create_image(x, y, anchor=tk.NW, image=self.current_preview_photo)
        self.edit_preview_canvas.create_text(
            self.preview_width // 2,
            self.preview_height - 16,
            text=footer_text,
            fill="#ffffff",
        )

    def update_fullscreen_image_display(self):
        """Update the full-screen viewer image(s) at the current zoom level."""
        if not self.current_edited_image:
            return

        if self.fullscreen_viewers:
            for viewer_state in self.fullscreen_viewers:
                self.update_fullscreen_viewer_image(viewer_state)
            return

        if self.fullscreen_canvas:
            self.fullscreen_viewers = [{
                'canvas': self.fullscreen_canvas,
                'image': self.current_edited_image,
                'zoom_level': self.zoom_level,
                'photo': None,
                'image_id': None,
            }]
            self.update_fullscreen_viewer_image(self.fullscreen_viewers[0])

    def update_fullscreen_viewer_image(self, viewer_state):
        image = viewer_state['image']
        canvas = viewer_state['canvas']
        zoom_level = viewer_state.get('zoom_level', self.zoom_level)
        width, height = image.size
        new_width = max(1, int(width * zoom_level))
        new_height = max(1, int(height * zoom_level))
        display_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        viewer_state['photo'] = ImageTk.PhotoImage(display_image)

        if viewer_state.get('image_id'):
            canvas.delete(viewer_state['image_id'])

        viewer_state['image_id'] = canvas.create_image(0, 0, anchor=tk.NW, image=viewer_state['photo'])
        canvas.config(scrollregion=canvas.bbox(tk.ALL))

    def open_fullscreen_preview(self, event=None):
        """Open a full-screen split viewer for original and edited images."""
        if not self.current_edited_image or not self.original_edit_image:
            return

        viewer = tk.Toplevel(self.root)
        viewer.title("Edited Image Preview")
        viewer.attributes("-fullscreen", True)
        viewer.bind("<Escape>", lambda event: viewer.destroy())

        toolbar = ttk.Frame(viewer)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="Close", command=viewer.destroy).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(toolbar, text="Original and edited images. Each side has independent zoom and scroll. Esc closes.").pack(side=tk.LEFT, padx=10)

        split_frame = ttk.Frame(viewer)
        split_frame.pack(fill=tk.BOTH, expand=True)
        split_frame.columnconfigure(0, weight=1, uniform="preview")
        split_frame.columnconfigure(1, weight=1, uniform="preview")
        split_frame.rowconfigure(0, weight=1)

        self.fullscreen_viewers = []
        original_image = self.original_edit_image.copy()
        edited_image = self.current_edited_image.copy()
        self.create_split_viewer_panel(split_frame, "Original", original_image, 0)
        self.create_split_viewer_panel(split_frame, "Edited", edited_image, 1)

        self.fullscreen_canvas = self.fullscreen_viewers[0]['canvas']
        self.zoom_level = 1.0
        self.update_fullscreen_image_display()
        self.fullscreen_canvas.focus_set()

        def cleanup(event=None):
            self.fullscreen_canvas = None
            self.fullscreen_photo = None
            self.fullscreen_image_id = None
            self.fullscreen_viewers = []

        viewer.bind("<Destroy>", cleanup)

    def create_split_viewer_panel(self, parent, title, image, column):
        panel = ttk.LabelFrame(parent, text=title, padding="5")
        panel.grid(row=0, column=column, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        controls = ttk.Frame(panel)
        controls.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Label(controls, text=title).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="-", width=3, command=lambda: self.zoom_viewer(canvas, 1 / 1.25)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="+", width=3, command=lambda: self.zoom_viewer(canvas, 1.25)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Reset", command=lambda: self.reset_viewer_zoom(canvas)).pack(side=tk.LEFT, padx=5)

        h_scrollbar = ttk.Scrollbar(panel, orient=tk.HORIZONTAL)
        v_scrollbar = ttk.Scrollbar(panel, orient=tk.VERTICAL)
        canvas = tk.Canvas(
            panel,
            bg="#111111",
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set,
        )
        h_scrollbar.config(command=canvas.xview)
        v_scrollbar.config(command=canvas.yview)

        canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        h_scrollbar.grid(row=2, column=0, sticky=(tk.W, tk.E))
        v_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))

        canvas.bind("<MouseWheel>", self.on_fullscreen_mousewheel)
        canvas.bind("<Shift-MouseWheel>", self.on_fullscreen_shift_mousewheel)
        canvas.bind("<Option-MouseWheel>", self.on_fullscreen_shift_mousewheel)
        canvas.bind("<Command-MouseWheel>", self.on_fullscreen_shift_mousewheel)
        canvas.bind("<Control-MouseWheel>", self.on_fullscreen_zoom_wheel)
        canvas.bind("<Button-4>", self.on_fullscreen_scroll_up)
        canvas.bind("<Button-5>", self.on_fullscreen_scroll_down)
        self.bind_if_supported(canvas, "<Button-6>", self.on_fullscreen_scroll_left)
        self.bind_if_supported(canvas, "<Button-7>", self.on_fullscreen_scroll_right)
        try:
            canvas.bind("<Magnify>", self.on_fullscreen_magnify)
        except tk.TclError:
            pass

        self.fullscreen_viewers.append({
            'canvas': canvas,
            'image': image,
            'zoom_level': 1.0,
            'photo': None,
            'image_id': None,
        })

    def bind_if_supported(self, widget, sequence, callback):
        try:
            widget.bind(sequence, callback)
        except tk.TclError:
            pass

    def get_viewer_state_for_canvas(self, canvas):
        for viewer_state in self.fullscreen_viewers:
            if viewer_state.get('canvas') is canvas:
                return viewer_state
        return None

    def zoom_viewer(self, canvas, factor):
        viewer_state = self.get_viewer_state_for_canvas(canvas)
        if not viewer_state:
            return

        viewer_state['zoom_level'] = max(0.05, viewer_state.get('zoom_level', 1.0) * factor)
        self.update_fullscreen_viewer_image(viewer_state)

    def reset_viewer_zoom(self, canvas):
        viewer_state = self.get_viewer_state_for_canvas(canvas)
        if not viewer_state:
            return

        viewer_state['zoom_level'] = 1.0
        self.update_fullscreen_viewer_image(viewer_state)

    def on_fullscreen_mousewheel(self, event):
        if event.widget:
            horizontal = self.is_horizontal_scroll_event(event)
            self.smooth_scroll_canvas(event.widget, -event.delta, horizontal=horizontal)
        return "break"

    def on_fullscreen_shift_mousewheel(self, event):
        if event.widget:
            self.smooth_scroll_canvas(event.widget, -event.delta, horizontal=True)
        return "break"

    def on_fullscreen_scroll_up(self, event):
        if event.widget:
            self.smooth_scroll_canvas(event.widget, -120, horizontal=False)
        return "break"

    def on_fullscreen_scroll_down(self, event):
        if event.widget:
            self.smooth_scroll_canvas(event.widget, 120, horizontal=False)
        return "break"

    def on_fullscreen_scroll_left(self, event):
        if event.widget:
            self.smooth_scroll_canvas(event.widget, -120, horizontal=True)
        return "break"

    def on_fullscreen_scroll_right(self, event):
        if event.widget:
            self.smooth_scroll_canvas(event.widget, 120, horizontal=True)
        return "break"

    def smooth_scroll_canvas(self, canvas, delta, horizontal=False):
        bbox = canvas.bbox(tk.ALL)
        if not bbox:
            return

        visible_size = canvas.winfo_width() if horizontal else canvas.winfo_height()
        content_size = (bbox[2] - bbox[0]) if horizontal else (bbox[3] - bbox[1])
        if content_size <= visible_size:
            return

        view = canvas.xview() if horizontal else canvas.yview()
        scrollable = max(1, content_size - visible_size)
        current_offset = view[0] * content_size
        next_offset = min(max(0, current_offset + delta), scrollable)
        fraction = next_offset / content_size

        if horizontal:
            canvas.xview_moveto(fraction)
        else:
            canvas.yview_moveto(fraction)

    def on_fullscreen_zoom_wheel(self, event):
        if event.delta > 0:
            self.zoom_viewer(event.widget, 1.25)
        else:
            self.zoom_viewer(event.widget, 1 / 1.25)
        return "break"

    def on_fullscreen_magnify(self, event):
        self.zoom_viewer(event.widget, max(0.2, 1.0 + event.delta))
        return "break"

    def is_horizontal_scroll_event(self, event):
        # Tk modifier masks vary by platform/theme; these cover Shift, Mod1/Option, and Command/Mod2 paths.
        horizontal_masks = (0x0001, 0x0008, 0x0010, 0x0080, 0x20000)
        return any(event.state & mask for mask in horizontal_masks)

    def bind_app_scroll_events(self):
        """Make two-finger/mouse-wheel scrolling work across scrollable app areas."""
        self.bind_all_if_supported("<MouseWheel>", self.on_app_mousewheel)
        self.bind_all_if_supported("<Shift-MouseWheel>", self.on_app_shift_mousewheel)
        self.bind_all_if_supported("<Button-4>", self.on_app_scroll_up)
        self.bind_all_if_supported("<Button-5>", self.on_app_scroll_down)
        self.bind_all_if_supported("<Button-6>", self.on_app_scroll_left)
        self.bind_all_if_supported("<Button-7>", self.on_app_scroll_right)

    def bind_all_if_supported(self, sequence, callback):
        try:
            self.root.bind_all(sequence, callback, add="+")
        except tk.TclError:
            pass

    def find_scrollable_widget(self, widget, horizontal=False):
        """Find the nearest ancestor that can scroll in the requested direction."""
        while widget:
            if widget is self.edit_preview_canvas:
                widget = widget.master
                continue

            view_method = "xview" if horizontal else "yview"
            if hasattr(widget, view_method):
                return widget
            widget = getattr(widget, "master", None)
        return None

    def scroll_widget(self, widget, amount, horizontal=False):
        if not widget:
            return

        if horizontal and hasattr(widget, "xview_scroll"):
            widget.xview_scroll(amount, "units")
        elif not horizontal and hasattr(widget, "yview_scroll"):
            widget.yview_scroll(amount, "units")

    def on_app_mousewheel(self, event):
        if event.state & 0x0004:
            return
        if isinstance(event.widget, tk.Text):
            return

        horizontal = self.is_horizontal_scroll_event(event)
        widget = self.find_scrollable_widget(event.widget, horizontal=horizontal)
        self.scroll_widget(widget, int(-1 * (event.delta / 120)), horizontal=horizontal)

    def on_app_shift_mousewheel(self, event):
        if isinstance(event.widget, tk.Text):
            return

        widget = self.find_scrollable_widget(event.widget, horizontal=True)
        self.scroll_widget(widget, int(-1 * (event.delta / 120)), horizontal=True)

    def on_app_scroll_up(self, event):
        if isinstance(event.widget, tk.Text):
            return

        widget = self.find_scrollable_widget(event.widget)
        self.scroll_widget(widget, -3)

    def on_app_scroll_down(self, event):
        if isinstance(event.widget, tk.Text):
            return

        widget = self.find_scrollable_widget(event.widget)
        self.scroll_widget(widget, 3)

    def on_app_scroll_left(self, event):
        widget = self.find_scrollable_widget(event.widget, horizontal=True)
        self.scroll_widget(widget, -3, horizontal=True)

    def on_app_scroll_right(self, event):
        widget = self.find_scrollable_widget(event.widget, horizontal=True)
        self.scroll_widget(widget, 3, horizontal=True)

    def setup_edit_drag_and_drop(self, parent, content):
        """Enable OS file drops on the Editing tab when tkinterdnd2 is available."""
        if DND_FILES is None or not hasattr(parent, "drop_target_register"):
            return

        for widget in (parent, content, self.edit_image_entry, self.edit_preview_canvas):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_edit_image_drop)

    def on_edit_image_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        for path in paths:
            if self.set_edit_image_path(path):
                return "break"
        messagebox.showerror("Error", "Drop a JPG, JPEG, or PNG image file")
        return "break"

    def set_edit_image_path(self, file_path):
        """Select an image for editing and reset derived state."""
        path = Path(file_path)
        if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
            return False

        self.edit_image_path.set(str(path))
        self.reset_editing_context()
        self.show_selected_image_preview(path)
        return True

    def browse_edit_image(self):
        """Browse for image to edit"""
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("All files", "*.*")]
        )
        if file_path:
            self.set_edit_image_path(file_path)

    def browse_watermark_image(self):
        """Browse for an optional watermark image."""
        file_path = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("All files", "*.*")]
        )
        if file_path:
            self.edit_watermark_path.set(file_path)

    def apply_ai_edit(self):
        """Apply AI-guided editing to the image"""
        image_path = self.edit_image_path.get()
        if not image_path:
            messagebox.showerror("Error", "Please select an image first")
            return

        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your Google API Key")
            return

        # Disable button and reset progress
        self.edit_button.state(['disabled'])
        self.edit_progress_var.set(0)
        self.edit_status_label.config(text="Starting AI editing...")
        additional_instructions = self.additional_edit_instructions_text.get("1.0", tk.END).strip()

        # Start editing in a separate thread
        thread = threading.Thread(
            target=self._perform_ai_edit,
            args=(
                image_path,
                api_key,
                additional_instructions,
                self.aspect_ratio_var.get(),
                self.edit_bird_name.get().strip(),
                self.edit_watermark_path.get().strip(),
                self.get_edit_options(),
            ),
        )
        thread.daemon = True
        thread.start()

    def save_edited_image(self):
        """Save the edited image"""
        if not self.current_edited_image:
            messagebox.showerror("Error", "No edited image to save")
            return

        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            title="Save Edited Image",
            defaultextension=".jpg",
            filetypes=[("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("All files", "*.*")]
        )

        if file_path:
            try:
                if Path(file_path).suffix.lower() == '.png':
                    self.current_edited_image.save(file_path, format='PNG')
                else:
                    self.current_edited_image.convert('RGB').save(file_path, format='JPEG', quality=95)
                messagebox.showinfo("Success", f"Image saved to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image: {str(e)}")

    def get_edit_options(self):
        return {
            'fix_lighting_color': self.fix_lighting_color_var.get(),
            'fix_blur': self.fix_blur_var.get(),
            'focus_on_bird': self.focus_on_bird_var.get(),
            'add_bird_name': self.add_bird_name_var.get(),
            'bird_name_text_color': self.bird_name_text_color_var.get(),
            'bird_name_text_size': self.bird_name_text_size_var.get(),
        }

    def _perform_ai_edit(self, image_path, api_key, modification=None, aspect_ratio='square', bird_name='', user_watermark='', edit_options=None):
        """Perform AI-guided editing in background thread"""
        temp_path = None
        try:
            edit_options = edit_options or {}
            # Load original image if not already loaded
            if not self.original_edit_image:
                self.queue.put({'type': 'edit_progress', 'value': 10, 'text': 'Loading image...'})
                self.original_edit_image = Image.open(image_path)

            self.queue.put({'type': 'edit_progress', 'value': 20, 'text': 'Sending to AI for editing...'})

            # Save image to temp file for API without losing PNG support.
            input_suffix = Path(image_path).suffix.lower()
            if input_suffix == '.png':
                temp_suffix = '.png'
                temp_format = 'PNG'
                upload_image = self.original_edit_image
            else:
                temp_suffix = '.jpg'
                temp_format = 'JPEG'
                upload_image = self.original_edit_image.convert('RGB')

            with tempfile.NamedTemporaryFile(suffix=temp_suffix, delete=False) as tmp:
                if temp_format == 'JPEG':
                    upload_image.save(tmp.name, format=temp_format, quality=95)
                else:
                    upload_image.save(tmp.name, format=temp_format)
                temp_path = tmp.name

            # Resolve watermark: user-selected first, then default watermark.jpg
            if user_watermark:
                watermark_path = Path(user_watermark)
            else:
                watermark_path = Path('watermark.jpg')
            watermark_exists = watermark_path.exists()

            # Create prompt for AI
            watermark_instruction = """
- Place the watermark image (second image) in the BOTTOM RIGHT corner
- Make the watermark VERY SMALL (approximately 5% of the image width)
- Remove the background from the watermark, make it transparent
- The watermark should be subtle and not distract from the bird""" if watermark_exists else ""

            aspect_specs = {
                'square': ('SQUARE', '1:1 aspect ratio'),
                'vertical': ('VERTICAL', '9:16 aspect ratio (portrait, taller than wide)'),
                'horizontal': ('HORIZONTAL', '16:9 aspect ratio (landscape, wider than tall)'),
            }
            aspect_label, aspect_desc = aspect_specs[aspect_ratio]
            api_aspect_ratio = {
                'square': '1:1',
                'vertical': '9:16',
                'horizontal': '16:9',
            }[aspect_ratio]

            edit_instructions = []
            if edit_options.get('fix_lighting_color'):
                edit_instructions.append(
                    "- Fix lighting, exposure, white balance, color profile, contrast, and tone so the photograph looks professionally finished in the style of a National Geographic bird photographer."
                )
            if edit_options.get('fix_blur'):
                edit_instructions.append(
                    "- If the bird is blurred, soft, out of focus, or affected by motion blur, reduce blur and improve sharpness/detail on the bird only as a photographer would. Correct motion blur only where existing edges and details are visible. Never change the bird's pose, silhouette, anatomy, expression, eye shape, beak shape, feather layout, wing position, leg position, or feet. Do not invent new feather patterns, anatomy, pose, eyes, beak, legs, or background details."
                )
            if edit_options.get('focus_on_bird'):
                edit_instructions.append(
                    "- Reframe only through crop, zoom, and pan so the bird is prominent and centered in the frame with a strong wildlife-photography composition."
                )
            if modification:
                edit_instructions.append(
                    "- Apply these additional user-requested editing instructions only if they can be done as photographer-style edits without changing the pose, features, anatomy, objects, background elements, or factual content of the photo. These additional instructions must never override the critical requirements below: "
                    f"{modification}"
                )
            if not edit_instructions:
                edit_instructions.append("- Make no aesthetic corrections beyond preserving the requested aspect ratio and any watermark placement.")

            selected_edits = "\n".join(edit_instructions)
            prompt = f"""Edit this bird photograph using ONLY the requested corrections below.

REQUESTED CORRECTIONS:
{selected_edits}

CRITICAL REQUIREMENTS:
- Make the output a {aspect_label} image ({aspect_desc}) - VERY IMPORTANT
- This must remain the same photograph. Do not make meaningful content changes. Only make photographer-style edits similar to Lightroom/Photoshop adjustments.
- Preserve the original photograph. Do not replace the bird, do not generate a new bird, and do not synthesize a different scene.
- Keep the exact same bird species, pose, silhouette, anatomy, body proportions, expression, eye shape, beak shape, feather layout, plumage markings, wing position, leg position, feet, surroundings, background, and lighting direction unless a selected correction requires a subtle photographic adjustment.
- Never change the pose or features of the bird. The bird must not look like a different individual, a cleaner/generated version, or a species-reference reconstruction.
- Do not add or remove objects, branches, leaves, watermarks, text, birds, body parts, or background elements, except for the requested watermark if provided.
- Be extremely strict about not inventing image content. Do not hallucinate, fabricate, reconstruct, guess, or add any detail that is not already visibly present in the source image.
- Do not create new feather barbs, feather patterns, eye catchlights, beak edges, claws, legs, wing outlines, branch texture, leaf texture, background texture, bokeh, shadows, highlights, or scenery that are not already present.
- For blur or motion-blur correction, only improve clarity of existing visible pixels and edges. If a detail is not visible enough to recover from the source image, leave it soft rather than inventing it.
- Sharpening must be conservative and photographic, not generative. Do not use external knowledge of what this species should look like to add missing detail or alter visible features.
- Use only non-destructive photographic edits: crop, zoom, pan, exposure, color, contrast, white balance, sharpening, and blur reduction when requested. No relighting, repainting, generative cleanup, denoising that changes texture, or content-aware fill.
- If an edit option is not requested, leave that aspect of the photo unchanged.{watermark_instruction}

Create a {aspect_label} edited version of this exact image following these requirements."""

            self.queue.put({'type': 'edit_progress', 'value': 40, 'text': 'AI is processing the image...'})

            # Call Gemini image API with watermark if it exists
            if watermark_exists:
                response = call_gemini_image_api(api_key, prompt, temp_path, str(watermark_path), api_aspect_ratio)
            else:
                response = call_gemini_image_api(api_key, prompt, temp_path, aspect_ratio=api_aspect_ratio)

            self.queue.put({'type': 'edit_progress', 'value': 70, 'text': 'Extracting edited image...'})

            # Extract the image from response
            edited_image = self._extract_image_from_response(response)

            if not edited_image:
                error_msg = "No image was returned by the AI."
                if hasattr(self, '_last_api_text_response') and self._last_api_text_response:
                    error_msg += f"\n\nAPI Response: {self._last_api_text_response[:300]}"
                else:
                    error_msg += " The API may not support image editing yet, or it may have filtered the request."
                raise Exception(error_msg)

            self.queue.put({'type': 'edit_progress', 'value': 90, 'text': f'Finalizing and ensuring {aspect_ratio} output...'})

            # Ensure the image matches the requested aspect ratio
            edited_image = self._ensure_aspect_ratio(edited_image, aspect_ratio)
            if edit_options.get('add_bird_name'):
                edited_image = self._add_bird_name_label(
                    edited_image,
                    bird_name,
                    edit_options.get('bird_name_text_color', 'white'),
                    edit_options.get('bird_name_text_size', 'small'),
                )

            # Store the edited image
            self.current_edited_image = edited_image

            # Notify that image is ready for display
            self.queue.put({'type': 'edit_image'})
            self.queue.put({'type': 'edit_progress', 'value': 100, 'text': 'Editing complete!'})
            self.queue.put({'type': 'edit_complete'})

        except Exception as e:
            self.queue.put({
                'type': 'messagebox_error',
                'title': 'Error',
                'text': f"Error during editing: {str(e)}"
            })
            print(f"Error during AI editing: {str(e)}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            self.queue.put({'type': 'edit_button_ready'})

    def _add_bird_name_label(self, image, bird_name, text_color, text_size):
        """Draw the optional bird name top-right with capped Lexend Giga text height."""
        if not bird_name:
            return image

        text_color = 'black' if text_color == 'black' else 'white'
        size_multiplier = {
            'small': 1,
            'medium': 2,
            'large': 3,
        }.get(text_size, 1)
        output = image.convert("RGBA")
        draw = ImageDraw.Draw(output)
        width, height = output.size
        max_text_height = max(1, int(height * 0.05 * size_multiplier))
        horizontal_padding = max(12, int(width * 0.04))
        max_text_width = width - (horizontal_padding * 2)

        font = self._load_overlay_font(max_text_height)
        while font.size > 8:
            bbox = draw.textbbox((0, 0), bird_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width <= max_text_width and text_height <= max_text_height:
                break
            font = self._load_overlay_font(font.size - 1)

        bbox = draw.textbbox((0, 0), bird_name, font=font)
        text_width = bbox[2] - bbox[0]
        x = max(4, width - text_width - horizontal_padding)
        y = max(4, int(height * 0.025))

        draw.text(
            (x, y - bbox[1]),
            bird_name,
            font=font,
            fill=text_color,
        )
        return output.convert(image.mode if image.mode in ("RGB", "RGBA") else "RGB")

    def _load_overlay_font(self, size):
        """Load Lexend Giga when available, with safe fallbacks."""
        font_paths = [
            "/usr/share/fonts/truetype/lexend/LexendGiga-Regular.ttf",
            "/usr/share/fonts/truetype/lexend-giga/LexendGiga-Regular.ttf",
            "/usr/share/fonts/truetype/google-fonts/LexendGiga-Regular.ttf",
            "/Library/Fonts/LexendGiga-Regular.ttf",
            "C:/Windows/Fonts/LexendGiga-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/Library/Fonts/NotoSans-Regular.ttf",
            "C:/Windows/Fonts/NotoSans-Regular.ttf",
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size=size)

        try:
            return ImageFont.truetype("LexendGiga-Regular.ttf", size=size)
        except OSError:
            pass

        try:
            return ImageFont.truetype("NotoSans-Regular.ttf", size=size)
        except OSError:
            return ImageFont.load_default(size=size)

    def _extract_image_from_response(self, response):
        """Extract image data from Gemini API response"""
        try:
            # Debug: Print response structure
            print(f"API Response keys: {response.keys()}")

            # The response structure may contain image data in different formats
            # Check for inline_data in parts
            candidates = response.get('candidates', [])
            if not candidates:
                print("No candidates in response")
                # Print full response for debugging
                print(f"Full response: {json.dumps(response, indent=2)}")
                return None

            for i, candidate in enumerate(candidates):
                print(f"Candidate {i}: {candidate.keys()}")
                content = candidate.get('content', {})
                parts = content.get('parts', [])
                print(f"Number of parts: {len(parts)}")

                for j, part in enumerate(parts):
                    print(f"Part {j} keys: {part.keys()}")

                    # Check if API returned text instead of image
                    if 'text' in part:
                        text_response = part['text']
                        print(f"API returned text instead of image: {text_response[:200]}")
                        # Store this for better error message
                        self._last_api_text_response = text_response

                    # Check for inline_data with image
                    if 'inline_data' in part:
                        inline_data = part['inline_data']
                        if 'data' in inline_data:
                            print("Found image data in inline_data")
                            # Decode base64 image
                            image_data = base64.b64decode(inline_data['data'])
                            # Convert to PIL Image
                            image = Image.open(BytesIO(image_data))
                            return image
                    # Also check for inlineData (camelCase)
                    elif 'inlineData' in part:
                        inline_data = part['inlineData']
                        if 'data' in inline_data:
                            print("Found image data in inlineData")
                            # Decode base64 image
                            image_data = base64.b64decode(inline_data['data'])
                            # Convert to PIL Image
                            image = Image.open(BytesIO(image_data))
                            return image

            print("No image found in response")
            print(f"Full response for debugging: {json.dumps(response, indent=2)}")
            return None

        except Exception as e:
            print(f"Error extracting image from response: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _ensure_aspect_ratio(self, image, aspect_ratio):
        """Center-crop the image to the requested aspect ratio."""
        width, height = image.size
        print(f"Image dimensions: {width}x{height}, target: {aspect_ratio}")

        ratios = {
            'square': (1, 1),
            'vertical': (9, 16),
            'horizontal': (16, 9),
        }
        target_w, target_h = ratios[aspect_ratio]
        target = target_w / target_h
        current = width / height

        if abs(current - target) < 1e-3:
            print(f"Image already matches {aspect_ratio} ratio")
            return image

        if current > target:
            # Too wide — crop width
            new_width = int(round(height * target))
            left = (width - new_width) // 2
            box = (left, 0, left + new_width, height)
        else:
            # Too tall — crop height
            new_height = int(round(width / target))
            top = (height - new_height) // 2
            box = (0, top, width, top + new_height)

        print(f"Cropping to {aspect_ratio}: {box[2]-box[0]}x{box[3]-box[1]}")
        return image.crop(box)

    def start_classification(self):
        # Save API key
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your Google API Key")
            return
        save_api_key(api_key)
        
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("Error", "Please select an input folder")
            return
        
        self.start_button.state(['disabled'])
        self.progress_var.set(0)
        self.status_label.config(text="Starting classification...")

        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_photos, args=(folder, api_key))
        thread.daemon = True
        thread.start()
    
    def distribute_photos(self):
        self.input_dir = Path(self.folder_path.get())
        """Distribute photos into folders based on their names."""
        if not self.input_dir:
            messagebox.showerror("Error", "Please select an input folder first")
            return
            
        # Reset progress bar
        self.progress_var.set(0)
        self.status_label.config(text="Starting distribution...")
        
        # Disable the distribute button while processing
        self.distribute_button.state(['disabled'])

        # Start processing in a separate thread
        thread = threading.Thread(target=self._distribute_photos_thread)
        thread.daemon = True
        thread.start()
    
    def _distribute_photos_thread(self):
        """Thread function for distributing photos."""
        try:
            # Create output directory
            output_dir = self.input_dir / f'0000-{self.input_dir.name}'
            output_dir.mkdir(exist_ok=True)

            # Progress file path
            progress_file = output_dir / '.distribute-into-folders.progress'

            # Load progress
            progress_data = load_progress(str(progress_file))
            processed_images = set(progress_data.get('processed', []))

            # Get all image files (skip macOS metadata files)
            images = [f for f in output_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and not f.name.startswith('._') and not f.name.startswith('.')]
            total_images = len(images)

            if total_images == 0:
                self.queue.put({
                    'type': 'error',
                    'text': "No images found to distribute"
                })
                return

            # Get API key for bird info
            api_key = self.api_key_var.get().strip()

            # Track unique birds for progress
            unique_birds = set()

            for i, image_path in enumerate(images, 1):
                # Update progress (including skipped items)
                progress = (i / total_images) * 100

                # Skip if already processed
                if image_path.name in processed_images:
                    self.queue.put({
                        'type': 'progress',
                        'value': progress,
                        'text': f"Skipping already distributed {i}/{total_images}: {image_path.name}"
                    })
                    continue

                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Processing image {i} of {total_images}: {image_path.name}"
                })

                # Extract bird name from filename using AI
                bird_name = self.extract_bird_name_from_filename(image_path.stem, api_key)

                # Skip if bird is unidentified or if there's no bird name
                if not bird_name or bird_name.lower() == "unidentified":
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
                    self.queue.put({
                        'type': 'progress',
                        'value': progress,
                        'text': f"Creating info file for {bird_name}..."
                    })
                    # Get bird information
                    info_text = get_bird_info(bird_name, api_key)
                    if info_text:
                        create_bird_info_file(bird_folder, bird_name, info_text)
                        self.queue.put({
                            'type': 'progress',
                            'value': progress,
                            'text': f"Created info file for {bird_name}"
                        })

                # Mark image as processed and save progress
                processed_images.add(image_path.name)
                save_progress(str(progress_file), list(processed_images))

            # Clear progress file after successful completion
            clear_progress(str(progress_file))

            # Update final status with summary
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': f"Distribution completed! Organized {len(unique_birds)} unique bird species."
            })

            # Use queue to show messagebox from main thread
            self.queue.put({
                'type': 'messagebox_info',
                'title': 'Success',
                'text': f"Photos have been distributed into folders!\nOrganized {len(unique_birds)} unique bird species."
            })

        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error during distribution: {str(e)}"
            })
        finally:
            # Re-enable the distribute button
            self.distribute_button.state(['!disabled'])

    def process_photos(self, input_folder, api_key):
        """Process photos from the input folder."""
        try:
            # Store input directory for later use
            self.input_dir = Path(input_folder)

            if not self.input_dir.exists():
                self.queue.put({
                    'type': 'error',
                    'text': f"Input folder '{input_folder}' does not exist"
                })
                return

            # Create output directory
            output_dir = self.input_dir / f'0000-{self.input_dir.name}'
            output_dir.mkdir(exist_ok=True)

            # Progress file path
            progress_file = self.input_dir / '.classifier.progress'

            # Load progress
            progress_data = load_progress(str(progress_file))
            processed_images = set(progress_data.get('processed', []))

            # Get list of images (skip macOS metadata files starting with ._ )
            images = [f for f in self.input_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and not f.name.startswith('._') and not f.name.startswith('.')]
            total_images = len(images)
            loaded_birds = ["None"]

            # Get user's probable location
            user_location = self.location_var.get().strip()
            if user_location:
                user_location = f"Probably {user_location}"

            for i, image_path in enumerate(images, 1):
                # Update progress (including skipped items)
                progress = (i / total_images) * 100

                # Skip if already processed
                if image_path.name in processed_images:
                    self.queue.put({
                        'type': 'progress',
                        'value': progress,
                        'text': f"Skipping already processed {i}/{total_images}: {image_path.name}"
                    })
                    continue

                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Processing image {i} of {total_images}: {image_path.name}"
                })

                # Get location from EXIF data or use user's input
                location = get_location_from_exif(image_path)
                if not location and user_location:
                    location = user_location
                
                # Process image
                contains_bird, bird_name, is_blurred = identify_bird(image_path, api_key, loaded_birds, location)
                # Update last processed image
                img = Image.open(image_path)
                # Resize image to fit GUI
                img.thumbnail((400, 400))
                photo = ImageTk.PhotoImage(img)
                status_text = f"Bird: {bird_name if bird_name else 'Unidentified'}"
                if is_blurred:
                    status_text += " (Blurred)"
                if location:
                    status_text += f" ({location})"
                self.queue.put({
                    'type': 'image',
                    'image': photo,
                    'text': status_text
                })
                
                if bird_name and bird_name != "NA" and bird_name != "N/A" and bird_name != "Unidentified":
                    # Generate new filename with bird name as suffix (without location)
                    new_filename = get_new_filename(image_path, bird_name, is_blurred)
                    # Create the file in the output directory
                    new_path = output_dir / new_filename

                    # Copy the file to the output directory with new name
                    shutil.copy2(str(image_path), str(new_path))
                    loaded_birds.append(bird_name)
                else:
                    # Handle unidentified birds the same way as identified ones
                    new_filename = get_new_filename(image_path, "Unidentified", is_blurred)
                    new_path = output_dir / new_filename
                    shutil.copy2(str(image_path), str(new_path))
                    loaded_birds.append("Unidentified")

                # Mark image as processed and save progress
                processed_images.add(image_path.name)
                save_progress(str(progress_file), list(processed_images))

            # Clear progress file after successful completion
            clear_progress(str(progress_file))

            # Update final status
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': "Classification completed! Click 'Distribute into Folders' to organize the photos."
            })

            # Enable the distribute button
            self.distribute_button.state(['!disabled'])

            # Use queue to show messagebox from main thread
            self.queue.put({
                'type': 'messagebox_info',
                'title': 'Success',
                'text': "Classification completed! Click 'Distribute into Folders' to organize the photos."
            })

        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error: {str(e)}"
            })
            print(f"Error during classification: {str(e)}")
        finally:
            self.start_button.state(['!disabled'])
            # Always enable the distribute button
            self.distribute_button.state(['!disabled'])

    def start_distribution(self):
        """Start the distribution process in a separate thread"""
        # Validate API key
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your Google API Key")
            return

        # Validate input folder
        input_folder = self.dist_input_path.get()
        if not input_folder:
            messagebox.showerror("Error", "Please select an input folder")
            return

        # Validate output folder
        output_folder = self.dist_output_path.get()
        if not output_folder:
            messagebox.showerror("Error", "Please select an output folder")
            return

        # Clear the log
        self.dist_log_text.delete(1.0, tk.END)

        # Reset progress
        self.dist_progress_var.set(0)
        self.dist_status_label.config(text="Starting distribution...")

        # Disable button
        self.dist_start_button.state(['disabled'])

        # Start processing in a separate thread
        thread = threading.Thread(target=self.distribute_to_organized_folder, args=(input_folder, output_folder, api_key))
        thread.daemon = True
        thread.start()

    def extract_bird_name_from_filename(self, filename_stem, api_key):
        """Use AI to extract the bird name from a filename"""
        try:
            prompt = f"""I have a photo filename (without extension): "{filename_stem}"

This filename contains the original photo name and a bird species name appended to it.
The format is typically: [original_photo_name] [bird_species_name][ blurred]

Please extract and return ONLY the bird species name. If there are multiple bird names mentioned, return the most appropriate one.
If the bird is "Unidentified" or you cannot determine a bird name, return "Unidentified".

Examples:
- "IMG_1234 Bengal Bush Lark" -> "Bengal Bush Lark"
- "0180_8884 Indian Bush Lark blurred" -> "Indian Bush Lark"
- "photo Bengal Bush Lark 0180_8884 Indian Bush Lark" -> "Bengal Bush Lark"

Respond with ONLY the bird species name, nothing else.

Response:"""

            response = call_gemini_api(api_key, prompt)
            response_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()

            # Clean up the response
            bird_name = re.sub(r'[^a-zA-Z\s\'\-]', '', response_text).strip()
            return bird_name if bird_name else None
        except Exception as e:
            print(f"Error extracting bird name from '{filename_stem}': {str(e)}")
            return None

    def match_bird_names(self, bird_name, existing_birds, api_key):
        """Use AI to match bird name with existing bird folders"""
        if not existing_birds:
            return None

        try:
            prompt = f"""I have a bird species called "{bird_name}".
I need to check if this is the same bird as any of the following existing bird names:
{', '.join(existing_birds)}

Please respond with ONLY the exact matching bird name from the list above, or "NO_MATCH" if none match.
The bird names might have slight variations (e.g., "Red Cardinal" vs "Cardinal" vs "Northern Cardinal"),
but they should refer to the same species. Be strict - only match if you're confident they're the same species.

Response:"""

            response = call_gemini_api(api_key, prompt)
            response_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()

            if response_text and response_text != "NO_MATCH" and response_text in existing_birds:
                return response_text
            return None
        except Exception as e:
            self.queue.put({'type': 'dist_log', 'text': f"Error matching bird name '{bird_name}': {str(e)}"})
            return None

    def distribute_to_organized_folder(self, input_folder, output_folder, api_key):
        """Main distribution logic"""
        try:
            input_path = Path(input_folder)
            output_path = Path(output_folder)

            # Create output folder if it doesn't exist
            output_path.mkdir(exist_ok=True)

            # Progress file path
            progress_file = output_path / '.alphabetic-distributor.progress'

            # Load progress
            progress_data = load_progress(str(progress_file))
            processed_folders = set(progress_data.get('processed', []))

            # Get the input folder name (for prepending)
            input_folder_name = input_path.name

            # Get all bird folders from input (skip info files and images)
            bird_folders = [f for f in input_path.iterdir() if f.is_dir() and not f.name.startswith('.')]

            if not bird_folders:
                self.queue.put({'type': 'dist_log', 'text': "No bird folders found in input directory"})
                self.queue.put({'type': 'dist_progress', 'value': 0, 'text': "No folders to process"})
                self.dist_start_button.state(['!disabled'])
                return

            total_folders = len(bird_folders)
            self.queue.put({'type': 'dist_log', 'text': f"Found {total_folders} bird folders to process"})

            # Build a map of existing birds in the output folder
            existing_birds_map = {}  # bird_name -> path
            for letter_folder in output_path.iterdir():
                if letter_folder.is_dir() and len(letter_folder.name) == 2 and letter_folder.name[0] == '0':
                    for bird_folder in letter_folder.iterdir():
                        if bird_folder.is_dir():
                            existing_birds_map[bird_folder.name] = bird_folder

            self.queue.put({'type': 'dist_log', 'text': f"Found {len(existing_birds_map)} existing bird folders in output"})

            # Process each bird folder
            for i, bird_folder in enumerate(bird_folders, 1):
                bird_name = bird_folder.name
                progress = (i / total_folders) * 100

                # Skip if already processed
                if bird_name in processed_folders:
                    self.queue.put({'type': 'dist_progress', 'value': progress, 'text': f"Skipping already processed {i}/{total_folders}: {bird_name}"})
                    self.queue.put({'type': 'dist_log', 'text': f"\n[{i}/{total_folders}] Skipping (already processed): {bird_name}"})
                    continue

                self.queue.put({'type': 'dist_progress', 'value': progress, 'text': f"Processing {i}/{total_folders}: {bird_name}"})
                self.queue.put({'type': 'dist_log', 'text': f"\n[{i}/{total_folders}] Processing: {bird_name}"})

                # Get all images in this bird folder
                images = [f for f in bird_folder.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and not f.name.startswith('._')]

                if not images:
                    self.queue.put({'type': 'dist_log', 'text': f"  No images found in {bird_name}, skipping"})
                    continue

                # Try to match with existing birds
                matched_bird = self.match_bird_names(bird_name, list(existing_birds_map.keys()), api_key)

                if matched_bird:
                    # Use existing folder
                    target_folder = existing_birds_map[matched_bird]
                    self.queue.put({'type': 'dist_log', 'text': f"  Matched to existing bird: {matched_bird}"})
                else:
                    # Create new folder
                    # Determine letter folder (0A, 0B, etc.)
                    first_letter = bird_name[0].upper()
                    letter_folder_name = f"0{first_letter}"
                    letter_folder_path = output_path / letter_folder_name

                    # Create letter folder if needed
                    if not letter_folder_path.exists():
                        letter_folder_path.mkdir()
                        self.queue.put({'type': 'dist_log', 'text': f"  Created new letter folder: {letter_folder_name}"})

                    # Create bird folder
                    target_folder = letter_folder_path / bird_name
                    target_folder.mkdir(exist_ok=True)
                    existing_birds_map[bird_name] = target_folder
                    self.queue.put({'type': 'dist_log', 'text': f"  Created new bird folder: {bird_name} in {letter_folder_name}"})

                # Copy all images with prepended folder name
                copied_count = 0
                for image in images:
                    # Create new filename with prepended folder name
                    new_filename = f"{input_folder_name} {image.name}"
                    target_path = target_folder / new_filename

                    # Copy the file
                    shutil.copy2(str(image), str(target_path))
                    copied_count += 1

                self.queue.put({'type': 'dist_log', 'text': f"  Copied {copied_count} images to {target_folder}"})

                # Mark folder as processed and save progress
                processed_folders.add(bird_name)
                save_progress(str(progress_file), list(processed_folders))

            # Clear progress file after successful completion
            clear_progress(str(progress_file))

            # Final status
            self.queue.put({'type': 'dist_progress', 'value': 100, 'text': "Distribution completed!"})
            self.queue.put({'type': 'dist_log', 'text': f"\n✓ Distribution completed! Processed {total_folders} bird folders."})

            # Use queue to show messagebox from main thread
            self.queue.put({
                'type': 'messagebox_info',
                'title': 'Success',
                'text': f"Distribution completed!\nProcessed {total_folders} bird folders."
            })

        except Exception as e:
            error_msg = f"Error during distribution: {str(e)}"
            self.queue.put({'type': 'dist_log', 'text': f"\n✗ {error_msg}"})
            self.queue.put({'type': 'dist_progress', 'value': 0, 'text': "Error occurred"})
            # Use queue to show messagebox from main thread
            self.queue.put({
                'type': 'messagebox_error',
                'title': 'Error',
                'text': error_msg
            })
        finally:
            self.dist_start_button.state(['!disabled'])

def main():
    print("Starting application. This might take upto 2 minutes.")
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = BirdClassifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
