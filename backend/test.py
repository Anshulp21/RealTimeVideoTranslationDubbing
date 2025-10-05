import requests, zipfile, io, os

url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
output_dir = "backend/models"

os.makedirs(output_dir, exist_ok=True)

print("Downloading Vosk model...")
r = requests.get(url)
z = zipfile.ZipFile(io.BytesIO(r.content))
z.extractall(output_dir)

print("Model downloaded and extracted to", output_dir)
