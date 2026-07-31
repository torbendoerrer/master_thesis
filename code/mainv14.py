import json
import os
from crewai import Task, Crew, Process

# --- Importiere unsere ausgelagerten Module ---
from utilsv14 import extract_json_from_output, create_excel_dashboard, extract_known_canon, heavy_preprocessing
from agentsv14 import local_builder, global_joiner, synthesizer

def process_lovc_json(full_model_file, test_slice_file, output_file, debug_file="debug_preprocessedv14.json"):
    # 1. Lade das RIESIGE Modell NUR für das Wörterbuch (known_canon)
    print(f"\n📚 Lade komplettes Modell für Known Canon: {full_model_file}")
    try:
        with open(full_model_file, 'r', encoding='utf-8') as f:
            full_data = json.load(f)
            known_canon = extract_known_canon(full_data)
            print(f"🔍 System hat {len(known_canon)} klassifizierte Merkmale im gesamten Modell gefunden.")
    except Exception as e:
        print(f"❌ Fehler beim Laden des vollen Modells: {e}")
        return

    # 2. Lade den kleinen Test-Slice für die eigentliche Verarbeitung
    print(f"\n📂 Lade Test-Slice JSON für Verarbeitung: {test_slice_file}")
    try:
        with open(test_slice_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Test-JSON: {e}")
        return

    # =================================================================
    # PHASE 0: PYTHON PRE-PROCESSING (Der SymPy-Compiler)
    # =================================================================
    
    for cls in data.get("classes", []):
        for i, char in enumerate(cls.get("characteristics", [])):
            cls["characteristics"][i] = heavy_preprocessing(char, known_canon)
            
    try:
        with open(debug_file, 'w', encoding='utf-8') as debug_f:
            json.dump(data, debug_f, indent=2)
        print(f"💾 [TRACE 0] Pre-Processor Output gespeichert unter: {debug_file}")
    except Exception as e:
        print(f"⚠️ Konnte Debug-Datei nicht speichern: {e}")

    # =================================================================
    # PHASE 1: MAP (Local Table Builder)
    # =================================================================
    print("\n" + "="*50)
    print("🧠 [PHASE 1] STARTE LOCAL BUILDER (MAP)")
    print("="*50)
    
    local_plans = []
    classes = data.get("classes", [])
    
    for cls in classes:
        for char in cls.get("characteristics", []):
            char_name = char.get("name", "Unknown")
            
            if not any("dependency" in val and len(val["dependency"]) > 0 for val in char.get("values", [])):
                continue
                
            print(f"⚙️  Erstelle lokalen Bauplan für: {char_name}")
            chunk_json_str = json.dumps(char, indent=2)
            
            task_local = Task(
                description=f'''Analysiere das Merkmal {char_name}:\n{chunk_json_str}\n
                Entscheide, ob eine Tabelle gebaut wird.
                ANTWORTE ZWINGEND EXAKT IN DIESEM JSON-FORMAT (ohne Markdown-Formatierungen, nur das reine JSON):
                {{
                  "zielmerkmal": "{char_name}",
                  "decision": "TABLE", // oder "NO_TABLE"
                  "bedingungs_spalten": ["Spalte1", "Spalte2"], // LEER LASSEN WENN NO_TABLE
                  "zeilen_daten": [["Wert1", "Wert2", "Zielwert"]], // LEER LASSEN WENN NO_TABLE
                  "if_constraints_text": "Dein Text für reine Constraints...", // LEER LASSEN WENN TABLE
                  "original_code_mapping": [
                    {{"wert": "04", "logik": "Das exakte Logik-Feld dieses Wertes aus dem Input..."}}
                  ]
                }}''',
                expected_output='Ein striktes, valides JSON-Objekt.',
                agent=local_builder
            )
            
            crew_local = Crew(agents=[local_builder], tasks=[task_local], verbose=False)
            try:
                result = crew_local.kickoff()
                parsed_plan = extract_json_from_output(str(result))
                if parsed_plan:
                    local_plans.append(parsed_plan)
                else:
                    print(f"⚠️  Konnte Bauplan für {char_name} nicht parsen.")
            except Exception as e:
                print(f"❌ Fehler bei {char_name}: {e}")

    try:
        with open("debug_1_local_plansv14.json", "w", encoding="utf-8") as f:
            json.dump(local_plans, f, indent=2)
    except Exception:
        pass

    # =================================================================
    # PHASE 2: CLUSTERING (Python Bucketing)
    # =================================================================
    print("\n" + "="*50)
    print("🗂️  [PHASE 2] PYTHON CLUSTERING (BUCKETING)")
    print("="*50)
    
    buckets = {}
    standalone_items = []
    
    for plan in local_plans:
        if plan.get("decision") == "TABLE":
            cols = tuple(sorted([c.upper() for c in plan.get("bedingungs_spalten", [])]))
            if cols not in buckets:
                buckets[cols] = []
            buckets[cols].append(plan)
        else:
            standalone_items.append(plan)
            
    print(f"📊 {len(buckets)} Master-Tabellen-Cluster gefunden. {len(standalone_items)} Merkmale bleiben als reiner Code.")

    try:
        json_buckets = {", ".join(k): v for k, v in buckets.items()}
        with open("debug_2_clustersv14.json", "w", encoding="utf-8") as f:
            json.dump({"clusters": json_buckets, "standalone": standalone_items}, f, indent=2)
    except Exception:
        pass

    # =================================================================
    # PHASE 3 & 4: REDUCE (Joiner) & SYNTHESE
    # =================================================================
    print("\n" + "="*50)
    print("🔄 [PHASE 3 & 4] GLOBAL JOINER & SYNTHESIZER")
    print("="*50)
    
    dashboard_data = {}
    bucket_counter = 1
    
    for cols, tables in buckets.items():
        bucket_name = f"MASTER_TAB_{bucket_counter}"
        print(f"\n🧩 Verarbeite Cluster: {cols} -> {bucket_name}")
        
        if len(tables) > 1:
            tables_json = json.dumps(tables, indent=2)
            task_join = Task(
                description=f'''Hier sind {len(tables)} Tabellen, die alle die Bedingungsspalten {cols} nutzen:\n{tables_json}\n
                Führe sie zu einer optimierten Master-Tabelle zusammen. Entferne logische Redundanzen.
                Output-Format ist dir freigestellt, hauptsache der Synthesizer versteht es.''',
                expected_output='Eine strukturierte, zusammengeführte Master-Tabelle.',
                agent=global_joiner
            )
            
            task_synth = Task(
                description=f'''Nimm die Master-Tabelle vom Joiner und erstelle den AVC-Code für {bucket_name}.
                Formatiere dein Ergebnis ZWINGEND als JSON nach diesem Schema:
                {{"herleitung": "...", "tabelle_kopf": ["..."], "tabelle_zeilen": [["..."]], "avc_code": "..."}}''',
                expected_output='Ein finales JSON Objekt für das Dashboard.',
                agent=synthesizer
            )
            
            crew_reduce = Crew(agents=[global_joiner, synthesizer], tasks=[task_join, task_synth], process=Process.sequential, verbose=False)
        else:
            single_table = json.dumps(tables[0], indent=2)
            task_synth = Task(
                description=f'''Hier ist der Tabellenbauplan für {tables[0].get('zielmerkmal')}:\n{single_table}\n
                Erstelle den AVC-Code. Formatiere dein Ergebnis ZWINGEND als JSON nach diesem Schema:
                {{"herleitung": "...", "tabelle_kopf": ["..."], "tabelle_zeilen": [["..."]], "avc_code": "..."}}''',
                expected_output='Ein finales JSON Objekt für das Dashboard.',
                agent=synthesizer
            )
            crew_reduce = Crew(agents=[synthesizer], tasks=[task_synth], verbose=False)
            
        try:
            result = crew_reduce.kickoff()
            parsed_json = extract_json_from_output(str(result))
            if parsed_json:
                dashboard_data[bucket_name] = parsed_json
                print(f"✅ {bucket_name} erfolgreich synthetisiert.")
        except Exception as e:
            print(f"❌ Fehler bei Cluster {bucket_name}: {e}")
            
        bucket_counter += 1

    for item in standalone_items:
        char_name = item.get("zielmerkmal", "Unknown")
        print(f"\n📝 Verarbeite reinen Code für: {char_name}")
        
        item_json = json.dumps(item, indent=2)
        task_synth = Task(
            description=f'''Hier ist der Bauplan ohne Tabelle für {char_name}:\n{item_json}\n
            Erstelle den reinen IF-Constraint Code. Formatiere dein Ergebnis ZWINGEND als JSON nach diesem Schema:
            {{"herleitung": "...", "tabelle_kopf": [], "tabelle_zeilen": [], "avc_code": "..."}}''',
            expected_output='Ein finales JSON Objekt für das Dashboard.',
            agent=synthesizer
        )
        crew_standalone = Crew(agents=[synthesizer], tasks=[task_synth], verbose=False)
        try:
            result = crew_standalone.kickoff()
            parsed_json = extract_json_from_output(str(result))
            if parsed_json:
                dashboard_data[char_name] = parsed_json
                print(f"✅ Code für {char_name} erfolgreich synthetisiert.")
        except Exception as e:
            print(f"❌ Fehler bei Standalone {char_name}: {e}")

    try:
        with open("debug_3_final_datav14.json", "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2)
    except Exception:
        pass

    # =================================================================
    # PHASE 5: EXCEL EXPORT
    # =================================================================
    if dashboard_data:
        create_excel_dashboard(output_file, dashboard_data)
    else:
        print("\n⚠️ Keine validen Daten zur Excel-Erstellung gefunden.")

if __name__ == "__main__":
    FULL_MODEL_JSON = "Beispiel1_Vorbedingungen_full.json" 
    TEST_SLICE_JSON = "Beispiel1_Vorbedingungen.json" 
    OUTPUT_FILE = "MAS_Entwickler_Dashboardv14.xlsx"
    
    print("Starte hybride Map-Reduce Multi-Agenten-System Pipeline...")
    process_lovc_json(FULL_MODEL_JSON, TEST_SLICE_JSON, OUTPUT_FILE)