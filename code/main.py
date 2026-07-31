import os
import json
from dotenv import load_dotenv
from crewai.tools import tool
from crewai import Agent, Task, Crew, Process, LLM

# ==========================================
# 1. SETUP & LLM INITIALISIERUNG
# ==========================================
load_dotenv()
print("🚀 Initialisiere SAP AI Core für CrewAI...")

if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

# Native CrewAI LLM Klasse (SAP AI Core)
sap_llm = LLM(model="sap/gpt-4o-mini")

# ==========================================
# 2. DAS TOOL (VALIDATOR)
# ==========================================
@tool("AVC Syntax & Format Validator")
def avc_format_validator(avc_code: str) -> str:
    """
    Prüft den generierten Code auf grundlegende AVC-Tugenden,
    insbesondere ob $self oder $root verwendet wird und ob
    alte Operatoren wie 'eq' oder 'ne' eliminiert wurden.
    """
    errors = []
    code_lower = avc_code.lower()
    
    if " eq " in code_lower or " ne " in code_lower:
        errors.append("[ERROR] Veraltete LO-VC Operatoren gefunden. Nutze '=' oder '<>' bzw '!='.")
    
    if "$self" not in code_lower and "$root" not in code_lower and "pc." not in code_lower:
        errors.append("[ERROR] Kein Objektbezug gefunden. Nutze $self., $root. oder Alias wie pc. (bei Constraints).")
        
    if "specified dummy" in code_lower:
        errors.append("[ERROR] 'specified dummy' gefunden. Der Analyst hätte das filtern sollen!")

    if not errors:
        return "SUCCESS: Code entspricht den syntaktischen AVC-Guidelines."
    
    return "VALIDATION FAILED:\n" + "\n".join(errors) + "\nBitte korrigiere den Code."

# ==========================================
# 3. DIE AGENTEN (Rollen-Definition)
# ==========================================
# Wir definieren die Agenten einmal global, da sich ihre Rolle nicht ändert.

analyst = Agent(
    role='LO-VC Data Analyst & Cleaner',
    goal='Bereinige das LO-VC JSON. Entferne tote Werte und extrahiere sauber die steuernden Merkmale.',
    backstory='Du bist ein präziser Datenanalyst. Du liest komplexe JSON-Vorbedingungen. Deine Hauptaufgabe: Ignoriere Werte, die "specified dummy" als Vorbedingung haben. Finde für die restlichen, gültigen Werte heraus, welche Merkmale sie steuern.',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

architect = Agent(
    role='AVC Table Architect',
    goal='Entwirf basierend auf den sauberen Daten einen Bauplan für eine AVC Variantentabelle.',
    backstory='Du bist der Systemarchitekt. Du bekommst eine Liste von Werten und deren steuernden Merkmalen. Du entscheidest, welche Merkmale die Spalten der Tabelle bilden. Wenn Werte exakt dieselben Vorbedingungen haben, instruierst du den Coder, diese mit dem IN() Operator zusammenzufassen.',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

synthesizer = Agent(
    role='AVC Syntax Coder',
    goal='Schreibe den finalen AVC Code (TABLE Aufruf und RESTRICT Constraints) basierend auf dem Architekten-Bauplan.',
    backstory='Du bist der Coder. Du übersetzt den Bauplan in strikte, fehlerfreie AVC-Syntax. Du erstellst eine TABLE-Definition und schreibst ein RESTRICT Constraint. Du nutzt immer korrekte Objektreferenzen (z.B. $self.). Du übergibst dein Ergebnis dem Validator-Tool.',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)

# ==========================================
# 4. DER ORCHESTRATOR (Die Pipeline-Logik)
# ==========================================
def process_lovc_json(input_file, output_file):
    print(f"📂 Lade JSON-Datei: {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der JSON: {e}")
        return

    all_results = []
    
    # Navigiere durch die JSON-Struktur (Klassen -> Merkmale)
    classes = data.get("classes", [])
    for cls in classes:
        characteristics = cls.get("characteristics", [])
        
        for char in characteristics:
            char_name = char.get("name", "Unknown")
            
            # Prüfen: Hat dieses Merkmal überhaupt Vorbedingungen?
            has_dependencies = False
            for val in char.get("values", []):
                if "dependency" in val and len(val["dependency"]) > 0:
                    has_dependencies = True
                    break
            
            # Wenn keine Vorbedingungen existieren, überspringen wir es (spart Zeit & Token)
            if not has_dependencies:
                continue
                
            print(f"\n==================================================")
            print(f"⚙️  Starte Pipeline für Merkmal: {char_name}")
            print(f"==================================================")
            
            # Den spezifischen JSON-Block in einen String umwandeln
            chunk_json_str = json.dumps(char, indent=2)
            
            # Dynamische Tasks für diesen spezifischen JSON-Chunk erstellen
            task_clean = Task(
                description=f'Analysiere dieses JSON für das Merkmal {char_name}:\n\n{chunk_json_str}\n\n1. Filtere Werte heraus, die "specified dummy" enthalten.\n2. Liste für die verbleibenden gültigen Werte auf, welche Merkmale sie steuern.',
                expected_output='Strukturierte Zusammenfassung der bereinigten Logik.',
                agent=analyst
            )

            task_architect = Task(
                description=f'Nimm die bereinigte Liste des Analysten für {char_name}. Erstelle einen Bauplan für eine AVC Tabelle. Identifiziere die Spalten. Instruiere den Coder, identische Bedingungen zu aggregieren.',
                expected_output='Ein Tabellen-Bauplan (Spalten) und Anweisungen für die Aggregation.',
                agent=architect
            )

            task_code = Task(
                description=f'Nimm den Bauplan des Architekten und schreibe den finalen AVC-Code (CONSTRAINT mit TABLE) für {char_name}. Prüfe den Code abschließend zwingend mit dem "AVC Syntax & Format Validator".',
                expected_output='Nur der fertige, valide AVC-Quellcode. Keine Erklärungen.',
                agent=synthesizer
            )
            
            # Die Crew für diesen Durchlauf zusammenstellen
            pipeline_crew = Crew(
                agents=[analyst, architect, synthesizer],
                tasks=[task_clean, task_architect, task_code],
                process=Process.sequential, 
                verbose=False # Auf True setzen, wenn du das Agenten-Gespräch live im Terminal sehen willst
            )
            
            # Pipeline abfeuern!
            try:
                result = pipeline_crew.kickoff()
                
                # Ergebnis formatieren und speichern
                final_output = f"\n/* ==========================================\n"
                final_output += f"   AVC CONSTRAINT FÜR MERKMAL: {char_name}\n"
                final_output += f"   ========================================== */\n"
                final_output += str(result) + "\n"
                
                all_results.append(final_output)
                print(f"✅ Erfolgreich generiert für {char_name}")
                
            except Exception as e:
                print(f"❌ Fehler bei Merkmal {char_name}: {e}")

    # Alle Ergebnisse in eine Datei schreiben
    print(f"\n💾 Speichere alle Ergebnisse in {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.writelines(all_results)
        
    print("🎉 MIGRATION ABGESCHLOSSEN!")

# ==========================================
# 5. PROGRAMMSTART
# ==========================================
if __name__ == "__main__":
    # Passe hier die Dateinamen an deine lokalen Dateien an
    INPUT_JSON = "Beispiel1_Vorbedingungen.json"
    OUTPUT_FILE = "MAS_Output_AVC_Constraints.txt"
    
    process_lovc_json(INPUT_JSON, OUTPUT_FILE)