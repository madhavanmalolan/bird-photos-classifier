import os
import platform
import subprocess
import shutil

def build_app():
    # Install requirements
    subprocess.run(['pip', 'install', '-r', 'requirements.txt'])
    
    # Clean previous builds
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    
    # Build the application
    subprocess.run(['pyinstaller', '--onefile', '--name=BirdClassifier', 'main.py'])
    
    # Create distribution folder
    dist_folder = 'dist/BirdClassifier'
    if os.path.exists(dist_folder):
        shutil.rmtree(dist_folder)
    os.makedirs(dist_folder)
    
    # Copy the executable
    if platform.system() == 'Windows':
        shutil.copy('dist/BirdClassifier.exe', dist_folder)
    else:
        shutil.copy('dist/BirdClassifier', dist_folder)
    
    # Copy the .env file
    shutil.copy('.env', dist_folder)
    
    # Create a README file
    with open(os.path.join(dist_folder, 'README.txt'), 'w') as f:
        f.write("""Bird Photo Classifier

Instructions:
1. Place your bird photos in a folder
2. Run the application
3. Enter your Google API key in the input field
4. Click 'Browse' to select your folder
5. Click 'Start Classification'
6. Wait for the process to complete

The classified photos will be organized in a '0000-bird-folders' directory inside your selected folder.

Note: The API key will be saved automatically after the first use.
""")
    
    print(f"\nBuild completed! The application is in the {dist_folder} folder.")

if __name__ == "__main__":
    build_app() 