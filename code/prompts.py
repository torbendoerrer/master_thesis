# =====================================================================
# PROMPTS FÜR DEN GLOBAL JOINER (PHASE 3)
# =====================================================================

JOINER_PROMPT = """
Hier sind mehrere Tabellen-Baupläne, die alle exakt dieselben Spalten nutzen ({cluster_key}).
Deine Aufgabe ist es, diese Tabellen zu einer einzigen großen Master-Tabelle zusammenzufügen.
Achte auf Redundanzen (identische Zeilen).

INPUT BAUPLÄNE:
{plans_in_cluster}
"""

# =====================================================================
# PROMPTS FÜR DEN SYNTHESIZER (PHASE 4)
# =====================================================================

SYNTHESIZER_PROMPT = """
Übersetze diesen Bauplan in validen SAP AVC Code.
Folge zwingend den AVC-Syntax-Regeln aus deiner Backstory (SPECIFIED, <>, Großschreibung von Operatoren).
Wenn die Entscheidung "TABLE" ist, MUSS ein TABLE-Aufruf generiert werden.
Nutze für Zuweisungen IMMER das "echtes_zielmerkmal".

WICHTIGE SYNTAX-REGEL FÜR STANDALONE-CODE (NO_TABLE):
Schreibe Zuweisungen IMMER nach dem Muster "Zuweisung IF Bedingung." 
Beispiel RICHTIG: K40_KO = '09' IF (K40_pl IN ('d1', 'd2')).
Beispiel FALSCH:  IF (K40_pl IN ('d1', 'd2')) THEN K40_KO = '09'.

BAUPLAN:
{plan}
"""

SYNTHESIZER_EXPECTED_OUTPUT = """Ein reines JSON Objekt:
{
  "herleitung": "Erklärung deines Gedankengangs",
  "tabelle_kopf": ["Spalte1", "Spalte2", ...],
  "tabelle_zeilen": [["Wert1", "Wert2", ...], ...],
  "avc_code": "Der finale SAP AVC Code"
}"""

# =====================================================================
# PROMPTS FÜR DEN VALIDATOR (PHASE 4)
# =====================================================================

VALIDATOR_PROMPT = """
Nimm den Output des Synthesizers. Prüfe den Wert im Feld "avc_code" streng nach AVC-Regeln:
- Keine 'specified' ohne Klammern (muss SPECIFIED(xyz) sein)
- Keine 'ne' (muss <> sein)
- Großschreibung von Operatoren (AND, OR, NOT, IN, IF)
- Bei einzelnen Zuweisungen steht das IF zwingend HINTER der Zuweisung (Merkmal = Wert IF Bedingung)
Korrigiere den Code, falls nötig, und gib das exakt selbe JSON-Format zurück.
"""

VALIDATOR_EXPECTED_OUTPUT = "Ein validiertes JSON Objekt mit denselben Schlüsseln wie der Input."