import os
import shutil
import argparse
from pathlib import Path
import google.genai as genai
from PIL import Image, ImageTk
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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

# Initialize client with API key
def init_client(api_key):
    return genai.Client(api_key=api_key)

# Get API key from environment variable or saved file
GOOGLE_API_KEY = load_saved_api_key()

client = genai.Client(api_key=GOOGLE_API_KEY)

def get_bird_info(bird_name):
    """Get detailed information about a bird using Gemini AI."""
    try:
        prompt = f"""For the bird species '{bird_name}', provide the following information in this exact format:
        Scientific name: [Scientific name]
        Description: [100 words about the bird's appearance, habitat, behavior, and characteristics]
        Wikipedia link: [Wikipedia link]

        Be specific and accurate. The description should be less than 100 words.
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
        
        # Start button
        self.start_button = ttk.Button(main_frame, text="Start Classification", command=self.start_classification)
        self.start_button.grid(row=2, column=0, columnspan=2, pady=10)
        
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
        
        # Initialize client as None
        self.client = None
    
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
        
        # Initialize Gemini client with the API key
        try:
            self.client = init_client(api_key)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize API client: {str(e)}")
            return
        
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("Error", "Please select an input folder")
            return
        
        self.start_button.state(['disabled'])
        self.progress_var.set(0)
        self.status_label.config(text="Starting classification...")
        
        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_photos, args=(folder,))
        thread.daemon = True
        thread.start()
        
        # Start GUI updates
        self.update_gui()
    
    def process_photos(self, input_folder):
        """Process photos from the input folder."""
        try:
            # Convert input folder to Path object
            input_dir = Path(input_folder)
            if not input_dir.exists():
                self.queue.put({
                    'type': 'error',
                    'text': f"Input folder '{input_folder}' does not exist"
                })
                return
            
            # Create output directory inside input folder
            output_dir = input_dir / '0000-bird-folders'
            unidentified_dir = output_dir / "Unidentified"
            output_dir.mkdir(exist_ok=True)
            unidentified_dir.mkdir(exist_ok=True)
            
            # Get list of images
            images = [f for f in input_dir.glob('*') if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
            total_images = len(images)
            
            for i, image_path in enumerate(images, 1):
                # Update progress
                progress = (i / total_images) * 100
                self.queue.put({
                    'type': 'progress',
                    'value': progress,
                    'text': f"Processing image {i} of {total_images}: {image_path.name}"
                })
                
                # Process image
                contains_bird, bird_name = identify_bird(image_path)
                
                # Update last processed image
                img = Image.open(image_path)
                # Resize image to fit GUI
                img.thumbnail((400, 400))
                photo = ImageTk.PhotoImage(img)
                self.queue.put({
                    'type': 'image',
                    'image': photo,
                    'text': f"Bird: {bird_name if bird_name else 'Unidentified'}"
                })
                
                if contains_bird and bird_name:
                    # Create bird folder if it doesn't exist
                    bird_folder = output_dir / bird_name
                    bird_folder.mkdir(exist_ok=True)
                    
                    # Create info file if it doesn't exist
                    info_file = bird_folder / "info.txt"
                    if not info_file.exists():
                        info_text = get_bird_info(bird_name)
                        if info_text:
                            create_bird_info_file(bird_folder, bird_name, info_text)
                    
                    # Generate new filename with bird name as suffix
                    new_filename = get_new_filename(image_path, bird_name)
                    
                    # Copy the image to the bird folder with new name
                    shutil.copy2(image_path, bird_folder / new_filename)
                else:
                    # Move unidentified photos to the Unidentified folder
                    shutil.copy2(image_path, unidentified_dir / image_path.name)
            
            # Update final status
            self.queue.put({
                'type': 'progress',
                'value': 100,
                'text': "Classification completed!"
            })
            
        except Exception as e:
            self.queue.put({
                'type': 'error',
                'text': f"Error: {str(e)}"
            })
        finally:
            self.start_button.state(['!disabled'])

def main():
    root = tk.Tk()
    app = BirdClassifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
