const { ipcRenderer } = require('electron');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

// DOM elements
const apiKeyInput = document.getElementById('apiKey');
const folderPathInput = document.getElementById('folderPath');
const browseBtn = document.getElementById('browseBtn');
const startBtn = document.getElementById('startBtn');
const progressBar = document.getElementById('progressBar');
const statusText = document.getElementById('status');
const previewImg = document.getElementById('preview');
const birdNameText = document.getElementById('birdName');

// Load saved API key
window.addEventListener('DOMContentLoaded', async () => {
    const savedApiKey = await ipcRenderer.invoke('get-api-key');
    if (savedApiKey) {
        apiKeyInput.value = savedApiKey;
    }
});

// Handle folder selection
browseBtn.addEventListener('click', async () => {
    const result = await ipcRenderer.invoke('select-folder');
    if (result) {
        folderPathInput.value = result;
    }
});

// Handle start button
startBtn.addEventListener('click', async () => {
    const apiKey = apiKeyInput.value.trim();
    const folderPath = folderPathInput.value;

    if (!apiKey) {
        alert('Please enter your Google API Key');
        return;
    }

    if (!folderPath) {
        alert('Please select an input folder');
        return;
    }

    // Save API key
    await ipcRenderer.invoke('save-api-key', apiKey);

    // Disable controls
    startBtn.disabled = true;
    apiKeyInput.disabled = true;
    folderPathInput.disabled = true;
    browseBtn.disabled = true;

    try {
        await processPhotos(folderPath, apiKey);
    } catch (error) {
        alert(`Error: ${error.message}`);
    } finally {
        // Re-enable controls
        startBtn.disabled = false;
        apiKeyInput.disabled = false;
        folderPathInput.disabled = false;
        browseBtn.disabled = false;
    }
});

async function processPhotos(folderPath, apiKey) {
    const files = fs.readdirSync(folderPath)
        .filter(file => /\.(jpg|jpeg|png)$/i.test(file));
    
    const totalFiles = files.length;
    let processedFiles = 0;

    // Create output directory
    const outputDir = path.join(folderPath, '0000-bird-folders');
    const unidentifiedDir = path.join(outputDir, 'Unidentified');
    fs.mkdirSync(outputDir, { recursive: true });
    fs.mkdirSync(unidentifiedDir, { recursive: true });

    for (const file of files) {
        const filePath = path.join(folderPath, file);
        
        // Update progress
        processedFiles++;
        const progress = (processedFiles / totalFiles) * 100;
        progressBar.value = progress;
        statusText.textContent = `Processing ${file} (${processedFiles}/${totalFiles})`;

        try {
            // Identify bird
            const { containsBird, birdName } = await identifyBird(filePath, apiKey);
            
            // Show preview and bird name only after identification
            previewImg.src = `file://${filePath}`;
            previewImg.style.display = 'block';
            birdNameText.textContent = `Bird: ${birdName || 'Unidentified'}`;

            if (containsBird && birdName) {
                // Create bird folder
                const birdFolder = path.join(outputDir, birdName);
                fs.mkdirSync(birdFolder, { recursive: true });

                // Get bird info
                const infoText = await getBirdInfo(birdName, apiKey);
                if (infoText) {
                    fs.writeFileSync(
                        path.join(birdFolder, 'info.txt'),
                        `Name: ${birdName}\n\n${infoText}`
                    );
                }

                // Copy image with new name
                const newFileName = `${path.parse(file).name}_${birdName}${path.parse(file).ext}`;
                fs.copyFileSync(filePath, path.join(birdFolder, newFileName));
            } else {
                // Move to unidentified
                fs.copyFileSync(filePath, path.join(unidentifiedDir, file));
            }
        } catch (error) {
            console.error(`Error processing ${file}:`, error);
            // Move to unidentified on error
            fs.copyFileSync(filePath, path.join(unidentifiedDir, file));
        }
    }

    statusText.textContent = 'Classification completed!';
}

async function identifyBird(imagePath, apiKey) {
    const imageData = fs.readFileSync(imagePath, 'base64');
    
    const response = await axios.post(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`,
        {
            contents: [{
                parts: [
                    { text: `Analyze this image and tell me:
                    1. Does this image contain a bird? (Yes/No)
                    2. If yes, what is the name of the bird? (If you can identify it)
                    Please respond in this exact format:
                    Contains bird: [Yes/No]
                    Bird name: [Name or N/A]
                    
                    Be exact in the name of the bird. Qualify the exact species. Be specific. Don't use scientific names.
                    The bird is most likely to be shot in India, but might also have been shot in other countries.` },
                    {
                        inline_data: {
                            mime_type: 'image/jpeg',
                            data: imageData
                        }
                    }
                ]
            }]
        }
    );

    const responseText = response.data.candidates[0].content.parts[0].text;
    console.log(responseText);

    const containsBird = responseText.includes('Contains bird: Yes');
    let birdName = null;

    if (containsBird) {
        const nameMatch = responseText.match(/Bird name: (.*)/);
        if (nameMatch && nameMatch[1].toLowerCase() !== 'n/a') {
            birdName = nameMatch[1].trim();
        }
    }

    return { containsBird, birdName };
}

async function getBirdInfo(birdName, apiKey) {
    const response = await axios.post(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`,
        {
            contents: [{
                parts: [{
                    text: `For the bird species '${birdName}', provide the following information in this exact format:
                    Scientific name: [Scientific name]
                    Description: [100 words about the bird's appearance, habitat, behavior, and characteristics]
                    Wikipedia link: [Wikipedia link]

                    Be specific and accurate. The description should be less than 100 words.`
                }]
            }]
        }
    );

    return response.data.candidates[0].content.parts[0].text;
} 