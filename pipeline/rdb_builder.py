import sqlite3
import pandas as pd
import re

class RelationalDBBuilder:
    def __init__(self, pha_path, nodes_path, ar_path, gap_path, sqlite_path):
        self.pha_path = pha_path
        self.nodes_path = nodes_path
        self.ar_path = ar_path
        self.gap_path = gap_path
        self.sqlite_path = sqlite_path

    def extract_all_pids(self, pid_string):
        if not pid_string or pd.isna(pid_string): return []
        matches = re.findall(r'\d{2}-[A-Za-z0-9]+-\d+', str(pid_string))
        return list(set(matches))

    def clean_single_pid(self, pid_str):
        if not pid_str or pd.isna(pid_str): return ""
        return re.sub(r'(?i)redline|rev\s*\d+', '', str(pid_str)).strip()

    def run(self):
        print("Starting SQLite Relational Database Build (3NF Legacy Mode)...")
        
        df_pha = pd.read_csv(self.pha_path, dtype=str).fillna('')
        df_nodes = pd.read_csv(self.nodes_path, dtype=str).fillna('')
        df_ar = pd.read_csv(self.ar_path, dtype=str).fillna('')
        
        try:
            df_gap = pd.read_csv(self.gap_path)
        except Exception:
            df_gap = pd.DataFrame()

        # 1. Drawings & Node_Drawing_Map
        df_nodes['PID_List'] = df_nodes['P&ID'].apply(self.extract_all_pids)
        df_ndm = df_nodes[['Node_ID', 'PID_List']].explode('PID_List').dropna(subset=['PID_List'])
        df_ndm.rename(columns={'PID_List': 'PID_Number'}, inplace=True)
        df_ndm = df_ndm[(df_ndm['PID_Number'] != '') & (df_ndm['Node_ID'] != '')].drop_duplicates()

        if 'P&ID' in df_ar.columns:
            df_ar['PID_Number'] = df_ar['P&ID'].apply(self.clean_single_pid)
        else:
            df_ar['PID_Number'] = ""

        all_pids = pd.concat([df_ndm['PID_Number'], df_ar['PID_Number']])
        df_drawings = pd.DataFrame({'PID_Number': all_pids.dropna().unique()})
        df_drawings = df_drawings[df_drawings['PID_Number'] != '']

        # 2. Nodes
        df_nodes_table = df_nodes[['Node_ID', 'Node_Text']].drop_duplicates(subset=['Node_ID'])
        df_nodes_table = df_nodes_table[df_nodes_table['Node_ID'] != '']

        # 3. Equipment & Node_Equipment_Map
        df_equipment = df_nodes[['Equipment_Tag', 'Equipment_Description', 'Design_Conditions']].drop_duplicates(subset=['Equipment_Tag'])
        df_equipment = df_equipment[df_equipment['Equipment_Tag'] != '']
        
        df_nem = df_nodes[['Node_ID', 'Equipment_Tag']].drop_duplicates()
        df_nem = df_nem[(df_nem['Node_ID'] != '') & (df_nem['Equipment_Tag'] != '')]

        # 4. Hazard_Scenarios
        haz_cols = ['Consequence_ID', 'Node_ID', 'Deviation_ID', 'Deviation_Text', 'Cause_ID', 'Cause_Text', 'Consequence_Text', 'CAT', 'S', 'L', 'R']
        for c in haz_cols:
            if c not in df_pha.columns: df_pha[c] = ""
            
        df_hazards = df_pha[haz_cols].drop_duplicates(subset=['Consequence_ID'])
        df_hazards = df_hazards[df_hazards['Consequence_ID'] != '']

        # 5. Safeguards & Scenario_Safeguard_Map
        df_safeguards = df_pha[['Safeguard_ID', 'Safeguard_Text']].drop_duplicates(subset=['Safeguard_ID'])
        df_safeguards = df_safeguards[df_safeguards['Safeguard_ID'] != '']
        
        df_ssm = df_pha[['Consequence_ID', 'Safeguard_ID']].drop_duplicates()
        df_ssm = df_ssm[(df_ssm['Consequence_ID'] != '') & (df_ssm['Safeguard_ID'] != '')]

        # 6. AR_Master
        df_ar_master = df_ar.copy()
        df_ar_master.rename(columns={
            'Signal/Instrument Tag': 'Signal_Tag',
            'Alarm Descriptor (if used)': 'Alarm_Descriptor',
            'EU Lo (update)': 'EU_Lo_Update',
            'EU Hi (update)': 'EU_Hi_Update',
            'Mode of Operation (Blank = Normal)': 'Mode_of_Operation'
        }, inplace=True)
        df_ar_master.columns = df_ar_master.columns.str.replace(r'[^a-zA-Z0-9_]', '_', regex=True)
        if 'Signal_Tag' in df_ar_master.columns:
            df_ar_master = df_ar_master.drop_duplicates(subset=['Signal_Tag'])
        
        # Write to SQLite
        with sqlite3.connect(self.sqlite_path) as conn:
            df_drawings.to_sql('Drawings', conn, if_exists='replace', index=False)
            df_ndm.to_sql('Node_Drawing_Map', conn, if_exists='replace', index=False)
            df_nodes_table.to_sql('Nodes', conn, if_exists='replace', index=False)
            df_equipment.to_sql('Equipment', conn, if_exists='replace', index=False)
            df_nem.to_sql('Node_Equipment_Map', conn, if_exists='replace', index=False)
            df_hazards.to_sql('Hazard_Scenarios', conn, if_exists='replace', index=False)
            df_safeguards.to_sql('Safeguards', conn, if_exists='replace', index=False)
            df_ssm.to_sql('Scenario_Safeguard_Map', conn, if_exists='replace', index=False)
            df_ar_master.to_sql('AR_Master', conn, if_exists='replace', index=False)
            
            if not df_gap.empty:
                df_gap.to_sql('Gap_Analysis_Report', conn, if_exists='replace', index=False)

        print(f"[OK] RDB Build Complete! Database saved to: {self.sqlite_path}")
