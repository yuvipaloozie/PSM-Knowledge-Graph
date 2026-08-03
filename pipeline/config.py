import os

class Config:
    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.INPUT_DIR = os.path.join(self.BASE_DIR, 'CSV Inputs')
        self.OUTPUT_DIR = os.path.join(self.BASE_DIR, 'Script Outputs')

        # Raw Inputs
        self.PHA_FULL_CSV = os.path.join(self.INPUT_DIR, 'PSM PHA Full Table CSV.csv')
        self.PHA_STUDY_CSV = os.path.join(self.INPUT_DIR, 'PSM PHA Study Table CSV.csv')
        
        # Parsed/Flattened Outputs
        self.FLAT_PHA_CSV = os.path.join(self.OUTPUT_DIR, 'PSM_Final_PHA_Database.csv')
        self.EXTRACTED_NODES_CSV = os.path.join(self.OUTPUT_DIR, 'PSM_Extracted_Equipment_Nodes.csv')

        # NLP Parsed Outputs
        self.SIF_OUTPUT_CSV = os.path.join(self.OUTPUT_DIR, 'PSM_HAZOP_Instrumented_Functions.csv')
        self.ALARMS_OUTPUT_CSV = os.path.join(self.OUTPUT_DIR, 'PSM_HAZOP_Alarms.csv')

        # AR Gap Analysis Inputs & Outputs
        self.AR_MATRIX_CSV = os.path.join(self.OUTPUT_DIR, 'PSM Final AR Matrix CSV - Splitter.csv')
        self.GAP_REPORT_CSV = os.path.join(self.OUTPUT_DIR, 'PSM_HAZOP-AR_Gap_Report.csv')

        # Database Outputs
        self.SQLITE_DB = os.path.join(self.BASE_DIR, 'PSM_Master_Inputs.db')

        # Model Names
        self.NLP_MODEL_NAME = 'all-MiniLM-L6-v2'

    def ensure_directories(self):
        os.makedirs(self.INPUT_DIR, exist_ok=True)
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
