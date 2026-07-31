import os
from dotenv import load_dotenv
from crewai.tools import tool
from crewai import Agent, LLM

# ==========================================
# 1. SETUP & LLM INITIALISIERUNG
# ==========================================
load_dotenv()

# Dummy-Key bereinigen falls nötig
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

# Native CrewAI LLM Klasse (GPT-4o für bestes Instruction-Following)
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
    """Prüft den generierten Code auf grundlegende AVC-Tugenden."""
    errors = []
    code_lower = avc_code.lower()
    
    if any(sql_word in code_lower for sql_word in ["select ", "from ", "where "]):
        errors.append("[ERROR] SQL-Syntax gefunden! AVC nutzt kein SELECT, FROM oder WHERE.")
    if any(meta in code_lower for meta in ["precondition", "description", "syntax", "code char"]):
        errors.append("[ERROR] Metadaten in der Tabelle gefunden! Nutze nur echte Merkmale als Spalten.")
    if " eq " in code_lower or " ne " in code_lower:
        errors.append("[ERROR] Veraltete LO-VC Operatoren gefunden. Nutze '=' oder '<>'.")
    if "$self" not in code_lower and "$root" not in code_lower and "pc." not in code_lower:
        errors.append("[ERROR] Kein Objektbezug gefunden. Nutze z.B. pc.Merkmal.")

    if not errors:
        return "SUCCESS: Code entspricht den syntaktischen AVC-Guidelines."
    return "VALIDATION FAILED:\n" + "\n".join(errors) + "\nBitte korrigiere den Code!"

# ==========================================
# 4. DIE AGENTEN (Rollen-Definition)
# ==========================================
analyst = Agent(
    role='LO-VC Data Analyst & Cleaner',
    goal='Bereinige das LO-VC JSON. Ignoriere technische IDs und extrahiere NUR die echten Merkmale aus der Syntax.',
    backstory='''Du bist ein präziser Datenanalyst. Deine Aufgaben:
    1. Ignoriere Werte mit "specified dummy".
    2. Lösche Zeilen mit einem Stern (*), das sind alte Kommentare.
    3. WICHTIG: Das Feld "precondition" (z.B. V_TW0016) enthält nur technische Datenbank-IDs. Das sind KEINE Merkmale! Ignoriere diese IDs komplett.
    4. Lies ausschließlich das Feld "syntax". Extrahiere daraus die echten Merkmale, die den jeweiligen Wert steuern.''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

architect = Agent(
    role='AVC Table Architect',
    goal='Entwirf eine tabellarische Struktur, die ausschließlich echte Merkmale als Spalten nutzt.',
    backstory='''Du bist der Systemarchitekt. Du bekommst eine Liste von Werten.
    Deine Aufgaben:
    1. Herleitung: Erkläre kurz, welche Werte du aggregierst und welche du als Ausreißer behandelst.
    2. Tabellen-Entwurf: Lege fest, welche echten Merkmale die Spalten der Tabelle bilden. 
    WICHTIG: Die letzte Spalte ist die Ergebnis-Spalte. Nenne diese Spalte exakt nach dem Merkmal, das konfiguriert wird (z.B. K40_KO). Nutze keine IDs wie V_TW0016 oder Metadaten als Spalten!''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

synthesizer = Agent(
    role='AVC Syntax Coder & JSON Formatter',
    goal='Erstelle fehlerfreien AVC-Code und formatiere das Gesamtergebnis ZWINGEND als JSON.',
    backstory=f'''Du bist ein SAP-Entwickler und Daten-Strukturierer.
    Nutze dieses Handbuch für den Code:
    {avc_knowledge}
    
    DEINE WICHTIGSTE REGEL: 
    Dein finaler Output darf KEIN Fließtext sein, sondern MUSS ein sauberes, maschinenlesbares JSON-Objekt sein.
    Bilde die Werte, die du in die Tabelle schreibst, NICHT mehr durch IF-Anweisungen im Code ab!
    
    NUTZE EXAKT DIESES JSON-SCHEMA FÜR DEINEN FINALEN OUTPUT:
    {{
      "herleitung": "Erklärung des Architekten als Text...",
      "tabelle_kopf": ["Spalte1", "Spalte2", "Ergebnis_Merkmal"],
      "tabelle_zeilen": [
        ["Wert A", "Wert B", "Zielwert 1"],
        ["*", "Wert C", "Zielwert 2"]
      ],
      "avc_code": "TABLE VC_TAB_NAME (\\n  Spalte1 = pc.Spalte1\\n).\\npc.Ergebnis = 'Ausreißer' IF pc.Spalte1 = 'X'."
    }}
    
    Achte darauf, dass das JSON gültig ist (korrekte Anführungszeichen entkommen).''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)