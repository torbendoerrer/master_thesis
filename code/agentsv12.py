import os
import re
from dotenv import load_dotenv
from crewai.tools import tool
from crewai import Agent, LLM

# ==========================================
# 1. SETUP & LLM INITIALISIERUNG
# ==========================================
load_dotenv()
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

sap_llm = LLM(model="sap/gpt-4o")

# ==========================================
# 2. WISSENSBASIS LADEN
# ==========================================
try:
    with open('avc_guidelines.md', 'r', encoding='utf-8') as file:
        avc_knowledge = file.read()
except FileNotFoundError:
    avc_knowledge = "Halte dich an die SAP AVC-Regeln."

# ==========================================
# 3. DAS TOOL (STRIKTER AVC VALIDATOR)
# ==========================================
@tool("AVC Syntax & Format Validator")
def avc_format_validator(avc_code: str) -> str:
    """Prüft den generierten Code auf grundlegende AVC-Tugenden und Logikfehler."""
    errors = []
    code_lower = avc_code.lower()
    
    if any(sql_word in code_lower for sql_word in ["select ", "from ", "where "]):
        errors.append("[ERROR] SQL-Syntax gefunden! AVC nutzt kein SELECT, FROM oder WHERE.")
    if " eq " in code_lower or " ne " in code_lower:
        errors.append("[ERROR] Veraltete LO-VC Operatoren gefunden. Nutze '=' oder '<>'.")
    if "$self" not in code_lower and "$root" not in code_lower and "pc." not in code_lower:
        errors.append("[ERROR] Kein Objektbezug gefunden. Nutze z.B. pc.Merkmal.")
    
    # Anti-Zirkelbezug Prüfung im Validator
    lines = code_lower.split('\n')
    for line in lines:
        if " if " in line:
            parts = line.split(" if ")
            left_side = parts[0].strip()
            right_side = parts[1].strip()
            match = re.search(r'pc\.(\w+)\s*=', left_side)
            if match:
                target_var = match.group(1)
                if f"pc.{target_var}" in right_side:
                    errors.append(f"[ERROR] Zirkelbezug gefunden in Zeile: '{line}'. Das Zielmerkmal ({target_var}) darf nicht Teil der eigenen IF-Bedingung sein!")

    if not errors:
        return "SUCCESS: Code entspricht den syntaktischen AVC-Guidelines."
    return "VALIDATION FAILED:\n" + "\n".join(errors) + "\nBitte korrigiere den Code!"

# ==========================================
# 4. DIE AGENTEN (Rollen-Definition für Pipeline 3.0)
# ==========================================

