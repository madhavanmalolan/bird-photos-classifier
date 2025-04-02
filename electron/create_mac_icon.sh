#!/bin/bash

# Create iconset directory
mkdir bird-classifier.iconset

# Generate different icon sizes
sips -z 16 16 icon.png --out bird-classifier.iconset/icon_16x16.png
sips -z 32 32 icon.png --out bird-classifier.iconset/icon_16x16@2x.png
sips -z 32 32 icon.png --out bird-classifier.iconset/icon_32x32.png
sips -z 64 64 icon.png --out bird-classifier.iconset/icon_32x32@2x.png
sips -z 128 128 icon.png --out bird-classifier.iconset/icon_128x128.png
sips -z 256 256 icon.png --out bird-classifier.iconset/icon_128x128@2x.png
sips -z 256 256 icon.png --out bird-classifier.iconset/icon_256x256.png
sips -z 512 512 icon.png --out bird-classifier.iconset/icon_256x256@2x.png
sips -z 512 512 icon.png --out bird-classifier.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out bird-classifier.iconset/icon_512x512@2x.png

# Convert to .icns
iconutil -c icns bird-classifier.iconset

# Cleanup
rm -rf bird-classifier.iconset 