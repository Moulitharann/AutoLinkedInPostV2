import os
import time
import socket
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse

def test_huggingface_image():
    # Load the .env file from the project root
    load_dotenv()
    
    api_key = os.getenv("HUGGING_FACE_API_KEY")
    if not api_key:
        print("❌ Error: HUGGING_FACE_API_KEY not found. Check your .env file.")
        return

    # Masked key for verification
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
    print(f"🔑 Using API Key: {masked_key}")

    model_id = "stabilityai/stable-diffusion-3.5-large"
    url = f"https://api-inference.huggingface.co/models/{model_id}"
    
    # --- DNS Diagnostic Step ---
    host = urlparse(url).hostname
    print(f"🔍 Checking DNS resolution for {host}...")
    try:
        socket.gethostbyname(host)
        print("✅ DNS resolution successful.")
    except socket.gaierror:
        print(f"❌ DNS Error: Cannot resolve {host}. Check your internet/VPN/DNS settings.")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"inputs": "Professional tech illustration: A high-tech server room with glowing blue lights, isometric 3D style."}

    print(f"🚀 Testing Hugging Face model: {model_id}...")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        # Handle 503 (Model Loading) with a simple retry
        if response.status_code == 503:
            print("⏳ Model is loading. Waiting 20 seconds to retry...")
            time.sleep(20)
            response = requests.post(url, headers=headers, json=payload, timeout=120)

        if response.status_code == 200:
            if "image" in response.headers.get("Content-Type", ""):
                with open("test_image.png", "wb") as f:
                    f.write(response.content)
                print(f"✅ Success! Image saved to: {os.path.abspath('test_image.png')}")
            else:
                print(f"⚠️ Received unexpected content type: {response.headers.get('Content-Type')}")
                print(f"Response: {response.text}")
        
        elif response.status_code == 401:
            print("❌ Unauthorized: Your Hugging Face API key is invalid or lacks 'Read' permissions.")
        else:
            print(f"❌ Failed with status code {response.status_code}")
            print(f"Response: {response.text}")
    
    except requests.exceptions.ConnectionError as e:
        print("❌ Connection Error: Could not resolve Hugging Face's address.")
        print("This is likely a DNS or network issue.")
        print("Troubleshooting steps:")
        print(" 1. Check your internet connection.")
        print(" 2. If using a VPN, try turning it off.")
        print(" 3. Try changing your DNS to Google (8.8.8.8) or Cloudflare (1.1.1.1).")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    test_huggingface_image()