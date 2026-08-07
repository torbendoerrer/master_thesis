import json
from crewai import Task, Crew, Process

# Saubere, versionslose Imports
from utils_final import extract_json_from_output, create_excel_dashboard, extract_known_canon, heavy_preprocessing, create_heuristic_table_plan
from agents_final import global_joiner, synthesizer, avc_validator
# Importiere die neuen Prompts
from prompts import JOINER_PROMPT, SYNTHESIZER_PROMPT, SYNTHESIZER_EXPECTED_OUTPUT, VALIDATOR_PROMPT, VALIDATOR_EXPECTED_OUTPUT

def phase1_symbolic_builder(data, known_canon):
    """Führt das Pre-Processing und die initiale Tabellengenerierung durch."""
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
            
            parsed_plans = create_heuristic_table_plan(processed_char)
            local_plans.extend(parsed_plans)
            
    return local_plans


def phase2_clustering(local_plans):
    """Gruppiert die Baupläne nach Spaltensignaturen (Schema-Matching)."""
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

    print(f"📊 {len(clusters)} potenzielle Master-Tabellen-Cluster gefunden.")
    print(f"🚀 {len(standalone_plans)} Merkmale (oder Sub-Ausreißer) gehen auf die Standalone-Überholspur.")
    return clusters, standalone_plans


def phase3_global_joiner(clusters):
    """Kombiniert redundante Tabellen eines Clusters mittels KI."""
    print("\n" + "="*50)
    print("🤝 [PHASE 3] STARTE GLOBAL JOINER (KI REDUNDANZ-PRÜFUNG)")
    print("="*50)

    master_tables = []
    
    for cluster_key, plans_in_cluster in clusters.items():
        if len(plans_in_cluster) == 1:
            print(f"⏩ Überspringe Joiner für Cluster [{cluster_key}] (Nur 1 Tabelle enthalten)")
            master_tables.append(plans_in_cluster[0])
            continue
            
        print(f"🔄 Joine {len(plans_in_cluster)} Tabellen im Cluster [{cluster_key}]...")
        
        join_task = Task(
            description=JOINER_PROMPT.format(cluster_key=cluster_key, plans_in_cluster=json.dumps(plans_in_cluster, indent=2)),
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
            
    return master_tables


def phase4_synthesize_and_validate(master_tables, standalone_plans):
    """Synthetisiert und validiert den finalen SAP AVC Code."""
    print("\n" + "="*50)
    print("💻 [PHASE 4] STARTE SYNTHESIZER & VALIDATOR")
    print("="*50)

    final_results = {}
    all_final_plans = master_tables + standalone_plans

    for idx, plan in enumerate(all_final_plans):
        target_name = plan.get("zielmerkmal", f"MASTER_TAB_{idx+1}")
        
        # Fallback: Microsoft Excel erlaubt maximal 31 Zeichen für Tabellenblatt-Namen.
        if len(target_name) > 30: 
            target_name = f"MASTER_TAB_{idx+1}"
            
        print(f"✍️  Generiere & Validiere AVC-Code für: {target_name}")

        synth_task = Task(
            description=SYNTHESIZER_PROMPT.format(plan=json.dumps(plan, indent=2)),
            expected_output=SYNTHESIZER_EXPECTED_OUTPUT,
            agent=synthesizer
        )
        
        val_task = Task(
            description=VALIDATOR_PROMPT,
            expected_output=VALIDATOR_EXPECTED_OUTPUT,
            agent=avc_validator
        )

        crew = Crew(agents=[synthesizer, avc_validator], tasks=[synth_task, val_task], process=Process.sequential, verbose=False)
        result = crew.kickoff()
        
        final_data = extract_json_from_output(result.raw)
        if final_data:
            final_results[target_name] = final_data
        else:
            final_results[target_name] = {"herleitung": "JSON Parse Fehler", "tabelle_kopf": [], "tabelle_zeilen": [], "avc_code": "ERROR"}

    return final_results


def process_lovc_json(full_model_file, test_slice_file, output_file):
    """Der zentrale Orchestrator (Main Pipeline)."""
    
    # --- VORBEREITUNG ---
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

    # --- PIPELINE AUSFÜHRUNG ---
    # Phase 1
    local_plans = phase1_symbolic_builder(data, known_canon)
    try:
        with open("debug_1_local_plans.json", "w", encoding="utf-8") as f:
            json.dump(local_plans, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warnung: Konnte debug_1_local_plans.json nicht speichern: {e}")

    # Phase 2
    clusters, standalone_plans = phase2_clustering(local_plans)
    try:
        with open("debug_2_clusters.json", "w", encoding="utf-8") as f:
            json.dump({"clusters": clusters, "standalone": standalone_plans}, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warnung: Konnte debug_2_clusters.json nicht speichern: {e}")

    # Phase 3
    master_tables = phase3_global_joiner(clusters)
    
    # Phase 4
    final_results = phase4_synthesize_and_validate(master_tables, standalone_plans)
    try:
        with open("debug_3_final_data.json", "w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warnung: Konnte debug_3_final_data.json nicht speichern: {e}")

    # Phase 5
    print("\n" + "="*50)
    print("💾 [PHASE 5] ERSTELLE ENTWICKLER-DASHBOARD")
    print("="*50)
    create_excel_dashboard(output_file, final_results)


if __name__ == "__main__":
    FULL_MODEL_JSON = "Beispiel1_Vorbedingungen_full.json" 
    TEST_SLICE_JSON = "Beispiel1_Vorbedingungen.json" 
    OUTPUT_EXCEL = "MAS_Entwickler_Dashboard_final_third_run.xlsx"
    
    process_lovc_json(FULL_MODEL_JSON, TEST_SLICE_JSON, OUTPUT_EXCEL)