import pandas as pd
import re
import os

class PhaStudyFlattener:
    def __init__(self, input_csv, output_csv):
        self.input_csv = input_csv
        self.output_csv = output_csv

    def clean_text(self, text):
        if pd.isna(text): return ""
        text = str(text).strip()
        text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
        return text

    def extract_equipment_specs(self, design_text, equip_tag):
        if not design_text or not equip_tag:
            return ""

        tag_pattern = r'(?:^|\n)' + re.escape(equip_tag) + r'[^:]*:\s*\n(.*?)(?=\n[A-Z0-9]+-[A-Z0-9]+|$)'
        match = re.search(tag_pattern, design_text, re.DOTALL)
        if match:
            return match.group(1).strip()

        base_tag = re.sub(r'[A-Za-z/]+$', '', equip_tag)
        if base_tag != equip_tag and len(base_tag) > 3:
            pattern2 = r'(?:^|\n)' + re.escape(base_tag) + r'[^:]*:\s*\n(.*?)(?=\n[A-Z0-9]+-[A-Z0-9]+|$)'
            match2 = re.search(pattern2, design_text, re.DOTALL)
            if match2:
                return match2.group(1).strip()

        return ""

    def run(self):
        print("Starting PSM PHA Study Flatten...")
        
        if not os.path.exists(self.input_csv):
            raise FileNotFoundError(f"File not found: {self.input_csv}")

        df_raw = pd.read_csv(self.input_csv, header=None)
        data = []

        current_node = None
        current_design = None
        current_drawing = None

        for idx, row in df_raw.iterrows():
            node_val = str(row[0]).strip() if pd.notna(row[0]) else ""
            design_val = str(row[9]).strip() if pd.notna(row[9]) else ""
            drawing_val = str(row[13]).strip() if pd.notna(row[13]) else ""
            tag_val = str(row[16]).strip() if pd.notna(row[16]) else ""
            desc_val = str(row[17]).strip() if pd.notna(row[17]) else ""

            if re.match(r'^\d+\.\s*Node', node_val):
                current_node = self.clean_text(node_val)
                current_design = design_val 

                if drawing_val:
                    current_drawing = self.clean_text(drawing_val)

            if drawing_val and not drawing_val.startswith('Drawings'):
                current_drawing = self.clean_text(drawing_val)

            if current_node and tag_val:
                specs = self.extract_equipment_specs(current_design, tag_val)
                specs = self.clean_text(specs)

                data.append({
                    'Node': current_node,
                    'P&ID': current_drawing,
                    'Equipment_Tag': self.clean_text(tag_val),
                    'Equipment_Description': self.clean_text(desc_val),
                    'Design_Conditions': specs if specs else self.clean_text(current_design)
                })

        df_parsed = pd.DataFrame(data)
        if not df_parsed.empty:
            df_parsed = df_parsed[~df_parsed['Equipment_Tag'].str.lower().isin(['tag', 'equipment', ''])]
            df_parsed = df_parsed.drop_duplicates()

            extracted_nodes = df_parsed['Node'].str.extract(r'(?i)^\d*\.?\s*(Node\s*\d+)[\s:-]*(.*)')
            df_parsed['Node_ID'] = extracted_nodes[0].str.title()
            df_parsed['Node_Text'] = extracted_nodes[1].fillna(df_parsed['Node']).str.strip()

            cols = ['Node_ID', 'Node_Text', 'P&ID', 'Equipment_Tag', 'Equipment_Description', 'Design_Conditions']
            df_parsed = df_parsed[cols]

        df_parsed.to_csv(self.output_csv, index=False)
        print(f"Data Engineering complete. Extracted {df_parsed.shape[0]} equipment relationships. Exported to: {self.output_csv}")
