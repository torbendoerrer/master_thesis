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

# Falls ein OpenAI Dummy-Key stört, wird er entfernt
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

# Native CrewAI LLM Klasse (SAP AI Core)
sap_llm = LLM(model="sap/gpt-4o-mini")


# ==========================================
# 2. WISSENSBASIS LADEN (Knowledge Injection)
# ==========================================
print("📚 Lade AVC-Wissensdokument...")
try:
    with open('avc_guidelines.md', 'r', encoding='utf-8') as file:
        avc_knowledge = file.read()
    print("✅ Wissensdokument erfolgreich geladen!")
except FileNotFoundError:
    print("⚠️ Warnung: 'avc_guidelines.md' nicht gefunden. Agent hat kein spezifisches Domänenwissen!")
    avc_knowledge = "Halte dich an die allgemeinen SAP AVC-Regeln. Nutze kein SQL und baue keine Metadaten in Tabellen."


# ==========================================
# 3. DAS TOOL (STRIKTER AVC VALIDATOR)
# ==========================================
@tool("AVC Syntax & Format Validator")
def avc_format_validator(avc_code: str) -> str:
    """
    Prüft den generierten Code auf grundlegende AVC-Tugenden.
    Verhindert SQL-Halluzinationen und Metadaten-Spalten.
    """
    errors = []
    code_lower = avc_code.lower()
    
    # 1. SQL-Verbot
    if any(sql_word in code_lower for sql_word in ["select ", "from ", "where "]):
        errors.append("[ERROR] SQL-Syntax gefunden! AVC nutzt kein SELECT, FROM oder WHERE. Nutze TABLE(...) und IF-Guards.")
        
    # 2. Metadaten-Verbot in Tabellen
    if any(meta in code_lower for meta in ["precondition", "description", "syntax", "code char"]):
        errors.append("[ERROR] Metadaten in der Tabelle gefunden! Eine Variantentabelle darf NUR echte Merkmale als Spalten haben (z.B. K40_FG_AF).")
        
    # 3. Alte Operatoren
    if " eq " in code_lower or " ne " in code_lower:
        errors.append("[ERROR] Veraltete LO-VC Operatoren gefunden. Nutze '=' oder '<>' bzw '!='.")
        
    # 4. Objektbezug
    if "$self" not in code_lower and "$root" not in code_lower and "pc." not in code_lower:
        errors.append("[ERROR] Kein Objektbezug gefunden. Nutze $self., $root. oder Alias wie pc. (bei Constraints).")

    if not errors:
        return "SUCCESS: Code entspricht den syntaktischen AVC-Guidelines."
    
    return "VALIDATION FAILED:\n" + "\n".join(errors) + "\nBitte korrigiere den Code zwingend!"


# ==========================================
# 4. DIE AGENTEN (Rollen-Definition)
# ==========================================

