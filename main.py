import os
import shutil
import argparse
from pathlib import Path
import sys
import re
import requests
import base64
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dotenv import load_dotenv
import threading
from queue import Queue, Empty
import json

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

        # Configure grid weights for main frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Setup Classifier tab
        self.setup_classifier_tab(classifier_frame)

        # Setup Distributor tab
        self.setup_distributor_tab(distributor_frame)

        # Queue for thread communication
        self.queue = Queue()

        # Store the input directory path
        self.input_dir = None

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
        self.dist_log_text.update()

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
        except Empty:
            pass
        finally:
            self.root.after(100, self.update_gui)
    
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
        
        # Start GUI updates
        self.update_gui()
    
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
        
        # Start GUI updates
        self.update_gui()
    
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
                # Skip if already processed
                if image_path.name in processed_images:
                    continue
                # Update progress
                progress = (i / total_images) * 100
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
                # Skip if already processed
                if image_path.name in processed_images:
                    continue
                # Update progress
                progress = (i / total_images) * 100
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

                # Skip if already processed
                if bird_name in processed_folders:
                    continue

                progress = (i / total_folders) * 100

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
    root = tk.Tk()
    app = BirdClassifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
