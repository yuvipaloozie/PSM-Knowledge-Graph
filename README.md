# Process Safety Management (PSM) AI & Knowledge Graph

This repository demonstrates an end-to-end Machine Learning and Data Engineering pipeline for **Process Safety Management (PSM)** in the industrial sector. 

It takes massive amounts of flat, unstructured engineering documentation (HAZOPs, Alarm Registers, P&IDs) and dynamically constructs a queryable, mathematically robust **Digital Twin (Knowledge Graph)**. It uses Natural Language Processing (NLP) to extract engineering physics and includes an AI Copilot (GraphRAG) that answers technical questions using local data without hallucinating.

## Core Features
1. **Unstructured Data Parsing (ETL):** Extracts physical asset tags (valves, pumps, vessels) from raw human-written hazard causes and consequences.
2. **Semantic NLP (SentenceTransformers):** Utilizes `all-MiniLM-L6-v2` and Fuzzy String Matching (`rapidfuzz`) to categorize unstructured safety text into true Safety Instrumented Functions (SIFs) or Process Alarms.
3. **Automated Gap Analysis:** Mathematically audits engineering topologies, ensuring that the risk severities listed in Process Hazard Analyses (PHAs) accurately match the real-world alarm system configurations.
4. **Interactive Knowledge Graph:** Uses `NetworkX` and `PyVis` to visualize the "physics" of the facility as a Bowtie graph (Deviation ➔ Cause ➔ Consequence ➔ Safeguard).
5. **GraphRAG Copilot (Local AI):** Integrates with a local deployment of **Ollama (Llama 3.2)**. It extracts localized graph topologies and feeds them into the LLM prompt to provide hyper-accurate, hallucination-free Engineering AI.

---

## 🚀 How to Run Locally

Because this project uses a local LLM via Ollama and outputs standard `.graphml` files, it is completely lightweight. You do not need massive Docker containers or external cloud databases to run this demo.

### 1. Prerequisites
- **Python 3.9+**
- **Ollama** installed on your machine.
- Start Ollama and download the model by running:
  ```bash
  ollama run llama3.2
  ```

### 2. Installation
Clone the repository and install the Python dependencies:
```bash
git clone https://github.com/your-username/psm-knowledge-graph.git
cd psm-knowledge-graph
pip install -r requirements.txt
```

### 3. Run the Applications
This repository contains two primary Streamlit dashboards:

**To view the AI Copilot and 3D Interactive Process Graph:**
```bash
streamlit run appGraph.py
```

**To view the Relational Database tables and Gap Analysis Dashboard:**
```bash
streamlit run app.py
```

---

## 🏗️ Architecture

### 1. The Pipeline (`pipeline/`)
The background data engineering scripts that process the raw CSVs:
- `pha_study_flattener.py`: Extracts Node specifications using Regex.
- `hazop_flattener.py`: Generates the core Bowtie model logic.
- `sif_parser.py`: Uses Semantic NLP to isolate interlocks.
- `alarms_parser.py`: Uses Semantic NLP to extract process alarms.
- `gap_analyzer.py`: The automated auditor (compares HAZOP vs Alarm logic).

### 2. The Outputs (`Script Outputs/`)
The flat files are compiled into a central relational SQLite database (`PSM_Master_Inputs.db`) and a topological network map (`PSM_Master_Inputs.graphml`).

### 3. The Frontends
The Streamlit applications load the `.db` and `.graphml` files directly into memory, providing an elegant, high-speed interface for traversal and analysis.

---
*Note: All data in this repository has been strictly anonymized. No proprietary client schematics, PI numbers, or actual plant locations are included.*
