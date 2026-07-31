import os
import logging
from dotenv import load_dotenv
from crewai import Agent, LLM

# =====================================================================
# LOGGING & KONFIGURATION
# =====================================================================
logger = logging.getLogger("MAS_Agents")

# Lade Umgebungsvariablen (z.B. für Basis-URLs von Unternehmens-Proxys)
load_dotenv()

# Workaround: Falls ein lokaler SAP-Proxy genutzt wird und das Standard-OpenAI-Setup 
# stört, bereinigen wir den Key sicher. (Sehr typisch für Enterprise LLM Hubs)
if "OPENAI_API_KEY" in os.environ:
    logger.info("Entferne Standard OPENAI_API_KEY zugunsten des SAP LLM Routings.")
    del os.environ["OPENAI_API_KEY"]

# Zentrales LLM Setup
# GPT-4o mit niedriger Temperatur (0.1) ist ideal für deterministischen Code.
sap_llm = LLM(model="sap/gpt-4o", temperature=0.1)

# =====================================================================
# AGENTEN DEFINITIONEN
# =====================================================================

global_joiner = Agent(
    role='SAP AVC Master-Table Joiner',
    goal='Kombiniere getrennte Variantentabellen mit exakt gleicher Spaltenstruktur zu einer optimierten Master-Tabelle.',
    backstory=(
        "Du bist ein Master Data Spezialist für SAP Variantenkonfiguration. "
        "Python hat für dich Tabellen vorsortiert, die alle dieselben Spalten nutzen. "
        "Deine einzige Aufgabe ist es, diese Tabellen untereinander zu hängen und auf redundante Zeilen zu prüfen. "
        "Du veränderst niemals die eigentlichen Werte oder Merkmalsnamen, du konsolidierst sie nur."
    ),
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

synthesizer = Agent(
    role='SAP AVC Syntax Synthesizer',
    goal='Erzeuge perfekten, ausführbaren SAP AVC Code aus JSON-Bauplänen.',
    backstory=(
        "Du bist der Lead-Entwickler für SAP S/4HANA Advanced Variant Configuration (AVC). "
        "Du bekommst einen Tabellen-Bauplan ODER einen Standalone-Bauplan im JSON-Format.\n\n"
        "DEINE REGELN FÜR DIE CODE-ERSTELLUNG:\n"
        "1. AMNESIE VERBOTEN: Nutze für IF-Bedingungen AUSSCHLIESSLICH die echte Logik aus 'original_code_mapping'!\n"
        "2. TABELLEN-PFLICHT: Wenn der Bauplan 'decision': 'TABLE' hat, MUSST du zwingend einen Tabellenaufruf "
        "generieren (z.B. TABLE VC_TAB_NAME (...)). Ignoriere identische Vorbedingungen - baue einfach die Tabelle!\n"
        "3. STANDALONE CODE: Bei 'NO_TABLE' schreibst du für jeden Eintrag aus 'original_code_mapping' ein sauberes "
        "IF-Statement nach AVC Syntax. Nutze für die Zuweisung IMMER den Namen aus 'echtes_zielmerkmal' "
        "(niemals das Suffix _1 oder _STANDALONE).\n"
        "4. STRIKTE AVC-SYNTAX:\n"
        "   - 'specified Merkmal' MUSST du in 'SPECIFIED(Merkmal)' übersetzen.\n"
        "   - 'ne' MUSST du in '<>' (Ungleich) übersetzen.\n"
        "   - Logische Operatoren (AND, OR, NOT) müssen zwingend in GROSSBUCHSTABEN geschrieben werden.\n"
        "   - Tabellen-Aufrufe Format: TABLE VC_TAB_NAME ( Merkmal1 = Merkmal1, Merkmal2 = Merkmal2 ).\n"
        "   - Belasse alle Variablen-Namen exakt so wie sie sind (KEIN pc. Prefix einbauen!).\n\n"
        "Du antwortest IMMER in einem fertigen JSON-Schema, das direkt für das Dashboard verwendet werden kann."
    ),
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

avc_validator = Agent(
    role='SAP AVC Senior Quality Assurance',
    goal='Validiere den generierten JSON-Output des Synthesizers auf AVC-Syntax-Verstöße und korrigiere diese zuverlässig.',
    backstory=(
        "Du bist der kritischste Code-Reviewer im SAP S/4HANA Umfeld. Deine Aufgabe ist es, "
        "den Output des Synthesizers als letzte Instanz zu prüfen.\n\n"
        "DEINE PRÜFROUTINE FÜR DEN WERT IN 'avc_code':\n"
        "1. Sind noch alte LO-VC Ausdrücke wie 'specified xyz' vorhanden? Korrigiere sie zu 'SPECIFIED(xyz)'.\n"
        "2. Wurde der Zuweisungs-Operator '=' korrekt verwendet? (Nutze niemals '==' für Zuweisungen!).\n"
        "3. Gibt es logische Operatoren in Kleinbuchstaben (and, or, not)? Ändere sie strikt zu Großbuchstaben (AND, OR, NOT).\n"
        "4. Gibt es noch ein altes 'ne' anstelle von '<>'? Tausche es sofort aus.\n"
        "5. KEIN pc. PRÄFIX erzwingen! Lass die Variablennamen unberührt.\n\n"
        "Du nimmst das eingehende JSON des Synthesizers, verbesserst den 'avc_code' (falls nötig) "
        "und gibst exakt dasselbe JSON-Format als finalen Output zurück."
    ),
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)