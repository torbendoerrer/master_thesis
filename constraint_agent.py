import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from langchain_google_genai import ChatGoogleGenerativeAI

# API-Key laden
load_dotenv()
gemini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0) # Passe das Modell an dein verfügbares an

# 1. Unser Input: Das exakte Ergebnis vom Analyst-Agenten (Hardcoded für den Test)
analyst_output = """
{
  "constraint_lines": [
    "$self.TM_EDGE_LENGTH = 2 * ($self.TM_LENGTH + $self.TM_WIDTH)",
    "$self.TM_FORM = '030'"
  ]
}
"""

# 2. Der verbesserte Agent (The Constraint Builder mit Few-Shot)
builder_agent = Agent(
    role='SAP AVC Constraint Builder',
    goal='Übersetze imperative LO-VC-Zuweisungen in striktes, deklaratives AVC-Beziehungswissen.',
    backstory='''Du bist ein hochspezialisierter SAP-Architekt für S/4HANA.
    Deine Aufgabe ist die syntaktische Transformation von alten LO-VC Zuweisungen in moderne AVC-Constraints.
    
    Du wendest strikt folgende Syntax-Regeln für AVC an:
    1. Ein Constraint beginnt IMMER mit den Blöcken OBJECTS:, CONDITION: und RESTRICTIONS:.
    2. Die Zuweisung von Werten in den RESTRICTIONS erfolgt mit '='.
    3. Jeder Befehl im RESTRICTIONS Block MUSS mit einem Punkt (.) enden, nicht mit einem Komma!
    4. Wenn der Constraint keine IF-Bedingungen enthält, lass den Block CONDITION: komplett weg.
    5. Wenn es mehrere Zuweisungen unter RESTRICTIONS: gibt, trenne diese zwingend mit einem Komma (,). Nur die allerletzte Zeile des Constraints darf mit einem Punkt (.) enden.
    
    HIER IST EIN BEISPIEL FÜR DEINE ÜBERSETZUNG:
    Input (LO-VC):
    $self.TM_EDGE_LENGTH = 2 * ($self.TM_LENGTH + $self.TM_WIDTH)
    
    Output (AVC):
    CONSTRAINT CHG_EDGE_LENGTH
    OBJECTS:
      ?O IS_A (300) MY_CLASS
    RESTRICTIONS:
      ?O.TM_EDGE_LENGTH = 2 * (?O.TM_LENGTH + ?O.TM_WIDTH).
    ''',
    verbose=True,
    allow_delegation=False,
    llm=gemini_llm
)

# 3. Der Task
build_task = Task(
    description=f'''
    Nimm die folgenden Code-Zeilen aus dem JSON-Array "constraint_lines":
    {analyst_output}
    
    Generiere daraus einen korrekten AVC-Constraint-Block. 
    Achte darauf, dass die Zuweisungen syntaktisch korrekt als deklarative Restriktionen umgesetzt werden.
    ''',
    expected_output='Ein String, der den fertigen AVC-Code für die Constraints enthält.',
    agent=builder_agent
)

# 4. Die Crew starten (besteht aktuell nur aus dem Builder)
builder_crew = Crew(
    agents=[builder_agent],
    tasks=[build_task],
    verbose=True
)

result = builder_crew.kickoff()

print("\n######################")
print("ERGEBNIS DES BUILDERS:")
print(result)