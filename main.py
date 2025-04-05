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

def encode_image(image_path):
    """Encode image to base64 string."""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def call_gemini_api(api_key, prompt, image_path=None):
    """Make API call to Gemini."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
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
                # Filter out non-alphabet characters
                bird_name = re.sub(r'[^a-zA-Z\s]', '', bird_name).strip()
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
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # API Key frame
        api_frame = ttk.Frame(main_frame)
        api_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(api_frame, text="Google API Key:").pack(side=tk.LEFT, padx=5)
        self.api_key_var = tk.StringVar(value=load_saved_api_key())
        self.api_key_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=50, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=5)
        
        # Folder selection
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(folder_frame, text="Input Folder:").pack(side=tk.LEFT, padx=5)
        self.folder_path = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        
        # Location input
        location_frame = ttk.Frame(main_frame)
        location_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(location_frame, text="Probable Location:").pack(side=tk.LEFT, padx=5)
        self.location_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.location_var, width=50).pack(side=tk.LEFT, padx=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        # Start button
        self.start_button = ttk.Button(buttons_frame, text="Start Classification", command=self.start_classification)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Distribute button (initially disabled)
        self.distribute_button = ttk.Button(buttons_frame, text="Distribute into Folders", command=self.distribute_photos, state='disabled')
        self.distribute_button.pack(side=tk.LEFT, padx=5)
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="5")
        progress_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Last processed image frame
        image_frame = ttk.LabelFrame(main_frame, text="Last Processed Image", padding="5")
        image_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.image_label = ttk.Label(image_frame)
        self.image_label.grid(row=0, column=0, padx=5, pady=5)
        
        # Bird name label
        self.bird_name_label = ttk.Label(image_frame, text="", font=('Arial', 12, 'bold'))
        self.bird_name_label.grid(row=1, column=0, padx=5, pady=5)
        
        # Configure grid weights
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        # Queue for thread communication
        self.queue = Queue()
        
        # Store the input directory path
        self.input_dir = None
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            # Enable both start and distribute buttons when folder is selected
            self.start_button.state(['!disabled'])
            self.distribute_button.state(['!disabled'])
    
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
            output_dir = self.input_dir / '0000-bird-folders'
            output_dir.mkdir(exist_ok=True)
            
            # Get all image files
            images = [f for f in output_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
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
                # Update progress
                progress = (i / total_images) * 100
                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Processing image {i} of {total_images}: {image_path.name}"
                })
                
                # Extract bird name from filename
                # Format: original_name bird_name.extension
                name_parts = image_path.stem.split()
                if len(name_parts) > 1:
                    # Get the bird name (last part before extension)
                    bird_name = (" ".join(name_parts[1:])).split(".")[0]
                    
                    # Skip if bird is unidentified or if there's no bird name
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
            
            # Update final status with summary
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': f"Distribution completed! Organized {len(unique_birds)} unique bird species."
            })
            
            messagebox.showinfo("Success", f"Photos have been distributed into folders!\nOrganized {len(unique_birds)} unique bird species.")
            
        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error during distribution: {str(e)}"
            })
            messagebox.showerror("Error", f"Error during distribution: {str(e)}")
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
            output_dir = self.input_dir / '0000-bird-folders'
            output_dir.mkdir(exist_ok=True)
            
            # Get list of images
            images = [f for f in self.input_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
            total_images = len(images)
            loaded_birds = ["None"]
            
            # Get user's probable location
            user_location = self.location_var.get().strip()
            if user_location:
                user_location = f"Probably {user_location}"
            
            for i, image_path in enumerate(images, 1):
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
            
            # Update final status
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': "Classification completed! Click 'Distribute into Folders' to organize the photos."
            })
            
            # Enable the distribute button
            self.distribute_button.state(['!disabled'])
            
            messagebox.showinfo("Success", "Classification completed! Click 'Distribute into Folders' to organize the photos.")
            
        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error: {str(e)}"
            })
            print(f"Error during classification: {str(e)}")
            #messagebox.showerror("Error", f"Error during classification: {str(e)}")
        finally:
            self.start_button.state(['!disabled'])
            # Always enable the distribute button
            self.distribute_button.state(['!disabled'])

def main():
    print("Starting application. This might take upto 2 minutes.")
    root = tk.Tk()
    app = BirdClassifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
