import json
from crewai import Task, Crew, Process

# --- Importiere unsere ausgelagerten Module ---
from utilsv6 import extract_json_from_output, create_excel_dashboard
from agentsv6 import analyst, architect, synthesizer

def process_lovc_json(input_file, output_file):
    print(f"\n📂 Lade JSON-Datei: {input_file}")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der JSON: {e}")
        return

    dashboard_data = {}
    
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
            
            chunk_json_str = json.dumps(char, indent=2)
            
            task_clean = Task(
                description=f'Analysiere JSON für {char_name}:\n{chunk_json_str}\nIgnoriere "precondition" IDs. Extrahiere reine Logik aus "syntax".',
                expected_output='Saubere Merkmalsliste.',
                agent=analyst
            )

            task_architect = Task(
                description=f'Erstelle Herleitung und Tabellenstruktur für {char_name} aus der Analysten-Liste. Keine technischen IDs als Spalten!',
                expected_output='Architektur-Plan.',
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
                verbose=False # Setze auf True für Konsolen-Debugging der KI-Gedankengänge
            )
            
            try:
                result = pipeline_crew.kickoff()
                # Parse JSON aus dem Output unter Verwendung unserer Hilfsfunktion aus utils.py
                parsed_json = extract_json_from_output(str(result))
                
                if parsed_json:
                    dashboard_data[char_name] = parsed_json
                    print(f"✅ Vorschlag erfolgreich verarbeitet für {char_name}")
                else:
                    print(f"⚠️ Konnte JSON für {char_name} nicht parsen. Übersprungen.")
                    
            except Exception as e:
                print(f"❌ Fehler bei Merkmal {char_name}: {e}")

    # Am Ende: Excel generieren unter Verwendung unserer Hilfsfunktion aus utils.py
    if dashboard_data:
        create_excel_dashboard(output_file, dashboard_data)
    else:
        print("Keine validen Daten zur Excel-Erstellung gefunden.")


if __name__ == "__main__":
    # Stelle sicher, dass diese Dateien im selben Ordner liegen
    INPUT_JSON = "Beispiel1_Vorbedingungen.json"
    OUTPUT_FILE = "MAS_Entwickler_Dashboardv6.xlsx"
    
    print("Starte Multi-Agenten-System Pipeline...")
    process_lovc_json(INPUT_JSON, OUTPUT_FILE)