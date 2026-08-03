import os
import pandas as pd
import numpy as np
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class GapAnalyzer:
    def __init__(self, pha_file, ar_file, output_csv):
        self.pha_file = pha_file
        self.ar_file = ar_file
        self.output_csv = output_csv
        
        self.SYSTEM_AND_STATE_BLOCKS = {'IOP', 'IOPALM', 'MC', 'RST', 'SO', 'VLV', 'OVR', 'VEL', 'CL', 'CALC', 'ESTP'}
        self.FUNCTIONAL_INTENT_MAP = {
            'HI': {'allowed': {'HI', 'H', 'ALM', 'SWAH', 'HA', 'STAH', 'HTRP', 'HIHI', 'HH', 'HHALM', 'TRP', 'TRIP'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS.union({'L', 'LO', 'LL', 'LOLO', 'LTRP', 'SWAL', 'STAL'})},
            'HIHI': {'allowed': {'HIHI', 'HH', 'HTRP', 'TRP', 'TRIP', 'HHALM'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS.union({'L', 'LO', 'LL', 'LOLO', 'LTRP', 'SWAL', 'STAL'})},
            'LO': {'allowed': {'LO', 'L', 'ALM', 'SWAL', 'LA', 'STAL', 'LTRP', 'LOLO', 'LL', 'LLALM', 'TRP', 'TRIP'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS.union({'H', 'HI', 'HH', 'HIHI', 'HTRP', 'SWAH', 'STAH'})},
            'LOLO': {'allowed': {'LOLO', 'LL', 'LTRP', 'TRP', 'TRIP', 'LLALM'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS.union({'H', 'HI', 'HH', 'HIHI', 'HTRP', 'SWAH', 'STAH'})},
            'TRP': {'allowed': {'HTRP', 'LTRP', 'TRP', 'TRIP', 'ESTP'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS.union({'ALM', 'H', 'HI', 'L', 'LO', 'SWAH', 'SWAL', 'STAH', 'STAL'})},
            'ALM': {'allowed': {'ALM', 'H', 'HI', 'L', 'LO', 'HH', 'LL', 'SWAH', 'SWAL', 'STAH', 'STAL', 'HTRP', 'LTRP', 'TRP'}, 'forbidden': self.SYSTEM_AND_STATE_BLOCKS}
        }
        self.SEV_MAP = {'SEVERE': 5, 'MAJOR': 4, 'MINOR': 3, 'NEGLIGIBLE': 2, 'NEG': 2, 'NONE': 0, 'NAN': 0}

    def clean_tag(self, text):
        if pd.isna(text): return ""
        return re.sub(r'[^A-Z0-9]', '', str(text).upper())

    def get_prefix_and_loop(self, tag):
        match = re.match(r'^([A-Z]+)(\d+)', str(tag))
        if match: return match.group(1), match.group(2)
        return tag, ""

    def is_alarm_specific(self, prefix):
        if len(prefix) < 2: return False
        return 'A' in prefix[1:]

    def get_max_tfidf_similarity(self, ar_text, pha_concatenated):
        if pd.isna(ar_text) or pd.isna(pha_concatenated) or str(ar_text).strip() == "" or str(pha_concatenated).strip() == "":
            return 0.0

        pha_entries = [item.strip() for item in str(pha_concatenated).split('|') if len(item.strip()) > 5]
        if not pha_entries:
            return 0.0

        corpus = [str(ar_text)] + pha_entries

        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform(corpus)
            cosine_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
            return round(float(np.max(cosine_scores)), 3)
        except ValueError:
            return 0.0

    def perform_gap_analysis(self, pha, lookup, by_loop):
        results = []
        for _, p_row in pha.iterrows():
            p_tag = self.clean_tag(p_row['Extracted_Tag_Clean'])
            p_mnemonic = self.clean_tag(p_row['Alarm_Type'])
            p_prefix, p_loop = self.get_prefix_and_loop(p_tag)
            intent = self.FUNCTIONAL_INTENT_MAP.get(p_mnemonic, {'allowed': {p_mnemonic}, 'forbidden': {'IOP', 'IOPALM'}})

            match_found = False
            category = "GAP: NO MATCH"
            ref_tag = "N/A"

            if p_tag in lookup:
                available_exts = lookup[p_tag]
                if self.is_alarm_specific(p_prefix):
                    match_found, category, ref_tag = True, "MATCH: Tier 1 (Alarm-Specific)", p_tag
                elif intent['allowed'].intersection(available_exts):
                    matched_ext = list(intent['allowed'].intersection(available_exts))[0]
                    match_found, category, ref_tag = True, "MATCH: Tier 1 (Instrument Config)", f"{p_tag}.{matched_ext}"

            if not match_found and p_loop in by_loop:
                loop_mates = sorted(by_loop[p_loop], key=len)
                for mate in loop_mates:
                    mate_prefix, _ = self.get_prefix_and_loop(mate)
                    if not p_prefix or not mate_prefix or p_prefix[0] != mate_prefix[0]: continue

                    valid_exts = intent['allowed'].intersection(lookup[mate])
                    if valid_exts:
                        matched_ext = list(valid_exts)[0]
                        match_found, category, ref_tag = True, f"MATCH: Tier 2 (Loop-Mate {mate}.{matched_ext})", f"{mate}.{matched_ext}"
                        break

                if not match_found:
                    for mate in loop_mates:
                        mate_prefix, _ = self.get_prefix_and_loop(mate)
                        if not p_prefix or not mate_prefix or p_prefix[0] != mate_prefix[0]: continue
                        forbidden_found = intent['forbidden'].intersection(lookup[mate])
                        if forbidden_found:
                            category, ref_tag = f"FUNCTIONAL GAP: Found {mate}.{list(forbidden_found)[0]} but lacks valid process alarm.", mate
                            break

            if not match_found and category == "GAP: NO MATCH" and p_tag in lookup:
                category, ref_tag = f"PARTIAL GAP: Base {p_tag} exists, missing {p_mnemonic}", p_tag

            res = p_row.to_dict()
            res['Match_Status'], res['Gap_Category'], res['AR_Reference'] = match_found, category, ref_tag
            results.append(res)
        return pd.DataFrame(results)

    def audit_risk(self, row):
        raw_s = row.get('S')
        if pd.isna(raw_s) or str(raw_s).strip() == '': pha_s = 0
        else:
            try: pha_s = int(float(str(raw_s).strip()))
            except ValueError: pha_s = 0

        ar_sev_raw = row.get('AR_Severity')
        if pd.isna(ar_sev_raw) or str(ar_sev_raw).strip() == '' or str(ar_sev_raw).upper().strip() == 'NAN':
            ar_sev = 'NONE'
            ar_sev_raw = 'Missing'
        else:
            ar_sev = str(ar_sev_raw).strip().upper()

        ar_s_num = 0
        for key, val in self.SEV_MAP.items():
            if key in ar_sev:
                ar_s_num = val
                break

        if pd.isna(row.get('AR_Reference')) or row.get('AR_Reference') == 'N/A': return "N/A (No AR Match)"
        if pha_s == 0: return f"Aligned (PHA S is Missing/Blank)"
        if ar_s_num == 0: return f"UNRATIONALIZED: PHA S={pha_s} vs AR Sev=Missing"

        if pha_s >= 4 and ar_s_num <= 3: return f"CRITICAL MISMATCH: PHA S={pha_s} vs AR Sev={ar_sev_raw}"
        elif pha_s > ar_s_num: return f"UNDER-RATIONALIZED: PHA S={pha_s} > AR Sev={ar_sev_raw}"
        return "Aligned"

    def run(self):
        print("Starting Gap Analysis Engine...")
        df_pha = pd.read_csv(self.pha_file)
        df_ar = pd.read_csv(self.ar_file, dtype={'LOOP': str})

        ar_lookup = {}
        ar_by_loop = {}

        for _, row in df_ar.iterrows():
            raw_tag_str = str(row.get('Signal/Instrument Tag', '')).upper().strip()
            match = re.search(r'^(.*?)([\.\-_])([A-Z]+)$', raw_tag_str)
            inline_suffix = ""

            if match:
                potential_base, potential_suffix = match.group(1), match.group(3)
                if len(potential_suffix) == 1 and potential_suffix not in ['H', 'L']:
                    base_tag_str = raw_tag_str
                else:
                    base_tag_str = potential_base
                    inline_suffix = potential_suffix
            else:
                base_tag_str = raw_tag_str

            raw_tag = self.clean_tag(base_tag_str)

            type_val = str(row.get('Type', '')).upper().strip()
            ext_val = str(row.get('Alarm Tag / Extension', '')).upper().strip()

            final_ext = inline_suffix or type_val if (type_val and type_val != 'NAN') else (ext_val.split('.')[-1] if '.' in ext_val else (ext_val.split('-')[-1] if '-' in ext_val else ext_val))
            if 'IOP' in raw_tag_str or 'IOP' in ext_val: final_ext = 'IOP'
            if 'DCS' in raw_tag_str or 'DCS' in ext_val: final_ext = 'DCS'

            ext_cleaned = self.clean_tag(final_ext)

            if raw_tag not in ar_lookup: ar_lookup[raw_tag] = set()
            if ext_cleaned: ar_lookup[raw_tag].add(ext_cleaned)

            loop_num_raw = self.clean_tag(str(row.get('LOOP', '')).strip())
            loop_num = loop_num_raw if loop_num_raw and loop_num_raw != 'NAN' else self.get_prefix_and_loop(raw_tag)[1]

            if loop_num:
                if loop_num not in ar_by_loop: ar_by_loop[loop_num] = []
                if raw_tag not in ar_by_loop[loop_num]: ar_by_loop[loop_num].append(raw_tag)

        ar_metadata_df = df_ar[['Alarm Tag / Extension', 'Severity', 'Assessed Priority', 'Potential Cause', 'Potential Consequence']].copy()
        ar_metadata_df.columns = ['AR_Ref_Key', 'AR_Severity', 'AR_Priority', 'AR_Potential_Cause', 'AR_Potential_Consequence']
        ar_metadata_df = ar_metadata_df.drop_duplicates(subset=['AR_Ref_Key'])

        df_gap_results = self.perform_gap_analysis(df_pha, ar_lookup, ar_by_loop)

        df_audit = pd.merge(df_gap_results, ar_metadata_df, left_on='AR_Reference', right_on='AR_Ref_Key', how='left')
        df_audit = df_audit.drop(columns=['AR_Ref_Key'])

        df_audit['Risk_Integrity_Audit'] = df_audit.apply(self.audit_risk, axis=1)

        mask = df_audit['Match_Status'] == True
        df_audit.loc[mask, 'Cause_Similarity_Score'] = df_audit.loc[mask].apply(
            lambda x: self.get_max_tfidf_similarity(x['AR_Potential_Cause'], x['Cause_Text']), axis=1
        )
        df_audit.loc[mask, 'Conseq_Similarity_Score'] = df_audit.loc[mask].apply(
            lambda x: self.get_max_tfidf_similarity(x['AR_Potential_Consequence'], x['Consequence_Text']), axis=1
        )

        df_audit['Strong_Text_Match'] = (df_audit.get('Cause_Similarity_Score', 0) > 0.40) | \
                                        (df_audit.get('Conseq_Similarity_Score', 0) > 0.40)

        df_audit.to_csv(self.output_csv, index=False)
        print(f"[OK] AR Gap Analysis Complete. Report saved to: {self.output_csv}")
