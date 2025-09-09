import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# List models accessible to your API key
models = genai.list_models()

for model in models:
    print(f"Model: {model.name}")
    print(f"Supported methods: {model.supported_generation_methods}\n")
