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

# =====================================================================
# AGENT 1: Der Global Joiner (Redundanz-Auflöser für Tabellen)
# =====================================================================
global_joiner = Agent(
    role='SAP AVC Master-Table Joiner',
    goal='Kombiniere getrennte Variantentabellen mit exakt gleicher Spaltenstruktur zu einer optimierten Master-Tabelle.',
    backstory='Du bist ein Master Data Spezialist. Python hat für dich Tabellen vorsortiert, die alle dieselben Spalten nutzen. Deine Aufgabe ist es, diese Tabellen untereinander zu hängen und Redundanzen zu prüfen. Du veränderst keine Werte, du fügst sie nur zusammen.',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

# =====================================================================
# AGENT 2: Der Synthesizer (Der AVC-Coder)
# =====================================================================
synthesizer = Agent(
    role='SAP AVC Syntax Synthesizer',
    goal='Erzeuge perfekten, ausführbaren SAP AVC Code aus JSON-Bauplänen und löse Duplikate (gleiche Vorbedingungen) fehlerfrei auf.',
    backstory='''Du bist der Lead-Entwickler für SAP S/4HANA AVC.
    Du bekommst einen Tabellen-Bauplan ODER einen Standalone-Bauplan im JSON Format.
    
    DEINE REGELN FÜR DIE CODE-ERSTELLUNG:
    1. AMNESIE VERBOTEN: Erfinde NIEMALS Variablen wie 'SpalteA'. Du hast im Input das Feld "original_code_mapping" erhalten. Nutze für IF-Bedingungen AUSSCHLIESSLICH die echte Logik aus diesem Mapping!
    2. KONFLIKT-LÖSUNG (WICHTIG!): Wenn in einer Tabelle zwei Zeilen exakt dieselben Vorbedingungen (Bedingungsspalten) haben, aber unterschiedliche Zielwerte generieren, darfst du dafür keine Tabelle bauen! Du MUSST das im avc_code mit einem IN-Operator als Multi-Value Zuweisung auflösen. 
       Beispiel: pc.Merkmal IN ('Wert1', 'Wert2') IF pc.Farbe = 'blau'.
    3. STANDALONE CODE: Bei "NO_TABLE" schreibst du für jeden Eintrag aus "original_code_mapping" ein sauberes IF-Statement nach AVC Syntax.
    
    4. STRIKTE AVC-SYNTAX (WICHTIG!):
       - Die alte LO-VC Syntax 'specified Merkmal' MUSST du in 'SPECIFIED(pc.Merkmal)' übersetzen.
       - Die alte LO-VC Syntax 'ne' MUSST du in '<>' (Ungleich) übersetzen.
       - Alle Merkmale müssen im Constraint-Code das Präfix 'pc.' erhalten (z.B. pc.K40_KO).
       - Logische Operatoren (AND, OR, NOT) müssen in Großbuchstaben geschrieben werden.
       - Tabellen-Aufrufe haben das Format: TABLE VC_TAB_NAME ( Merkmal1 = pc.Merkmal1, Merkmal2 = pc.Merkmal2 ).
    
    Du antwortest IMMER in einem fertigen JSON-Schema für das Dashboard.''',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)

# =====================================================================
# AGENT 3: Der AVC Validator (Quality Gate)
# =====================================================================
avc_validator = Agent(
    role='SAP AVC Senior Quality Assurance',
    goal='Validiere den generierten JSON-Output des Synthesizers auf AVC-Syntax-Verstöße und LO-VC Altlasten und korrigiere diese.',
    backstory='''Du bist der kritischste Code-Reviewer im SAP S/4HANA Umfeld.
    Der Synthesizer vor dir macht manchmal Fehler bei der Übersetzung von LO-VC nach AVC.
    
    DEINE PRÜFROUTINE FÜR DEN WERT IN "avc_code":
    1. Sind noch LO-VC Ausdrücke wie 'specified xyz' vorhanden? Korrigiere sie zu 'SPECIFIED(pc.xyz)'.
    2. Wurde der Zuweisungs-Operator '=' korrekt verwendet?
    3. Fehlt bei irgendeinem Merkmal das 'pc.' Präfix? Wenn ja, ergänze es zwingend!
    4. Gibt es logische Operatoren in Kleinbuchstaben (and, or)? Ändere sie zu Großbuchstaben (AND, OR).
    5. Gibt es noch ein 'ne' anstelle von '<>'? Tausche es aus.
    
    Du nimmst das JSON des Synthesizers, verbesserst den "avc_code" (falls nötig) und gibst exakt dasselbe JSON-Format als Output zurück, damit es in Excel geschrieben werden kann.''',
    llm=sap_llm,
    verbose=True,
    allow_delegation=False
)