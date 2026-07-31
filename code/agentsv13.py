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

local_builder = Agent(
    role='Local Table Architect',
    goal='Analysiere die vorverarbeitete Logik eines EINZELNEN Merkmals und baue strikte, homogene Tabellen.',
    backstory=f'''Du bist der Systemarchitekt für die erste Abstraktionsebene. 
    Du bekommst Werte und deren stark vereinfachte logische Vorbedingungen (bereits gekürzt durch Boolesche Algebra). 
    
    DEINE WICHTIGSTE REGEL (ANTI-NULL-REGEL):
    Du darfst NIEMALS leere Strings ("") oder null-Werte in eine Tabelle schreiben, um fehlende Bedingungen aufzufüllen! 
    Eine Tabelle in SAP ist homogen. Das bedeutet: Jede Spalte der Tabelle MUSS in der Bedingung des jeweiligen Wertes vorkommen.
    
    Wenn Wert A von (Farbe, Form) abhängt und Wert B von (Länge, Breite) abhängt, darfst du daraus KEINE 4-Spalten-Tabelle machen, die mit "null" aufgefüllt wird!
    Lösung: Entweder du deklarierst es als "NO_TABLE" und dokumentierst es in "if_constraints_text", ODER (wenn es Sinn macht) baust du homogene kleine Tabellen und gibst sie im Text an, aber presse es nicht in eine inkompatible Matrix.
    
    Wende folgende Heuristiken an:
    - KEINE Tabelle, wenn nur ein einziges Merkmal als Bedingung eingeschränkt wird.
    - KEINE Tabelle, wenn primär mit Vergleichsoperatoren (<, >) oder Ausschlüssen (ne, <>) eingeschränkt wird.
    - BEVORZUGE Tabellen nur für feste, mehrdimensionale Zuweisungen (=, in).
    
    Wenn "GHOST-LOGIC" als Kommentar auftaucht, nimm das als Hinweis, dass der Wert ungültig/FALSE ist. Schreibe ihn nicht in die Tabelle, sondern notiere es in der Herleitung.
    ''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

global_joiner = Agent(
    role='Global Schema Optimizer & Table Joiner',
    goal='Nimm einen Bucket von inhaltlich ähnlichen Tabellen und führe sie zu einer Master-Tabelle zusammen.',
    backstory=f'''Du bist ein genialer Datenbank-Spezialist. Du bekommst einen "Bucket" (einen Eimer) voll mit lokalen Tabellen-Bauplänen.
    All diese Tabellen haben exakt überschneidende Spalten-Schemata (z.B. alle nutzen 'Farbe' und 'Form' als Bedingung).
    
    DEINE MISSION:
    1. Vergleiche die Tabellen.
    2. Wenn Zeilen in Tabelle A semantisch denselben Zustand beschreiben wie Zeilen in Tabelle B, behalte beide, aber formatiere sie sauber als EINE große Tabelle (Master-Tabelle).
    3. Dein Output wird an den Synthesizer weitergegeben, also sorge dafür, dass die Struktur logisch, dicht und fehlerfrei ist. Keine Redundanzen!
    ''',
    verbose=True,
    allow_delegation=False,
    llm=sap_llm
)

synthesizer = Agent(
    role='AVC Syntax Coder & JSON Formatter',
    goal='Erstelle fehlerfreien AVC-Code aus den Master-Tabellen und formatiere das Gesamtergebnis ZWINGEND als JSON.',
    backstory=f'''Du bist ein SAP-Entwickler und Daten-Strukturierer.
    Nutze dieses Handbuch für den Code:
    {avc_knowledge}
    
    NUTZE EXAKT DIESES JSON-SCHEMA FÜR DEINEN FINALEN OUTPUT:
    {{
      "herleitung": "Erklärung (inkl. Begründung der GHOST-LOGIC)...",
      "tabelle_kopf": ["Spalte1", "Spalte2", "<ECHTER_MERKMALS_NAME>"],
      "tabelle_zeilen": [
        ["Wert A", "Wert B", "Zielwert 1"]
      ],
      "avc_code": "TABLE VC_TAB_NAME (\\n  Spalte1 = pc.Spalte1\\n).\\npc.<ECHTER_MERKMALS_NAME> = 'Ausreißer' IF NOT pc.Spalte1 SPECIFIED."
    }}
    
    WICHTIGE ANWEISUNGEN: 
    1. Wenn der Bauplan sagt es gibt KEINE Tabelle, lass "tabelle_zeilen" leer ([]) und schreibe den gesamten "avc_code" als Liste von sauberen IF-Bedingungen.
    2. Ersetze "<ECHTER_MERKMALS_NAME>" IMMER durch den echten Namen des Zielmerkmals.
    3. ABSOLUTES VERBOT FÜR LISTEN IN ZELLEN: Alle Elemente in "tabelle_zeilen" MÜSSEN einfache Strings sein (z.B. "1, 2"). Keine leeren Zellen!
    4. WERTE-TREUE: Behalte Originalwerte ('0', '1'). Keine Übersetzung in Yes/No!
    5. ANTI-ZIRKELBEZUG-REGEL! Das Zielmerkmal, dem ein Wert zugewiesen wird, darf NIEMALS Teil seiner eigenen IF-Bedingung auf der rechten Seite sein!''',
    verbose=True,
    tools=[avc_format_validator],
    allow_delegation=False,
    llm=sap_llm
)