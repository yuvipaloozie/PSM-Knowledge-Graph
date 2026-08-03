import pandas as pd
import numpy as np
import re
from sentence_transformers import SentenceTransformer, util
import torch

class SifParser:
    def __init__(self, input_csv, output_csv, model_name='all-MiniLM-L6-v2'):
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.model_name = model_name

        self.MECH_BLACKLIST = ['PSV', 'PRV', 'RELIEF VALVE', 'RUPTURE DISK', 'CHECK VALVE', 'MECHANICAL STOP']
        self.ALARM_ONLY_KEYWORDS = ['ALERTS OPERATOR', 'PROMPT OPERATOR', 'OPERATOR RESPONSE', 'ALARM ONLY']
        self.SIF_KEYWORDS = ['PERMISSIVE', 'INTERLOCK', 'TRIP', 'SHUTDOWN', 'ESD', 'SIS', 'SIF', 'AUTOMATICALLY CLOSES', 'AUTOMATICALLY STOPS', 'AUTO-CLOSE']

        self.target_phrases = [
            "automatic safety shutdown system",
            "interlock trips the pump and closes the feed valve",
            "emergency shutdown ESD activates on high level",
            "safety instrumented function automatically isolates the process"
        ]

    def is_mechanical_only(self, text):
        text_up = str(text).upper()
        has_mech = any(mech in text_up for mech in self.MECH_BLACKLIST)
        has_sif = any(sif in text_up for sif in self.SIF_KEYWORDS)
        has_af = 'AF-' in text_up
        return has_mech and not (has_sif or has_af)

    def is_alarm_only(self, text):
        text_up = str(text).upper()
        has_alarm_intent = any(alm in text_up for alm in self.ALARM_ONLY_KEYWORDS)
        has_sif = any(sif in text_up for sif in self.SIF_KEYWORDS)
        has_af = 'AF-' in text_up
        is_basic_alarm = ('ALARM' in text_up or ' LEL ' in text_up) and not (has_sif or has_af)
        return (has_alarm_intent or is_basic_alarm)

    def run(self):
        print("Starting SIF Parsing Engine...")
        df_pha = pd.read_csv(self.input_csv)
        
        # Backward compatibility for pipeline column names
        safeguard_col = 'Safeguard_Text' if 'Safeguard_Text' in df_pha.columns else 'Safeguard'
        cause_col = 'Cause_Text' if 'Cause_Text' in df_pha.columns else 'Cause'
        conseq_col = 'Consequence_Text' if 'Consequence_Text' in df_pha.columns else 'Consequence'
        
        df_pha = df_pha.dropna(subset=[safeguard_col])

        print(f"Loading Semantic Model ({self.model_name}) for Tier 2 NLP...")
        model = SentenceTransformer(self.model_name)
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        target_embeddings = model.encode(self.target_phrases, convert_to_tensor=True).to(device)

        results = []

        for idx, row in df_pha.iterrows():
            raw_safeguards = str(row[safeguard_col]).split('\n')

            for sg_text in raw_safeguards:
                sg_text = sg_text.strip()
                if len(sg_text) < 10: continue

                if self.is_mechanical_only(sg_text):
                    continue
                if self.is_alarm_only(sg_text):
                    continue

                sg_upper = sg_text.upper()
                match_found = False
                technique = ""
                extracted_tags = []

                af_tags = re.findall(r'\b(AF-\d+[A-Z]?)\b', sg_upper)
                if af_tags:
                    extracted_tags.extend(af_tags)

                isa_tags = re.findall(r'\b([A-Z]{2,4}[- ]?\d{3,5}[A-Z]?)\b', sg_upper)
                for tag in isa_tags:
                    if tag not in extracted_tags and not any(ign in tag for ign in ['PSV', 'PM', 'TK', 'EX']):
                        extracted_tags.append(tag)

                if af_tags or any(k in sg_upper for k in self.SIF_KEYWORDS):
                    match_found = True
                    technique = "Tier 1: Explicit Interlock/AF Tag"
                    semantic_score = "N/A"
                    confidence = "High"
                else:
                    sg_emb = model.encode(sg_text, convert_to_tensor=True).to(device)
                    cosine_scores = util.cos_sim(sg_emb, target_embeddings)
                    max_score = float(torch.max(cosine_scores))

                    if max_score > 0.35:
                        match_found = True
                        technique = "Tier 2: Semantic NLP Match"
                        semantic_score = round(max_score, 3)
                        confidence = "Medium"

                if match_found:
                    results.append({
                        'Extracted_Tag_Clean': " | ".join(extracted_tags) if extracted_tags else "General SIF (No Tag)",
                        'Technique': technique,
                        'Confidence': confidence,
                        'Safeguard_Text': sg_text,
                        'Semantic_Score': semantic_score if 'semantic_score' in locals() else "N/A",
                        'Cause_Text': row.get(cause_col, ''),
                        'Consequence_Text': row.get(conseq_col, ''),
                        'Node_ID': row.get('Node_ID', ''),
                        'S': row.get('S', ''),
                        'L': row.get('L', ''),
                        'R': row.get('R', '')
                    })

        df_sif = pd.DataFrame(results)
        if not df_sif.empty:
            df_sif_unique = df_sif.groupby(['Safeguard_Text', 'Extracted_Tag_Clean', 'Technique', 'Node_ID']).agg({
                'Confidence': 'first',
                'Semantic_Score': 'first',
                'S': 'max',
                'Cause_Text': lambda x: ' | '.join(set(x)),
                'Consequence_Text': lambda x: ' | '.join(set(x))
            }).reset_index()

            print(f"[OK] Successfully extracted {len(df_sif_unique)} unique Instrumented Functions.")
            df_sif_unique.to_csv(self.output_csv, index=False)
            print(f"File saved to: {self.output_csv}")
        else:
            print("No SIFs found.")
