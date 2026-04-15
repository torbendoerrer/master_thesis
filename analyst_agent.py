import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from langchain_google_genai import ChatGoogleGenerativeAI

# 1. Umgebungsvariablen aus der .env Datei laden
load_dotenv()

# Prüfen, ob der Key wirklich geladen wurde (optional, aber gut zur Fehlersuche)
if not os.environ.get("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY wurde nicht gefunden. Bitte prüfe die .env Datei!")

# 2. Das Gemini LLM initialisieren
gemini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# 3. Den Input-Code definieren
legacy_code = """
$self.TM_AUSFUHERUNG ?= '010',
$self.TM_COLOUR ?= 'BLA'
  if $self.TM_AUSFUHERUNG = '020',
$self.TM_EDGE_LENGTH = 2 * ($self.TM_LENGTH + $self.TM_WIDTH),
$self.TM_FORM = '030',
"""

# 4. Den Agenten bauen (The Analyst)
analyst_agent = Agent(
    role='SAP LO-VC Code Analyst',
    goal='Analysiere imperativen Legacy-Code und trenne ihn semantisch in Prozedur- und Constraint-Bestandteile.',
    backstory='''Du bist ein erfahrener SAP-Architekt. Deine Aufgabe ist es, alten LO-VC Code für die Migration nach AVC vorzubereiten. 
    Du kennst die wichtigste Regel: 
    - Befehle mit '?=' (weiche Vorschlagswerte) müssen in einer 'Prozedur' bleiben.
    - Befehle mit '=' (harte Wertsetzungen und Berechnungen) müssen in einen 'Constraint' ausgelagert werden.
    Du analysierst den Code zeilenweise anhand der Kommas.''',
    verbose=True,
    allow_delegation=False,
    llm=gemini_llm
)

# 5. Den Task definieren
splitting_task = Task(
    description=f'''
    Analysiere den folgenden LO-VC Code:
    {legacy_code}
    
    Teile die Befehle nach folgenden Regeln auf:
    1. Alles was '?=' enthält, gehört in die Kategorie "Procedure".
    2. Alles was ein hartes '=' enthält (wie Zuweisungen oder Berechnungen), gehört in die Kategorie "Constraint".
    Achte darauf, dass Bedingungen (if ...) beim jeweiligen Befehl bleiben.
    ''',
    expected_output='Ein sauberes JSON-Format mit zwei Schlüsseln: "procedure_lines" (Liste der Code-Zeilen) und "constraint_lines" (Liste der Code-Zeilen).',
    agent=analyst_agent
)

# 6. Die Crew starten
migration_crew = Crew(
    agents=[analyst_agent],
    tasks=[splitting_task],
    verbose=True
)

# Ausführung starten
result = migration_crew.kickoff()

print("\n######################")
print("ERGEBNIS DES AGENTEN:")
print(result)