analyst = Agent(
    role='LO-VC Data Analyst & Cleaner',
    goal='Bereinige das LO-VC JSON. Entferne toten Code, Kommentare und extrahiere sauber die steuernden Merkmale.',
    backstory='''Du bist ein präziser Datenanalyst. Deine Aufgaben:
    1. Ignoriere Werte mit "specified dummy".
    2. GANZ WICHTIG: Wenn in der "syntax" Zeilen mit einem Stern (*) beginnen, sind das alte Kommentare. Lösche diese Zeilen rigoros aus deiner Analyse!
    3. Finde für die gültigen Werte heraus, welche Merkmale sie steuern.''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

architect = Agent(
    role='AVC Table Architect',
    goal='Erkläre die Logik und entwirf eine visuelle Markdown-Tabelle als Bauplan.',
    backstory='''Du bist der Systemarchitekt. Du bekommst eine Liste von Werten.
    Deine Aufgaben:
    1. Herleitung: Erkläre kurz in Textform, welche Werte du aggregierst (weil sie identische Bedingungen haben) und welche Ausreißer du als Einzeiler außerhalb der Tabelle behandelst.
    2. Visuelle Tabelle: Zeichne eine Markdown-Tabelle. Die Spaltenköpfe DÜRFEN NUR ECHTE MERKMALE sein (z.B. K40_FG_AF, K40_ABL, Zielwert). Keine Metadaten! Leere Zellen bedeuten Wildcards.''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

synthesizer = Agent(
    role='AVC Syntax Coder',
    goal='Schreibe den finalen, fehlerfreien AVC Code basierend auf dem Architekten-Bauplan und nutze dafür strikt das AVC-Handbuch.',
    backstory=f'''Du bist ein SAP-Entwickler, der sich strikt an die Syntax der Advanced Variant Configuration (AVC) hält.
    
    Hier ist dein offizielles Handbuch und Regelwerk, an das du dich ZWINGEND halten musst:
    
    --- START WISSENSBASIS ---
    {avc_knowledge}
    --- ENDE WISSENSBASIS ---
    
    DEIN OUTPUT FORMAT MUSS ZWINGEND SO AUSSEHEN:
    Gib zuerst die Herleitung und die visuelle Markdown-Tabelle des Architekten 1:1 aus.
    Darunter schreibst du "AVC CODE:" und fügst den reinen, sauberen AVC-Constraint-Code ein (TABLE und Einzeiler).''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)


# ==========================================
# 5. DER ORCHESTRATOR (Die Pipeline-Logik)
# ==========================================
def process_lovc_json(input_file, output_file):
    print(f"\n📂 Lade JSON-Datei: {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der JSON: {e}")
        return

    all_results = []
    
    classes = data.get("classes", [])
    for cls in classes:
        characteristics = cls.get("characteristics", [])
        
        for char in characteristics:
            char_name = char.get("name", "Unknown")
            
            # Prüfen, ob das Merkmal überhaupt Vorbedingungen hat
            has_dependencies = False
            for val in char.get("values", []):
                if "dependency" in val and len(val["dependency"]) > 0:
                    has_dependencies = True
                    break
            
            if not has_dependencies:
                continue
                
            print(f"\n==================================================")
            print(f"⚙️  Starte Pipeline für Merkmal: {char_name}")
            print(f"==================================================")
            
            chunk_json_str = json.dumps(char, indent=2)
            
            # Tasks definieren
            task_clean = Task(
                description=f'Analysiere dieses JSON für {char_name}:\n\n{chunk_json_str}\n\nLösche Dummy-Werte und alle mit * auskommentierten Zeilen. Liste die verbleibende saubere Logik auf.',
                expected_output='Bereinigte Liste der steuernden Merkmale pro Wert ohne Kommentare.',
                agent=analyst
            )

            task_architect = Task(
                description=f'Nimm die Analyse des Analysten für {char_name}. 1. Schreibe eine Herleitung (Aggregation/Ausreißer). 2. Zeichne eine visuelle Markdown-Tabelle mit den echten Merkmalen als Spalten.',
                expected_output='Textuelle Herleitung und eine Markdown-Tabelle.',
                agent=architect
            )

            task_code = Task(
                description=f'Nimm Herleitung und Tabelle des Architekten für {char_name}. Erstelle den AVC-Code nach Vorgabe deines Handbuchs. Prüfe den Code mit dem Validator. Präsentiere am Ende Herleitung, Tabelle und Code zusammen.',
                expected_output='Ein sauber strukturierter Bericht mit Herleitung, Tabelle und fehlerfreiem AVC-Code.',
                agent=synthesizer
            )
            
            # Crew zusammenstellen
            pipeline_crew = Crew(
                agents=[analyst, architect, synthesizer],
                tasks=[task_clean, task_architect, task_code],
                process=Process.sequential, 
                verbose=False # Setze dies auf True, um die KI beim Denken im Terminal zu beobachten
            )
            
            # Pipeline starten
            try:
                result = pipeline_crew.kickoff()
                
                # Output formatieren
                final_output = f"\n/* ==========================================\n"
                final_output += f"   MAS VORSCHLAG FÜR MERKMAL: {char_name}\n"
                final_output += f"   ========================================== */\n\n"
                final_output += str(result) + "\n"
                final_output += f"\n--------------------------------------------------\n"
                
                all_results.append(final_output)
                print(f"✅ Vorschlag erfolgreich generiert für {char_name}")
                
            except Exception as e:
                print(f"❌ Fehler bei Merkmal {char_name}: {e}")

    # Ergebnisse wegschreiben
    print(f"\n💾 Speichere alle Ergebnisse in {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.writelines(all_results)
        
    print("🎉 MIGRATION ABGESCHLOSSEN!")

# ==========================================
# 6. PROGRAMMSTART
# ==========================================
if __name__ == "__main__":
    INPUT_JSON = "Beispiel1_Vorbedingungen.json"
    OUTPUT_FILE = "MAS_Visuelle_Vorschlaege.txt"
    process_lovc_json(INPUT_JSON, OUTPUT_FILE)