# --- AGENT 1: LOCAL BUILDER (Fokus auf ein Merkmal) ---
local_builder = Agent(
    role='Local Table Architect',
    goal='Analysiere die vorverarbeitete Logik eines EINZELNEN Merkmals und entscheide, ob eine Tabelle sinnvoll ist. Wenn ja, erstelle einen Tabellen-Bauplan.',
    backstory=f'''Du bist der Systemarchitekt für die erste Abstraktionsebene. 
    Du bekommst Werte und deren stark vereinfachte logische Vorbedingungen (bereits gekürzt durch Boolesche Algebra). 
    
    DEINE WICHTIGSTE AUFGABE: ENTSCHEIDUNG ÜBER TABELLE VS. CODE
    Wende folgende universelle SAP-Heuristiken an, um zu entscheiden, OB für dieses Merkmal eine Tabelle gebaut wird:
    - KEINE Tabelle, wenn nur ein einziges Merkmal als Bedingung eingeschränkt wird.
    - KEINE Tabelle, wenn primär mit Vergleichsoperatoren (<, >) oder Ausschlüssen (ne, <>) eingeschränkt wird.
    - BEVORZUGE Tabellen nur für feste, mehrdimensionale Zuweisungen (=, in) und Zusammenfassungen von Werten.
    
    WICHTIGE ANWEISUNGEN FÜR TABELLEN:
    1. Nutze ausschließlich echte Merkmale als Spalten.
    2. Die letzte Spalte ist IMMER das Zielmerkmal (das konfiguriert wird).
    3. ZIELWERT-REGEL: In der Ergebnis-Spalte (der letzten Spalte) darf pro Zeile IMMER NUR EIN EINZIGER WERT stehen! 
    4. Wenn GHOST-LOGIC als Kommentar auftaucht, ignoriere sie für die Tabellenstruktur, aber erwähne sie in deiner Herleitung.
    
    Wenn keine Tabelle gebaut werden soll, deklariere ganz klar "KEINE_TABELLE" und dokumentiere die verbleibenden IF-Constraints.''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

# --- AGENT 2: GLOBAL JOINER (Redundanz-Killer) ---
global_joiner = Agent(
    role='Global Schema Optimizer & Table Joiner',
    goal='Nimm einen Bucket von inhaltlich ähnlichen Tabellen, erkenne Redundanzen und führe sie zu Master-Tabellen zusammen.',
    backstory=f'''Du bist ein genialer Datenbank-Spezialist. Du bekommst einen "Bucket" (einen Eimer) voll mit lokalen Tabellen-Bauplänen, die von anderen Agenten generiert wurden. 
    All diese Tabellen haben sich überschneidende Spalten-Schemata (z.B. alle nutzen 'Farbe' und 'Form' als Bedingung).
    
    DEINE MISSION (MAP-REDUCE):
    1. Vergleiche die Tabellen.
    2. Wenn Zeilen in Tabelle A semantisch denselben Zustand beschreiben wie Zeilen in Tabelle B, führe sie in einer Master-Tabelle zusammen.
    3. JOIN-REGEL: Manchmal lässt sich eine Tabelle um eine neue Spalte erweitern (als "Wildcard" oder "Any"), um eine andere Tabelle aufzunehmen.
    4. Ziel ist es, die Gesamtanzahl der Tabellen in deinem Bucket auf das absolute Minimum zu reduzieren, OHNE die Logik der SAP-Zuweisungen zu verfälschen.
    
    Output: Eine bereinigte Liste von abstrakten Master-Tabellen für deinen Bucket.''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

# --- AGENT 3: AVC SYNTHESIZER ---
synthesizer = Agent(
    role='AVC Syntax Coder & JSON Formatter',
    goal='Erstelle fehlerfreien AVC-Code aus den Master-Tabellen und formatiere das Gesamtergebnis ZWINGEND als JSON.',
    backstory=f'''Du bist ein SAP-Entwickler und Daten-Strukturierer.
    Nutze dieses Handbuch für den Code:
    {avc_knowledge}
    
    DEINE WICHTIGSTE REGEL: 
    Dein Output MUSS ein sauberes JSON-Objekt sein.
    
    NUTZE EXAKT DIESES JSON-SCHEMA:
    {{
      "herleitung": "Erklärung (inkl. Begründung der GHOST-LOGIC)...",
      "tabelle_kopf": ["Spalte1", "Spalte2", "<ECHTER_MERKMALS_NAME>"],
      "tabelle_zeilen": [
        ["Wert A", "Wert B", "Zielwert 1"]
      ],
      "avc_code": "TABLE VC_TAB_NAME (\\n  Spalte1 = pc.Spalte1\\n).\\npc.<ECHTER_MERKMALS_NAME> = 'Ausreißer' IF NOT pc.Spalte1 SPECIFIED."
    }}
    
    WICHTIGE ANWEISUNGEN: 
    1. Wenn der Bauplan "KEINE_TABELLE" sagt, lass "tabelle_zeilen" leer ([]) und schreibe den gesamten "avc_code" als Liste von sauberen IF-Bedingungen.
    2. Ersetze "<ECHTER_MERKMALS_NAME>" IMMER durch den echten Namen des Zielmerkmals.
    3. ABSOLUTES VERBOT FÜR LISTEN IN ZELLEN: Alle Elemente in "tabelle_zeilen" MÜSSEN einfache Strings sein (z.B. "1, 2").
    4. WERTE-TREUE: Behalte Originalwerte ('0', '1'). Keine Übersetzung in Yes/No/True/False!
    5. ANTI-ZIRKELBEZUG-REGEL! Das Zielmerkmal, dem ein Wert zugewiesen wird, darf NIEMALS Teil seiner eigenen IF-Bedingung auf der rechten Seite sein!''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)