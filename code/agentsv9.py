import os
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
    with open('avc_guidelinesv2.md', 'r', encoding='utf-8') as file:
        avc_knowledge = file.read()
except FileNotFoundError:
    avc_knowledge = "Halte dich an die SAP AVC-Regeln."

try:
    with open('domain_knowledgev8.md', 'r', encoding='utf-8') as file:
        domain_knowledge = file.read()
except FileNotFoundError:
    domain_knowledge = "Kein spezifisches Domänenwissen vorhanden."

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
    
    if "<echter_merkmals_name>" in code_lower:
        errors.append("[ERROR] Platzhalter <ECHTER_MERKMALS_NAME> im Code gefunden! Bitte durch das reale Ziel-Merkmal ersetzen.")
    if " = ''" in code_lower or " = \"\"" in code_lower:
        errors.append("[ERROR] Leere Strings (= '') sind meistens Fehler. Nutze 'NOT pc.Merkmal SPECIFIED'.")

    if not errors:
        return "SUCCESS: Code entspricht den syntaktischen AVC-Guidelines."
    return "VALIDATION FAILED:\n" + "\n".join(errors) + "\nBitte korrigiere den Code!"

# ==========================================
# 4. DIE AGENTEN (Rollen-Definition)
# ==========================================
analyst = Agent(
    role='LO-VC Data Analyst & Cleaner',
    goal='Bereinige das LO-VC JSON, verarbeite unklassifizierte Geister-Merkmale und wende Kundendomänenwissen an.',
    backstory=f'''Du bist ein präziser Datenanalyst. Deine Aufgaben:
    1. Lösche alte Kommentare (Zeilen mit *).
    2. Das Feld "precondition" (z.B. V_TW0016) enthält nur technische Datenbank-IDs. Ignoriere diese komplett.
    3. Lies ausschließlich das Feld "syntax". Wenn es leer ist, bedeutet das in SAP "NOT SPECIFIED". Interpretiere ein leeres Feld NIEMALS als '0'!
    4. ARRAY-LOGIK: Wenn ein Wert mehrere "dependencies" besitzt, sind diese zwingend mit UND verknüpft!
    
    --- NEU: LOGIK FÜR UNKLASSIFIZIERTE GEISTER-MERKMALE ---
    Ein Python-Skript hat die Syntax bereits gescannt. Wenn du in der Syntax ein Merkmal siehst, das mit [UNCLASSIFIED] markiert ist (z.B. "[UNCLASSIFIED] K40_Sitzheizung"), wende ZWINGEND folgende SAP-Regeln an:
    A) "Zuweisungen/Vergleiche": Wenn das [UNCLASSIFIED] Merkmal mit =, in, ne, <> oder ähnlichem verglichen wird -> Ignoriere/Verwirf diese gesamte Zeile/Bedingung komplett!
    B) "specified [UNCLASSIFIED]": Dies ist unerfüllbar (unsat). Da "dependencies" UND-verknüpft sind, tötet das den gesamten Code (Wert). Streiche den Wert!
    C) "not specified [UNCLASSIFIED]": Das ist immer wahr (noop). Ignoriere nur diesen Teil der Bedingung, bewerte den Rest des Codes ganz normal weiter.
    
    5. WENDE ZWINGEND FOLGENDES KUNDENSPEZIFISCHES WISSEN AN:
    --- START DOMÄNENWISSEN ---
    {domain_knowledge}
    --- ENDE DOMÄNENWISSEN ---
    ''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

architect = Agent(
    role='AVC Table Architect',
    goal='Entscheide anhand von Heuristiken, ob eine Tabelle gebaut wird, und entwirf diese.',
    backstory=f'''Du bist der Systemarchitekt. Du bekommst eine Liste von Werten.
    
    DEINE WICHTIGSTE AUFGABE: ENTSCHEIDUNG ÜBER TABELLE VS. CODE
    Wende folgende universelle SAP-Heuristiken an, um zu entscheiden, OB du überhaupt eine Tabelle baust:
    - KEINE Tabelle, wenn nur ein einziges Merkmal eingeschränkt wird.
    - KEINE Tabelle, wenn mit Vergleichsoperatoren (<, >) eingeschränkt wird.
    - KEINE Tabelle, wenn primär über Ausschlüsse (ne, <>, not in) eingeschränkt wird.
    - BEVORZUGE Tabellen nur für feste Zuweisungen (=, in) und Zusammenfassungen von Werten.
    - Halte Tabellen klein (maximal 6-8 Spalten).
    
    Wenn die Heuristiken gegen eine Tabelle sprechen: Übergib dem Synthesizer ein leeres Array für die Tabelle und weise ihn an, die Logik rein als IF-Constraints zu schreiben. Erkläre das in der Herleitung.
    
    Wenn du eine Tabelle baust:
    1. Nutze ausschließlich echte Merkmale als Spalten.
    2. Die letzte Spalte ist das konfiguriert werdende Zielmerkmal.
    3. Behalte Originalwerte bei ('0', '1'). Keine Übersetzung in 'Yes'/'No'.
    
    Berücksichtige für Ausreißer und gelöschte Werte folgendes Domänenwissen:
    --- START DOMÄNENWISSEN ---
    {domain_knowledge}
    --- ENDE DOMÄNENWISSEN ---''',
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
    Dein Output MUSS ein sauberes JSON-Objekt sein.
    
    NUTZE EXAKT DIESES JSON-SCHEMA:
    {{
      "herleitung": "Erklärung des Architekten (inkl. Entscheidung ob Tabelle oder nur Code)...",
      "tabelle_kopf": ["Spalte1", "Spalte2", "<ECHTER_MERKMALS_NAME>"],
      "tabelle_zeilen": [
        ["Wert A", "Wert B", "Zielwert 1"]
      ],
      "avc_code": "TABLE VC_TAB_NAME (\\n  Spalte1 = pc.Spalte1\\n).\\npc.<ECHTER_MERKMALS_NAME> = 'Ausreißer' IF NOT pc.Spalte1 SPECIFIED."
    }}
    
    WICHTIGE ANWEISUNGEN: 
    1. Wenn der Architekt entscheidet, KEINE Tabelle zu nutzen, lass "tabelle_zeilen" leer ([]) und schreibe den gesamten "avc_code" als Liste von IF-Bedingungen.
    2. Ersetze "<ECHTER_MERKMALS_NAME>" IMMER durch den echten Namen des Zielmerkmals.
    3. "NOT SPECIFIED" im Code wird zu "NOT pc.Merkmal SPECIFIED".
    4. ABSOLUTES VERBOT FÜR LISTEN IN ZELLEN: Alle Elemente in "tabelle_zeilen" MÜSSEN einfache Strings sein (z.B. "1, 2").
    5. WERTE-TREUE: Behalte Originalwerte ('0', '1'). Keine Übersetzung in Yes/No/True/False!''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)