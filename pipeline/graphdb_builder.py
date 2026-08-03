import sqlite3
import pandas as pd
import networkx as nx
import pickle
import re
from rapidfuzz import process, fuzz

class GraphDBBuilder:
    def __init__(self, pha_path, nodes_path, sqlite_path):
        self.sqlite_path = sqlite_path

    def run(self):
        print("Starting Graph Database Build (SQL-to-Graph Extraction)...")
        
        conn = sqlite3.connect(self.sqlite_path)
        
        df_nodes = pd.read_sql_query("SELECT * FROM Nodes", conn)
        df_equip = pd.read_sql_query("SELECT * FROM Equipment", conn)
        df_draw = pd.read_sql_query("SELECT * FROM Drawings", conn)
        df_ne_map = pd.read_sql_query("SELECT * FROM Node_Equipment_Map", conn)
        df_nd_map = pd.read_sql_query("SELECT * FROM Node_Drawing_Map", conn)
        df_haz = pd.read_sql_query("SELECT * FROM Hazard_Scenarios", conn)
        df_safe = pd.read_sql_query("SELECT * FROM Safeguards", conn)
        df_ss_map = pd.read_sql_query("SELECT * FROM Scenario_Safeguard_Map", conn)
        
        conn.close()

        G = nx.DiGraph()

        # 1. Build Foundational Nodes
        for _, row in df_nodes.iterrows():
            G.add_node(row['Node_ID'], type="Node", label=row['Node_ID'], title=row['Node_Text'])
            
        for _, row in df_equip.iterrows():
            G.add_node(row['Equipment_Tag'], type="Equipment", label=row['Equipment_Tag'], title=row['Equipment_Description'])
            
        for _, row in df_draw.iterrows():
            G.add_node(row['PID_Number'], type="Drawing", label=row['PID_Number'], title=row['PID_Number'])

        # 2. Build Foundational Edges
        for _, row in df_ne_map.iterrows():
            if row['Node_ID'] in G and row['Equipment_Tag'] in G:
                G.add_edge(row['Node_ID'], row['Equipment_Tag'], relation="CONTAINS")
                
        for _, row in df_nd_map.iterrows():
            if row['Node_ID'] in G and row['PID_Number'] in G:
                G.add_edge(row['Node_ID'], row['PID_Number'], relation="APPEARS_ON")

        valid_tags = df_equip['Equipment_Tag'].dropna().unique().tolist()
        
        def extract_nlp_equipment(text, valid_tags_list):
            if not text or pd.isna(text): return set()
            found = set()
            # 1. Regex chunking: look for anything that vaguely looks like an equipment tag (Letters followed by numbers)
            potential_tags = re.findall(r'\b[A-Za-z]{1,4}[- ]?\d{2,5}[A-Za-z]?\b', str(text))
            
            for ptag in potential_tags:
                # 2. Fuzzy Match against valid ontology
                match = process.extractOne(ptag.upper(), valid_tags_list, scorer=fuzz.token_sort_ratio, score_cutoff=80)
                if match:
                    found.add(match[0]) # Add the exact ontology tag
            
            # 3. Direct substring search as a fallback for exact matches that regex might miss
            text_upper = str(text).upper()
            for vtag in valid_tags_list:
                if f" {vtag} " in f" {text_upper} ":
                    found.add(vtag)
                    
            return found

        # 3. Build HAZOP Logic (Deviation -> Cause -> Consequence)
        for _, row in df_haz.iterrows():
            node_id = row['Node_ID']
            dev_id = f"DEV_{row['Deviation_ID']}"
            cau_id = f"CAU_{row['Cause_ID']}"
            con_id = f"CON_{row['Consequence_ID']}"

            if dev_id not in G:
                G.add_node(dev_id, type="Deviation", label=row['Deviation_Text'], title=row['Deviation_Text'])
                if node_id in G:
                    G.add_edge(node_id, dev_id, relation="EXPERIENCES")

            if cau_id not in G:
                cause_text = str(row['Cause_Text'])
                G.add_node(cau_id, type="Cause", label="Cause", title=cause_text)
                G.add_edge(dev_id, cau_id, relation="CAUSED_BY")
                
                # Extract Reference
                if valid_tags:
                    found_tags = extract_nlp_equipment(cause_text, valid_tags)
                    for t_upper in found_tags:
                        if t_upper in G:
                            G.add_edge(cau_id, t_upper, relation="REFERENCES_EQUIPMENT")

            if con_id not in G:
                con_text = str(row['Consequence_Text'])
                G.add_node(con_id, type="Consequence", label=f"Risk: {row['R']}", title=con_text, severity=row['S'], likelihood=row['L'], risk=row['R'])
                G.add_edge(cau_id, con_id, relation="RESULTS_IN")
                
                # Extract Reference
                if valid_tags:
                    found_tags = extract_nlp_equipment(con_text, valid_tags)
                    for t_upper in found_tags:
                        if t_upper in G:
                            G.add_edge(con_id, t_upper, relation="REFERENCES_EQUIPMENT")

        # 4. Build Safeguards
        for _, row in df_safe.iterrows():
            sg_id = row['Safeguard_ID']
            raw_safeguard = str(row['Safeguard_Text'])
            G.add_node(sg_id, type="Safeguard", label="Safeguard", title=raw_safeguard)
            
            # Extract Reference
            if valid_tags:
                found_tags = extract_nlp_equipment(raw_safeguard, valid_tags)
                for t_upper in found_tags:
                    if t_upper in G:
                        G.add_edge(sg_id, t_upper, relation="REFERENCES_EQUIPMENT")
                        
        # Connect Safeguards to Consequences via M:N Map
        for _, row in df_ss_map.iterrows():
            con_id = f"CON_{row['Consequence_ID']}"
            sg_id = row['Safeguard_ID']
            if sg_id in G and con_id in G:
                G.add_edge(sg_id, con_id, relation="MITIGATES")

        graph_path = self.sqlite_path.replace('.db', '.graphml')
        nx.write_graphml(G, graph_path)

        print(f"[OK] Graph DB Built with {G.number_of_nodes()} Nodes and {G.number_of_edges()} Edges.")
        print(f"Graph Saved to: {graph_path}")
