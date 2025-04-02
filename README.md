# Bird Photo Organizer

This script uses Google's Gemini AI to identify birds in photos and organize them into folders based on bird species.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your Google API key:
```bash
export GOOGLE_API_KEY='your-api-key-here'
```

## Usage

1. Create an `input` directory and place your photo folders inside it:
```
input/
  folder1/
    photo1.jpg
    photo2.jpg
  folder2/
    photo3.jpg
    ...
```

2. Run the script:
```bash
python main.py
```

3. The script will:
   - Process each photo in the input folders
   - Use Gemini AI to identify if the photo contains a bird
   - If a bird is identified, create a folder in the `output` directory with the bird's name
   - Copy the photo to the corresponding bird folder

The output structure will look like:
```
output/
  Bird Species 1/
    photo1.jpg
    photo3.jpg
  Bird Species 2/
    photo2.jpg
    ...
```

## Notes

- Supported image formats: JPG, JPEG, PNG
- The script will skip photos where no bird is identified
- If a bird species folder already exists, the script will use the existing folder 