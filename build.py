import os
import platform
import subprocess
import shutil
import sys


def run_command(command):
    subprocess.run(command, check=True)


def ensure_pip():
    try:
        run_command([sys.executable, '-m', 'pip', '--version'])
    except subprocess.CalledProcessError:
        print("pip is not available in this Python environment. Trying ensurepip...")
        run_command([sys.executable, '-m', 'ensurepip', '--upgrade'])

def build_app():
    ensure_pip()

    # Install requirements into the same Python environment running this script.
    run_command([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
    
    # Clean previous builds
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    raw_dist = 'dist-build'
    if os.path.exists(raw_dist):
        shutil.rmtree(raw_dist)
    
    # Build the application. tkinterdnd2 needs its bundled tkdnd files collected.
    run_command([
        sys.executable,
        '-m',
        'PyInstaller',
        '--onefile',
        '--name=BirdClassifier',
        f'--distpath={raw_dist}',
        '--hidden-import=tkinterdnd2',
        '--collect-all=tkinterdnd2',
        'main.py',
    ])
    
    # Create distribution folder
    dist_folder = 'dist/BirdClassifier'
    os.makedirs(dist_folder)
    
    # Copy the executable
    if platform.system() == 'Windows':
        executable = os.path.join(raw_dist, 'BirdClassifier.exe')
    else:
        executable = os.path.join(raw_dist, 'BirdClassifier')

    if not os.path.isfile(executable):
        raise FileNotFoundError(f"PyInstaller did not create the expected executable: {executable}")

    shutil.copy(executable, dist_folder)
    
    # Copy the .env file
    if os.path.exists('.env'):
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

The classified photos will be organized in a '0000-<folder-name>' directory inside your selected folder.

Note: The API key will be saved automatically after the first use.
""")

    shutil.rmtree(raw_dist)
    
    print(f"\nBuild completed! The application is in the {dist_folder} folder.")

if __name__ == "__main__":
    build_app()
