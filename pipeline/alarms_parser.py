import pandas as pd
import re
from sentence_transformers import SentenceTransformer, util
import torch

class AlarmsParser:
    def __init__(self, input_csv, output_csv, model_name='all-MiniLM-L6-v2'):
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.model_name = model_name

        self.ASSET_BLACKLIST = ['PM', 'TK', 'EX', 'V', 'CM', 'HE', 'ST', 'CP', 'B', 'K', 'LP', 'AT', 'GPS']
        self.MNEMONIC_MAP = {
            'HIGH HIGH': 'HIHI', 'HIHI': 'HIHI', 'LAHH': 'HIHI', 'PAHH': 'HIHI',
            'HIGH': 'HI', 'HI': 'HI', 'LAH': 'HI', 'PAH': 'HI',
            'LOW LOW': 'LOLO', 'LOLO': 'LOLO', 'LALL': 'LOLO', 'PALL': 'LOLO',
            'LOW': 'LO', 'LO': 'LO', 'LAL': 'LO', 'PAL': 'LO',
            'TRIP': 'TRP', 'SHUTDOWN': 'TRP', 'INTERLOCK': 'TRP', 'ESD': 'TRP'
        }
        self.rx_tag = re.compile(r'\b([A-Z]{2,5})\s*[-_]?\s*(\d{4,5})((?:/\d{2,5})*)\s*([A-Z])?\b', re.IGNORECASE)

        self.target_phrases = [
            "automatic safety shutdown",
            "process alarm alerts operator",
            "interlock trip action",
            "emergency shutdown ESD activates",
            "high low alarm differential"
        ]

    def normalize_tag_strict(self, prefix, loop):
        return f"{prefix.upper()}{loop}"

    def expand_grouped_tags(self, prefix, loop, slash_group, suffix):
        if prefix.upper() in self.ASSET_BLACKLIST:
            return []

        tags = [self.normalize_tag_strict(prefix, loop)]
        if slash_group:
            extra_loops = slash_group.strip('/').split('/')
            for extra in extra_loops:
                new_loop = loop[:-len(extra)] + extra
                tags.append(self.normalize_tag_strict(prefix, new_loop))
        return tags

    def determine_centum_type(self, tag, text):
        t, s = tag.upper(), text.upper()
        if 'HH' in t: return 'HIHI'
        if 'LL' in t: return 'LOLO'
        if 'AH' in t: return 'HI'
        if 'AL' in t: return 'LO'
        
        for key, val in self.MNEMONIC_MAP.items():
            if key in s: return val
        return 'ALM'

    def run(self):
        print("Starting Alarms Parsing Engine...")
        model = SentenceTransformer(self.model_name)
        target_embeddings = model.encode(self.target_phrases, convert_to_tensor=True)

        df = pd.read_csv(self.input_csv)
        
        safeguard_col = 'Safeguard_Text' if 'Safeguard_Text' in df.columns else 'Safeguard'
        cause_col = 'Cause_Text' if 'Cause_Text' in df.columns else 'Cause'
        conseq_col = 'Consequence_Text' if 'Consequence_Text' in df.columns else 'Consequence'

        aggregation_functions = {
            'Node_ID': lambda x: ', '.join(x.unique()),
            cause_col: lambda x: ' | '.join(x.unique().astype(str)),
            conseq_col: lambda x: ' | '.join(x.unique().astype(str)),
            'S': 'max',
            'L': 'max',
            'R': 'max'
        }

        df_unique = df.dropna(subset=[safeguard_col]).groupby(safeguard_col).agg(aggregation_functions).reset_index()
        print(f"Pruned original data down to {len(df_unique)} unique functional safeguards.")

        records = []

        for _, row in df_unique.iterrows():
            text = str(row[safeguard_col])
            matches = self.rx_tag.findall(text)
            found_tag_in_row = False

            text_emb = model.encode(text, convert_to_tensor=True)
            max_score = util.cos_sim(text_emb, target_embeddings).max().item()

            for prefix, loop, slashes, suffix in matches:
                tags = self.expand_grouped_tags(prefix, loop, slashes, suffix)
                for t in tags:
                    if max_score > 0.35:
                        found_tag_in_row = True
                        rec = row.to_dict()
                        rec['Extracted_Tag_Clean'] = t
                        rec['Alarm_Type'] = self.determine_centum_type(t, text)
                        rec['Technique'] = 'Tier 1/2: Deterministic'
                        rec['Semantic_Score'] = 'N/A'
                        rec['Confidence'] = 'High'
                        records.append(rec)

            if not found_tag_in_row and max_score > 0.6:
                rec = row.to_dict()
                rec['Extracted_Tag_Clean'] = 'NO_TAG_FOUND'
                rec['Alarm_Type'] = self.determine_centum_type('NONE', text)
                rec['Technique'] = 'Tier 3: Semantic Only'
                rec['Semantic_Score'] = round(max_score, 4)
                rec['Confidence'] = 'Medium'
                records.append(rec)

        df_output = pd.DataFrame(records)
        
        if not df_output.empty:
            # Rename for GapAnalyzer compatibility
            df_output = df_output.rename(columns={
                safeguard_col: 'Safeguard_Text',
                cause_col: 'Cause_Text',
                conseq_col: 'Consequence_Text'
            })
            
            final_cols = [
                'Extracted_Tag_Clean',
                'Alarm_Type',
                'Technique',
                'Confidence',
                'Safeguard_Text',
                'Semantic_Score',
                'Cause_Text',
                'Consequence_Text',
                'Node_ID',
                'S', 'L', 'R'
            ]
            df_output = df_output[[c for c in final_cols if c in df_output.columns]]
            df_output.to_csv(self.output_csv, index=False)
            print(f"[OK] Master Alarm Register saved to: {self.output_csv}")
        else:
            print("No Alarms extracted.")
