import pandas as pd
import re
import os
import traceback

class HazopFlattener:
    def __init__(self, input_csv, output_hazop_csv):
        self.input_csv = input_csv
        self.output_hazop_csv = output_hazop_csv

    def run(self):
        print("Starting PSM HAZOP Flatten...")
        try:
            df_hazop, df_nodes = self.process_optimized_hazop_parser(self.input_csv)

            cols = [
                "Node_ID",
                "Deviation_ID", "Deviation_Text",
                "Cause_ID", "Cause_Text",
                "Consequence_ID", "Consequence_Text",
                "Safeguard_ID", "Safeguard_Text",
                "CAT", "S", "L", "R",
                "Recommendation", "Remark"
            ]
            df_hazop = df_hazop[cols]
            df_hazop.to_csv(self.output_hazop_csv, index=False)
            
            print(f"\nSuccess!")
            print(f"1. Main Database exported to: {self.output_hazop_csv}")

        except Exception as e:
            traceback.print_exc()

    def process_optimized_hazop_parser(self, file_path):
        print("Executing Optimized DOM-Tree Parser...")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}. Please verify the file path.")

        df_raw = pd.read_csv(file_path, header=None)

        # --- DYNAMIC COLUMN ALIGNMENT ---
        df_raw = df_raw.dropna(axis=1, how='all')
        df_raw.columns = range(df_raw.shape[1])

        header_idx = df_raw[df_raw.apply(lambda r: r.astype(str).str.contains('Deviation', case=False).any(), axis=1)].index[0]
        header_row = df_raw.iloc[header_idx].astype(str).str.lower()

        df_data = df_raw.iloc[header_idx + 1:].copy()

        col_map = {}
        for col_idx, val in header_row.items():
            val = str(val).lower()
            if 'deviation' in val: col_map[col_idx] = 'DEV'
            elif 'cause' in val: col_map[col_idx] = 'CAU'
            elif 'consequence' in val: col_map[col_idx] = 'CON'
            elif 'safeguard' in val: col_map[col_idx] = 'SAF'
            elif 'cat' in val: col_map[col_idx] = 'CAT'
            elif val.strip() == 's': col_map[col_idx] = 'S'
            elif val.strip() == 'l': col_map[col_idx] = 'L'
            elif 'r' in val and len(val.strip()) <= 3: col_map[col_idx] = 'R'
            elif 'recommendation' in val: col_map[col_idx] = 'REC'
            elif 'remark' in val: col_map[col_idx] = 'REM'

        rx_dev = re.compile(r'^\d+\.\d+\.')
        rx_cau = re.compile(r'^\d+\.\d+\.\d+\.')
        rx_con = re.compile(r'^\d+\.\d+\.\d+\.\d+\.')
        rx_saf = re.compile(r'^\d+\.')

        hazop_tree = []
        extracted_nodes = []

        active_dev = None
        active_cau = None
        active_con = None

        in_table_body = True
        node_metadata = {"Node_ID": "", "Description": "", "Drawings": ""}
        gathering_mode = None

        for _, row in df_data.iterrows():
            row_str = " ".join([str(x) for x in row if pd.notnull(x)]).strip()

            if "Node:" in row_str or "Drawings" in row_str or "References:" in row_str:
                in_table_body = False

            if "Deviation" in str(row.get(list(col_map.keys())[0] if col_map else "", "")) or "Causes" in str(row.get(list(col_map.keys())[1] if len(col_map)>1 else "", "")):
                in_table_body = True
                continue

            if not in_table_body:
                if not row_str: continue

                if "Node:" in row_str:
                    if node_metadata["Node_ID"]:
                        extracted_nodes.append(node_metadata.copy())

                    node_match = re.search(r'Node[\s:]*(\d+)', row_str, re.IGNORECASE)
                    clean_node_id = f"Node {node_match.group(1)}" if node_match else row_str[:15].strip()

                    node_metadata = {"Node_ID": clean_node_id, "Description": row_str + " ", "Drawings": ""}
                    gathering_mode = 'node'

                elif "Drawings" in row_str or "References:" in row_str:
                    gathering_mode = 'drawing'
                    node_metadata["Drawings"] += row_str + " "
                else:
                    if gathering_mode == 'node':
                        node_metadata["Description"] += row_str + " "
                    elif gathering_mode == 'drawing':
                        node_metadata["Drawings"] += row_str + " "
                continue

            r = {col_map[k]: str(row[k]).replace('\n', ' ').strip() if pd.notnull(row[k]) else "" for k in col_map.keys() if k in row}
            if all(v == "" for v in r.values()): continue

            if r.get('DEV'):
                if rx_dev.match(r['DEV']):
                    active_dev = {'text': r['DEV'], 'causes': []}
                    hazop_tree.append(active_dev)
                    active_cau = None
                    active_con = None
                elif active_dev:
                    active_dev['text'] += " " + r['DEV']

            if r.get('CAU'):
                if rx_cau.match(r['CAU']):
                    active_cau = {'text': r['CAU'], 'consequences': []}
                    if active_dev: active_dev['causes'].append(active_cau)
                    active_con = None
                elif active_cau:
                    active_cau['text'] += " " + r['CAU']

            if r.get('CON'):
                if rx_con.match(r['CON']):
                    active_con = {
                        'text': r['CON'], 'safeguards': [],
                        'CAT': "", 'S': "", 'L': "", 'R': "", 'REC': "", 'REM': ""
                    }
                    if active_cau: active_cau['consequences'].append(active_con)
                elif active_con:
                    active_con['text'] += " " + r['CON']

            if active_con:
                if r.get('SAF'):
                    if rx_saf.match(r['SAF']): active_con['safeguards'].append(r['SAF'])
                    elif active_con['safeguards']: active_con['safeguards'][-1] += " " + r['SAF']
                    else: active_con['safeguards'].append(r['SAF'])

                if r.get('CAT') and not active_con['CAT']: active_con['CAT'] = r['CAT']
                if r.get('S') and not active_con['S']: active_con['S'] = r['S']
                if r.get('L') and not active_con['L']: active_con['L'] = r['L']
                if r.get('R') and not active_con['R']: active_con['R'] = r['R']
                if r.get('REC'):
                    if active_con['REC']: active_con['REC'] += " " + r['REC']
                    else: active_con['REC'] = r['REC']
                if r.get('REM'):
                    if active_con['REM']: active_con['REM'] += " " + r['REM']
                    else: active_con['REM'] = r['REM']

        if node_metadata["Node_ID"]:
            extracted_nodes.append(node_metadata.copy())

        flattened_records = []
        for dev in hazop_tree:
            dev_text = dev['text']
            if not dev['causes']:
                flattened_records.append({"Deviation": dev_text, "Cause": "", "Consequence": "", "Safeguard": "", "CAT": "", "S": "", "L": "", "R": "", "Recommendation": "", "Remark": ""})
                continue
            for cau in dev['causes']:
                cau_text = cau['text']
                if not cau['consequences']:
                    flattened_records.append({"Deviation": dev_text, "Cause": cau_text, "Consequence": "", "Safeguard": "", "CAT": "", "S": "", "L": "", "R": "", "Recommendation": "", "Remark": ""})
                    continue
                for con in cau['consequences']:
                    con_text = con['text']
                    if not con['safeguards']:
                        flattened_records.append({"Deviation": dev_text, "Cause": cau_text, "Consequence": con_text, "Safeguard": "", "CAT": con['CAT'], "S": con['S'], "L": con['L'], "R": con['R'], "Recommendation": con['REC'], "Remark": con['REM']})
                        continue
                    for saf in con['safeguards']:
                        flattened_records.append({"Deviation": dev_text, "Cause": cau_text, "Consequence": con_text, "Safeguard": saf, "CAT": con['CAT'], "S": con['S'], "L": con['L'], "R": con['R'], "Recommendation": con['REC'], "Remark": con['REM']})

        df_hazop = pd.DataFrame(flattened_records)

        hierarchy_cols = ['Deviation', 'Cause', 'Consequence', 'Safeguard']

        for col in hierarchy_cols:
            extracted = df_hazop[col].str.extract(r'^([\d\.]+)\s*(.*)')
            df_hazop[f'{col}_ID'] = extracted[0].str.rstrip('.').fillna("")
            df_hazop[f'{col}_Text'] = extracted[1].fillna(df_hazop[col]).str.strip()

        node_nums = df_hazop['Deviation_ID'].str.extract(r'^(\d+)')[0]
        df_hazop.insert(0, 'Node_ID', "Node " + node_nums.astype(str))
        df_hazop['Node_ID'] = df_hazop['Node_ID'].replace('Node nan', '')

        df_nodes = pd.DataFrame(extracted_nodes)
        if not df_nodes.empty:
            df_nodes['Description'] = df_nodes['Description'].str.strip()
            df_nodes['Drawings'] = df_nodes['Drawings'].str.strip()
            df_nodes = df_nodes.drop_duplicates(subset=['Node_ID'], keep='first')

        return df_hazop, df_nodes
