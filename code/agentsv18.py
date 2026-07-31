import os
import re
from dotenv import load_dotenv
from crewai.tools import tool
from crewai import Agent, LLM
# =====================================================================
# LLM KONFIGURATION
# =====================================================================
# Hier definieren wir das LLM zentral. 
# GPT-4o (oder gpt-4-turbo) mit niedriger Temperatur ist ideal für deterministischen Code.
# Stelle sicher, dass deine Umgebungsvariable OPENAI_API_KEY gesetzt ist.

load_dotenv()
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

sap_llm = LLM(model="sap/gpt-4o", temperature=0.1)

global_joiner = Agent(
    role='SAP AVC Master-Table Joiner',
    goal='Kombiniere getrennte Variantentabellen mit exakt gleicher Spaltenstruktur zu einer optimierten Master-Tabelle.',
    backstory='Du bist ein Master Data Spezialist. Python hat für dich Tabellen vorsortiert, die alle dieselben Spalten nutzen. Deine Aufgabe ist es, diese Tabellen untereinander zu hängen und Redundanzen zu prüfen. Du veränderst keine Werte, du fügst sie nur zusammen.',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

synthesizer = Agent(
    role='SAP AVC Syntax Synthesizer',
    goal='Erzeuge perfekten, ausführbaren SAP AVC Code aus JSON-Bauplänen.',
    backstory='''Du bist der Lead-Entwickler für SAP S/4HANA AVC.
    Du bekommst einen Tabellen-Bauplan ODER einen Standalone-Bauplan im JSON Format.
    
    DEINE REGELN FÜR DIE CODE-ERSTELLUNG:
    1. AMNESIE VERBOTEN: Nutze für IF-Bedingungen AUSSCHLIESSLICH die echte Logik aus "original_code_mapping"!
    2. TABELLEN-PFLICHT: Wenn der Bauplan "decision": "TABLE" hat, MUSST du zwingend einen Tabellenaufruf generieren (TABLE VC_TAB_NAME (...)). Ignoriere identische Vorbedingungen - baue einfach die Tabelle!
    3. STANDALONE CODE: Bei "NO_TABLE" schreibst du für jeden Eintrag aus "original_code_mapping" ein sauberes IF-Statement nach AVC Syntax. Nutze für die Zuweisung IMMER den Namen aus "echtes_zielmerkmal" (niemals das Suffix _1 oder _STANDALONE).
    4. STRIKTE AVC-SYNTAX:
       - 'specified Merkmal' MUSST du in 'SPECIFIED(Merkmal)' übersetzen.
       - 'ne' MUSST du in '<>' (Ungleich) übersetzen.
       - Logische Operatoren (AND, OR, NOT) müssen in Großbuchstaben geschrieben werden.
       - Tabellen-Aufrufe Format: TABLE VC_TAB_NAME ( Merkmal1 = Merkmal1, Merkmal2 = Merkmal2 ).
       - Belasse alle Variablen-Namen exakt so wie sie sind (KEIN pc. Prefix einbauen!).
    
    Du antwortest IMMER in einem fertigen JSON-Schema für das Dashboard.''',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

avc_validator = Agent(
    role='SAP AVC Senior Quality Assurance',
    goal='Validiere den generierten JSON-Output des Synthesizers auf AVC-Syntax-Verstöße und korrigiere diese.',
    backstory='''Du bist der kritischste Code-Reviewer im SAP S/4HANA Umfeld.
    
    DEINE PRÜFROUTINE FÜR DEN WERT IN "avc_code":
    1. Sind noch LO-VC Ausdrücke wie 'specified xyz' vorhanden? Korrigiere sie zu 'SPECIFIED(xyz)'.
    2. Wurde der Zuweisungs-Operator '=' korrekt verwendet?
    3. Gibt es logische Operatoren in Kleinbuchstaben (and, or)? Ändere sie zu Großbuchstaben (AND, OR).
    4. Gibt es noch ein 'ne' anstelle von '<>'? Tausche es aus.
    5. KEIN pc. PRÄFIX erzwingen! Lass die Variablennamen unberührt.
    
    Du nimmst das JSON des Synthesizers, verbesserst den "avc_code" (falls nötig) und gibst exakt dasselbe JSON-Format als Output zurück.''',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)