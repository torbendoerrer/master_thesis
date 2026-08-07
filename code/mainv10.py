import json
from crewai import Task, Crew, Process

# --- Importiere unsere ausgelagerten Module ---
from utilsv10 import extract_json_from_output, create_excel_dashboard, extract_known_canon, preprocess_characteristic_json
from agentsv10 import analyst, architect, synthesizer

def process_lovc_json(input_file, output_file, debug_file="debug_preprocessedv10_third_run.json"):
    print(f"\n📂 Lade JSON-Datei: {input_file}")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der JSON: {e}")
        return

    dashboard_data = {}
    
    # 1. Schritt: knownCanon (Erlaubte Merkmale) über das gesamte Dokument extrahieren
    known_canon = extract_known_canon(data)
    print(f"🔍 System hat {len(known_canon)} klassifizierte Merkmale im 'knownCanon' gefunden.")
    
    # =================================================================
    # NEU: PRE-PROCESSING FÜR DAS GESAMTE DOKUMENT & DEBUG-SAVE
    # =================================================================
    # Wir überschreiben die Daten im Speicher mit den getaggten Versionen
    for cls in data.get("classes", []):
        for i, char in enumerate(cls.get("characteristics", [])):
            cls["characteristics"][i] = preprocess_characteristic_json(char, known_canon)
            
    # Wir speichern den Zustand NACH dem Python-Filter in eine Debug-Datei
    try:
        with open(debug_file, 'w', encoding='utf-8') as debug_f:
            json.dump(data, debug_f, indent=2)
        print(f"💾 Pre-Processor Output (für Debugging) gespeichert unter: {debug_file}")
    except Exception as e:
        print(f"⚠️ Konnte Debug-Datei nicht speichern: {e}")
    # =================================================================

    # 2. Schritt: KI-Pipeline für die vorbearbeiteten Merkmale starten
    classes = data.get("classes", [])
    for cls in classes:
        for char in cls.get("characteristics", []):
            char_name = char.get("name", "Unknown")
            
            # Prüfen, ob Abhängigkeiten vorhanden sind
            has_dependencies = any("dependency" in val and len(val["dependency"]) > 0 for val in char.get("values", []))
            if not has_dependencies:
                continue
                
            print(f"\n==================================================")
            print(f"⚙️  Starte Pipeline für Merkmal: {char_name}")
            print(f"==================================================")
            
            # Da das JSON schon vorher getaggt wurde, können wir es direkt an die KI geben
            chunk_json_str = json.dumps(char, indent=2)
            
            task_clean = Task(
                description=f'Analysiere JSON für {char_name}:\n{chunk_json_str}\nIgnoriere "precondition" IDs. Achte streng auf [UNCLASSIFIED] Tags und die SAP-Regeln dazu.',
                expected_output='Saubere Merkmalsliste, bei der unsat/unclcmp Zeilen gemäß Regeln entfernt wurden.',
                agent=analyst
            )

            task_architect = Task(
                description=f'Erstelle Herleitung und entscheide anhand deiner Heuristiken, ob für {char_name} eine Tabelle gebaut werden soll oder ob IF-Constraints reichen.',
                expected_output='Architektur-Plan inkl. Tabellenentscheidung.',
                agent=architect
            )

            task_code = Task(
                description=f'Erstelle AVC Code für {char_name}. Formatiere dein Gesamtergebnis ZWINGEND als JSON nach dem vorgegebenen Schema.',
                expected_output='Ein sauberes JSON Objekt.',
                agent=synthesizer
            )
            
            pipeline_crew = Crew(
                agents=[analyst, architect, synthesizer],
                tasks=[task_clean, task_architect, task_code],
                process=Process.sequential, 
                verbose=False
            )
            
            try:
                result = pipeline_crew.kickoff()
                parsed_json = extract_json_from_output(str(result))
                
                if parsed_json:
                    dashboard_data[char_name] = parsed_json
                    print(f"✅ Vorschlag erfolgreich verarbeitet für {char_name}")
                else:
                    print(f"⚠️ Konnte JSON für {char_name} nicht parsen. Übersprungen.")
                    
            except Exception as e:
                print(f"❌ Fehler bei Merkmal {char_name}: {e}")

    # 3. Schritt: Excel generieren
    if dashboard_data:
        create_excel_dashboard(output_file, dashboard_data)
    else:
        print("Keine validen Daten zur Excel-Erstellung gefunden.")

if __name__ == "__main__":
    INPUT_JSON = "Beispiel1_Vorbedingungen.json"
    OUTPUT_FILE = "MAS_Entwickler_Dashboardv10_third_run.xlsx"
    
    print("Starte hybride Multi-Agenten-System Pipeline...")
    process_lovc_json(INPUT_JSON, OUTPUT_FILE)