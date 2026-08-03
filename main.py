import os
import sys

from pipeline.config import Config
from pipeline.hazop_flattener import HazopFlattener
from pipeline.pha_study_flattener import PhaStudyFlattener
from pipeline.sif_parser import SifParser
from pipeline.alarms_parser import AlarmsParser
from pipeline.gap_analyzer import GapAnalyzer
from pipeline.rdb_builder import RelationalDBBuilder
from pipeline.graphdb_builder import GraphDBBuilder

def main():
    print("==========================================")
    print("PSM PSM Pipeline Orchestrator")
    print("==========================================")

    config = Config()
    config.ensure_directories()

    print("\n--- Phase 1: Data Flattening & ETL ---")
    HazopFlattener(config.PHA_FULL_CSV, config.FLAT_PHA_CSV).run()
    PhaStudyFlattener(config.PHA_STUDY_CSV, config.EXTRACTED_NODES_CSV).run()

    print("\n--- Phase 2: NLP Parsers (SIF & Alarms) ---")
    SifParser(config.FLAT_PHA_CSV, config.SIF_OUTPUT_CSV, config.NLP_MODEL_NAME).run()
    AlarmsParser(config.FLAT_PHA_CSV, config.ALARMS_OUTPUT_CSV, config.NLP_MODEL_NAME).run()

    print("\n--- Phase 3: AR Gap Analysis ---")
    GapAnalyzer(config.ALARMS_OUTPUT_CSV, config.AR_MATRIX_CSV, config.GAP_REPORT_CSV).run()

    print("\n--- Phase 4: Database Generation ---")
    RelationalDBBuilder(config.FLAT_PHA_CSV, config.EXTRACTED_NODES_CSV, config.AR_MATRIX_CSV, config.GAP_REPORT_CSV, config.SQLITE_DB).run()
    GraphDBBuilder(config.FLAT_PHA_CSV, config.EXTRACTED_NODES_CSV, config.SQLITE_DB).run()

    print("\n==========================================")
    print("Pipeline Execution Completed Successfully!")
    print("==========================================")

if __name__ == "__main__":
    main()
