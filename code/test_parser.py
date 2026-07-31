import json
from utils_test_parser_v2 import extract_known_canon, heavy_preprocessing

# =====================================================================
# KONFIGURATION DER TEST-UMGEBUNG
# =====================================================================
# Datei 1: Das RIESIGE JSON, aus dem das Vokabular extrahiert wird.
FULL_MODEL_JSON = "Beispiel1_Vorbedingungen_full.json" 

# Datei 2: Das JSON, das wir tatsächlich umformen und testen wollen.
TEST_TARGET_JSON = "Beispiel1_Vorbedingungen.json" 

# Output-Dateien
OUTPUT_DEBUG_FILE = "debug_parser_test_v3.json"
OUTPUT_KNOWN_CANON_FILE = "debug_known_canon_v3.txt" # <-- NEU

def run_parser_test():
    print("=" * 60)
    print("🚀 STARTE ISOLIERTEN PRE-PROCESSOR TEST")
    print("=" * 60)

    # 1. Lexikon aus dem riesigen Modell laden
    try:
        with open(FULL_MODEL_JSON, 'r', encoding='utf-8') as f:
            full_data = json.load(f)
            known_canon = extract_known_canon(full_data)
            print(f"✅ Lexikon geladen: {len(known_canon)} klassifizierte Merkmale gefunden.")
            
            # --- NEU: Known Canon in eine Textdatei speichern ---
            with open(OUTPUT_KNOWN_CANON_FILE, 'w', encoding='utf-8') as kc_file:
                kc_file.write(f"=== KNOWN CANON ({len(known_canon)} Merkmale) ===\n\n")
                for char in sorted(list(known_canon)):
                    kc_file.write(f"{char}\n")
            print(f"💾 'knownCanon' (Erlaubt-Liste) gespeichert unter: {OUTPUT_KNOWN_CANON_FILE}")
            # ---------------------------------------------------
            
    except Exception as e:
        print(f"❌ Fehler beim Laden des vollen Modells: {e}")
        return

    # 2. Test-Zieldaten laden
    try:
        with open(TEST_TARGET_JSON, 'r', encoding='utf-8') as f:
            target_data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Zieldaten: {e}")
        return

    # 3. Merkmale durchlaufen und umformen
    print("\n🔍 Analysiere und kürze Logik-Ausdrücke...\n")
    
    classes = target_data.get("classes", [])
    for cls in classes:
        for i, char in enumerate(cls.get("characteristics", [])):
            char_name = char.get("name", "Unknown")
            
            # Wir prüfen kurz, ob es überhaupt Werte/Abhängigkeiten gibt
            has_dependencies = any("dependency" in val and len(val["dependency"]) > 0 for val in char.get("values", []))
            if not has_dependencies:
                continue

            print(f"--- Merkmal: {char_name} ---")
            
            # Um das Vorher/Nachher zu zeigen, lesen wir kurz die alten Werte aus
            for val in char.get("values", []):
                deps = val.get("dependency", [])
                if deps:
                    old_syntax = " AND ".join([f"({d.get('syntax', '')})" for d in deps])
                    print(f"  Code '{val.get('code')}':")
                    print(f"    VORHER :  {old_syntax}")

            # ⚙️ HIER PASSIERT DIE MAGIE: Der Preprocessor läuft
            processed_char = heavy_preprocessing(char, known_canon)
            cls["characteristics"][i] = processed_char
            
            # Nachher-Ergebnis ausgeben
            for val in processed_char.get("values", []):
                deps = val.get("dependency", [])
                if deps:
                    new_syntax = deps[0].get('syntax', '')
                    print(f"    NACHHER:  {new_syntax}\n")
            print("-" * 30)

    # 4. Speichern des finalen Ergebnisses
    try:
        with open(OUTPUT_DEBUG_FILE, 'w', encoding='utf-8') as debug_f:
            json.dump(target_data, debug_f, indent=2)
        print(f"\n💾 Fertiges, gekürztes JSON gespeichert unter: {OUTPUT_DEBUG_FILE}")
    except Exception as e:
        print(f"⚠️ Konnte Debug-Datei nicht speichern: {e}")

if __name__ == "__main__":
    run_parser_test()