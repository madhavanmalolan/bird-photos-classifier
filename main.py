import os
import shutil
import argparse
from pathlib import Path
import sys

# Check for required libraries
try:
    import requests
except ImportError:
    print("Error: 'requests' library is not installed. Please run: pip install requests")
    sys.exit(1)

try:
    import base64
except ImportError:
    print("Error: 'base64' module is not available. This is a standard library module and should be available.")
    sys.exit(1)

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Error: 'Pillow' library is not installed. Please run: pip install Pillow")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("Error: 'tkinter' is not installed. On macOS, try: brew install python-tk@3.9")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Error: 'python-dotenv' library is not installed. Please run: pip install python-dotenv")
    sys.exit(1)

try:
    import json
except ImportError:
    print("Error: 'json' module is not available. This is a standard library module and should be available.")
    sys.exit(1)

try:
    import threading
    from queue import Queue, Empty
except ImportError:
    print("Error: 'threading' or 'queue' module is not available. These are standard library modules and should be available.")
    sys.exit(1)

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
        print(f"Error getting bird info: {str(e)}")
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

def identify_bird(image_path, api_key, loaded_birds):
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
        The bird is most likely to be shot in India, but might also have been shot in other countries.
        You have already identified the following birds: {', '.join(list(set(loaded_birds)))} already. Check if this bird is one of them. If yes, make sure to return the exact same name.
        The last bird you identified was {loaded_birds[-1]}. See if this bird is same as the last bird you identified.
        """
        
        response = call_gemini_api(api_key, prompt, image_path)
        response_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        print(response_text)
        
        # Parse the response
        contains_bird = "Contains bird: Yes" in response_text
        bird_name = None
        is_blurred = False
        
        for line in response_text.split('\n'):
            if line.startswith('Bird name:'):
                bird_name = line.replace('Bird name:', '').strip()
                if bird_name.lower() == 'n/a':
                    bird_name = None
            elif line.startswith('Is blurred:'):
                is_blurred = "Is blurred: Yes" in line
        
        return contains_bird, bird_name, is_blurred
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        return False, None, False

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
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        # Start button
        self.start_button = ttk.Button(buttons_frame, text="Start Classification", command=self.start_classification)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Distribute button (initially disabled)
        self.distribute_button = ttk.Button(buttons_frame, text="Distribute into Folders", command=self.distribute_photos, state='disabled')
        self.distribute_button.pack(side=tk.LEFT, padx=5)
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="5")
        progress_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Last processed image frame
        image_frame = ttk.LabelFrame(main_frame, text="Last Processed Image", padding="5")
        image_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.image_label = ttk.Label(image_frame)
        self.image_label.grid(row=0, column=0, padx=5, pady=5)
        
        # Bird name label
        self.bird_name_label = ttk.Label(image_frame, text="", font=('Arial', 12, 'bold'))
        self.bird_name_label.grid(row=1, column=0, padx=5, pady=5)
        
        # Configure grid weights
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # Queue for thread communication
        self.queue = Queue()
        
        # Store the input directory path
        self.input_dir = None
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
    
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
        """Distribute photos into folders based on their names."""
        if not self.input_dir:
            messagebox.showerror("Error", "Please select an input folder first")
            return
            
        try:
            # Create output directory
            output_dir = self.input_dir / '0000-bird-folders'
            output_dir.mkdir(exist_ok=True)
            
            # Get all image files
            images = [f for f in output_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
            total_images = len(images)
            
            for i, image_path in enumerate(images, 1):
                # Update progress
                progress = (i / total_images) * 100
                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Distributing image {i} of {total_images}: {image_path.name}"
                })
                
                # Extract bird name from filename
                # Format: original_name bird_name.extension
                name_parts = image_path.stem.split()
                if len(name_parts) > 1:
                    # Get the bird name (last part before extension)
                    bird_name = (" ".join(name_parts[1:])).split(".")[0]
                    # Create bird folder
                    bird_folder = output_dir / bird_name
                    bird_folder.mkdir(exist_ok=True)
                    
                    # Move the file to the bird folder
                    shutil.move(str(image_path), str(bird_folder / image_path.name))
            
            # Update final status
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': "Distribution completed!"
            })
            
            messagebox.showinfo("Success", "Photos have been distributed into folders!")
            
        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error during distribution: {str(e)}"
            })
            messagebox.showerror("Error", f"Error during distribution: {str(e)}")

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
            
            for i, image_path in enumerate(images, 1):
                # Update progress
                progress = (i / total_images) * 100
                if i > 10:
                    break
                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Processing image {i} of {total_images}: {image_path.name}"
                })
                
                # Process image
                contains_bird, bird_name, is_blurred = identify_bird(image_path, api_key, loaded_birds)
                
                # Update last processed image
                img = Image.open(image_path)
                # Resize image to fit GUI
                img.thumbnail((400, 400))
                photo = ImageTk.PhotoImage(img)
                status_text = f"Bird: {bird_name if bird_name else 'Unidentified'}"
                if is_blurred:
                    status_text += " (Blurred)"
                self.queue.put({
                    'type': 'image',
                    'image': photo,
                    'text': status_text
                })
                
                if contains_bird and bird_name:
                    # Generate new filename with bird name as suffix
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
            messagebox.showerror("Error", f"Error during classification: {str(e)}")
        finally:
            self.start_button.state(['!disabled'])

def main():
    root = tk.Tk()
    app = BirdClassifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
