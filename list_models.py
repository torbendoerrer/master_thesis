import os
import google.generativeai as genai
from dotenv import load_dotenv

# 1. Key aus der .env Datei laden
load_dotenv()

# 2. Dem Google-Paket den Key übergeben
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("Kein Key in der .env gefunden!")

genai.configure(api_key=api_key)

# 3. Alle Modelle abfragen und auflisten
print("\nVerfügbare Modelle für die Textgenerierung:")
print("-" * 45)

for m in genai.list_models():
    # Wir filtern nach Modellen, die 'generateContent' (also Text-Generierung) unterstützen
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)