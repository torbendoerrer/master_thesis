import json
import os
from crewai import Task, Crew, Process

from utilsv16 import extract_json_from_output, create_excel_dashboard, extract_known_canon, heavy_preprocessing, create_heuristic_table_plan
from agentsv16 import global_joiner, synthesizer, avc_validator

def process_lovc_json(full_model_file, test_slice_file, output_file, debug_file="debug_preprocessedv16.json"):
    
    # =================================================================
    # VORBEREITUNG
    # =================================================================
    print(f"📖 Lade vollständiges Lexikon aus {full_model_file}...")
    try:
        with open(full_model_file, 'r', encoding='utf-8') as f:
            full_data = json.load(f)
            known_canon = extract_known_canon(full_data)
            print(f"✅ Lexikon geladen: {len(known_canon)} klassifizierte Merkmale gefunden.")
    except Exception as e:
        print(f"❌ Fehler beim Laden des Lexikon-Modells: {e}")
        return

    print(f"\n📂 Lade Test-Daten aus {test_slice_file}...")
    try:
        with open(test_slice_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Test-Daten: {e}")
        return

    # =================================================================
    # PHASE 1: MAP (Pre-Processing & Sub-Clustering)
    # =================================================================
    print("\n" + "="*50)
    print("🧠 [PHASE 1] STARTE SYMBOLISCHEN LOCAL BUILDER (PYTHON)")
    print("="*50)
    
    local_plans = []
    classes = data.get("classes", [])
    
    for cls in classes:
        for i, char in enumerate(cls.get("characteristics", [])):
            char_name = char.get("name", "Unknown")
            
            if not any("dependency" in val and len(val["dependency"]) > 0 for val in char.get("values", [])):
                continue
                
            print(f"⚙️ Verarbeite Merkmal: {char_name}")
            processed_char = heavy_preprocessing(char, known_canon)
            cls["characteristics"][i] = processed_char 
            
            # Sub-Clustering liefert nun eine Liste von Plänen zurück
            parsed_plans = create_heuristic_table_plan(processed_char)
            local_plans.extend(parsed_plans)

    try:
        with open("debug_1_local_plansv16.json", "w", encoding="utf-8") as f:
            json.dump(local_plans, f, indent=2)
    except Exception:
        pass

    # =================================================================
    # PHASE 2: CLUSTERING (Global Bucketing)
    # =================================================================
    print("\n" + "="*50)
    print("🗂️  [PHASE 2] CLUSTERING DER BAUPLÄNE (Schema-Matching)")
    print("="*50)

    clusters = {}
    standalone_plans = []

    for plan in local_plans:
        if plan.get("decision") == "NO_TABLE":
            standalone_plans.append(plan)
        else:
            cols = plan.get("bedingungs_spalten", [])
            cluster_key = ", ".join(sorted(cols))
            
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            clusters[cluster_key].append(plan)

    try:
        with open("debug_2_clustersv16.json", "w", encoding="utf-8") as f:
            json.dump({"clusters": clusters, "standalone": standalone_plans}, f, indent=2)
    except Exception:
        pass

    master_tables = []
    print(f"📊 {len(clusters)} potenzielle Master-Tabellen-Cluster gefunden.")
    print(f"🚀 {len(standalone_plans)} Merkmale (oder Sub-Ausreißer) gehen auf die Standalone-Überholspur.")

    # =================================================================
    # PHASE 3: REDUCE (Der Global Joiner)
    # =================================================================
    print("\n" + "="*50)
    print("🤝 [PHASE 3] STARTE GLOBAL JOINER (KI REDUNDANZ-PRÜFUNG)")
    print("="*50)

    for cluster_key, plans_in_cluster in clusters.items():
        if len(plans_in_cluster) == 1:
            print(f"⏩ Überspringe Joiner für Cluster [{cluster_key}] (Nur 1 Tabelle enthalten)")
            master_tables.append(plans_in_cluster[0])
            continue
            
        print(f"🔄 Joine {len(plans_in_cluster)} Tabellen im Cluster [{cluster_key}]...")
        
        join_task = Task(
            description=f"""
            Hier sind mehrere Tabellen-Baupläne, die alle exakt dieselben Spalten nutzen ({cluster_key}).
            Deine Aufgabe ist es, diese Tabellen zu einer einzigen großen Master-Tabelle zusammenzufügen.
            Achte auf Redundanzen (identische Zeilen).
            
            INPUT BAUPLÄNE:
            {json.dumps(plans_in_cluster, indent=2)}
            """,
            expected_output="Ein kombiniertes JSON-Objekt im selben Schema wie der Input (zielmerkmal, decision, bedingungs_spalten, zeilen_daten, if_constraints_text, original_code_mapping).",
            agent=global_joiner
        )
        
        join_crew = Crew(agents=[global_joiner], tasks=[join_task], process=Process.sequential, verbose=False)
        result = join_crew.kickoff()
        
        joined_plan = extract_json_from_output(result.raw)
        if joined_plan:
            master_tables.append(joined_plan)
        else:
            print(f"⚠️ Fallback: Joiner hat kein valides JSON geliefert. Behalte Original-Tabellen.")
            master_tables.extend(plans_in_cluster)

    # =================================================================
    # PHASE 4: SYNTHESE & VALIDIERUNG
    # =================================================================
    print("\n" + "="*50)
    print("💻 [PHASE 4] STARTE SYNTHESIZER & VALIDATOR")
    print("="*50)

    final_results = {}
    all_final_plans = master_tables + standalone_plans

    for idx, plan in enumerate(all_final_plans):
        target_name = plan.get("zielmerkmal", f"MASTER_TAB_{idx+1}")
        if len(target_name) > 30: 
            target_name = f"MASTER_TAB_{idx+1}"
            
        print(f"✍️  Generiere & Validiere AVC-Code für: {target_name}")

        synth_task = Task(
            description=f"""
            Übersetze diesen Bauplan in validen SAP AVC Code.
            Folge zwingend den AVC-Syntax-Regeln aus deiner Backstory (SPECIFIED, <>, pc. Prefix, Großschreibung von Operatoren).
            Löse Konflikte in Tabellen durch "IN (...)" auf.
            Nutze für NO_TABLE Entscheidungen NUR das "original_code_mapping"!
            
            BAUPLAN:
            {json.dumps(plan, indent=2)}
            """,
            expected_output="""Ein reines JSON Objekt:
            {
              "herleitung": "Erklärung deines Gedankengangs",
              "tabelle_kopf": ["Spalte1", "Spalte2", ...],
              "tabelle_zeilen": [["Wert1", "Wert2", ...], ...],
              "avc_code": "Der finale SAP AVC Code"
            }""",
            agent=synthesizer
        )
        
        val_task = Task(
            description="""
            Nimm den Output des Synthesizers. Prüfe den Wert im Feld "avc_code" streng nach AVC-Regeln:
            - Keine 'specified' ohne Klammern (muss SPECIFIED(pc.xyz) sein)
            - Keine 'ne' (muss <> sein)
            - Kein fehlendes 'pc.' Präfix bei den Merkmalen
            Korrigiere den Code, falls nötig, und gib das exakt selbe JSON-Format zurück.
            """,
            expected_output="Ein validiertes JSON Objekt mit denselben Schlüsseln wie der Input.",
            agent=avc_validator
        )

        crew = Crew(agents=[synthesizer, avc_validator], tasks=[synth_task, val_task], process=Process.sequential, verbose=False)
        result = crew.kickoff()
        
        final_data = extract_json_from_output(result.raw)
        if final_data:
            final_results[target_name] = final_data
        else:
            final_results[target_name] = {"herleitung": "JSON Parse Fehler", "tabelle_kopf": [], "tabelle_zeilen": [], "avc_code": "ERROR"}

    try:
        with open("debug_3_final_datav16.json", "w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=2)
    except Exception:
        pass

    # =================================================================
    # PHASE 5: EXCEL EXPORT
    # =================================================================
    print("\n" + "="*50)
    print("💾 [PHASE 5] ERSTELLE ENTWICKLER-DASHBOARD")
    print("="*50)
    
    create_excel_dashboard(output_file, final_results)

if __name__ == "__main__":
    FULL_MODEL_JSON = "Beispiel1_Vorbedingungen_full.json" 
    TEST_SLICE_JSON = "Beispiel1_Vorbedingungen.json" 
    
    OUTPUT_EXCEL = "MAS_Entwickler_Dashboard_Finalv16.xlsx"
    
    process_lovc_json(FULL_MODEL_JSON, TEST_SLICE_JSON, OUTPUT_EXCEL)