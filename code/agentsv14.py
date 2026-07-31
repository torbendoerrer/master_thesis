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
    with open('avc_guidelinesv2.md', 'r', encoding='utf-8') as file:
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
# 4. DIE AGENTEN (Immunisierte Pipeline)
# ==========================================

local_builder = Agent(
    role='Local Table Architect',
    goal='Analysiere die vorverarbeitete Logik eines EINZELNEN Merkmals, baue strikte Tabellen und BEWAHRE die Original-Logik.',
    backstory=f'''Du bist der Systemarchitekt für die erste Abstraktionsebene. 
    Du bekommst Werte und deren stark vereinfachte logische Vorbedingungen. 
    
    DEINE WICHTIGSTE REGEL (ANTI-NULL-REGEL):
    Du darfst NIEMALS leere Strings ("") oder null-Werte in eine Tabelle schreiben! 
    Eine Tabelle MUSS homogen sein. Jede Spalte muss in der Bedingung des jeweiligen Wertes vorkommen.
    Wenn die Struktur abweicht, wähle "NO_TABLE".
    
    NEUE KRITISCHE REGEL (KEIN DATENVERLUST):
    Egal ob du dich für TABLE oder NO_TABLE entscheidest, du musst ZWINGEND ein "original_code_mapping" in deinem JSON mitliefern.
    Darin speicherst du für JEDEN Wert (Zielwert/Code) die exakte, von Python übergebene Vorbedingung (die logische Syntax). So stellst du sicher, dass nachfolgende Agenten den Code nicht erfinden müssen!
    ''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

global_joiner = Agent(
    role='Global Schema Optimizer & Table Joiner',
    goal='Nimm einen Bucket von inhaltlich ähnlichen Tabellen und führe sie zu einer Master-Tabelle zusammen.',
    backstory=f'''Du bist ein genialer Datenbank-Spezialist. Du bekommst einen "Bucket" voll mit lokalen Tabellen-Bauplänen, die dieselben Spalten nutzen.
    
    DEINE MISSION:
    1. Vergleiche die Tabellen.
    2. Führe sie zu einer großen Master-Tabelle zusammen.
    3. Bewahre das "original_code_mapping" der jeweiligen Tabellen und füge es zu einem großen Mapping zusammen, damit nichts verloren geht!
    ''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

synthesizer = Agent(
    role='AVC Syntax Coder & JSON Formatter',
    goal='Erstelle fehlerfreien AVC-Code aus Tabellen oder Code-Mappings ohne zu halluzinieren.',
    backstory=f'''Du bist der finale SAP AVC Entwickler. Nutze dieses Handbuch: {avc_knowledge}
    
    KRITISCHE ANTI-HALLUZINATIONS-REGELN:
    1. AMNESIE VERBOTEN: Erfinde NIEMALS Variablen wie "SpalteA" oder "SOME_DEPENDENCY". Du hast im Input das Feld "original_code_mapping" erhalten. Nutze für IF-Bedingungen AUSSCHLIESSLICH die echte Logik, die in diesem Mapping steht! Verändere die Variablen darin nicht.
    2. ANTI-SCHIZOPHRENIE: Generiere für denselben Sachverhalt ENTWEDER einen TABLE-Aufruf (falls eine Tabelle existiert und fehlerfrei ist) ODER IF-Statements aus dem Mapping. Verdopple die Logik niemals.
    3. MEHRDEUTIGKEITEN (IDENTISCHE ZEILEN): Wenn in "tabelle_zeilen" mehrere Zeilen EXAKT dieselben Vorbedingungen (Bedingungsspalten) haben, aber unterschiedliche Zielwerte liefern (z.B. Wert 12, 24, 25), ist das in SAP ein Konflikt! Diese Werte dürfen NICHT in die Tabelle. Löse sie im "avc_code" als Multi-Value-Zuweisung mit IN auf: z.B. `pc.<MERKMAL> IN ('12', '24', '25') IF <gemeinsame Vorbedingung>`.
    
    NUTZE EXAKT DIESES JSON-SCHEMA FÜR DEINEN FINALEN OUTPUT:
    {{
      "herleitung": "Erklärung (inkl. Begründung von Konfliktauflösungen oder GHOST-LOGIC)...",
      "tabelle_kopf": ["Spalte1", "Spalte2", "<ECHTER_MERKMALS_NAME>"],
      "tabelle_zeilen": [ ["Bedingung 1", "Zielwert"] ],
      "avc_code": "Dein generierter Code..."
    }}
    ''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)