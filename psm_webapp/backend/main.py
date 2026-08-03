from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import networkx as nx
import os
import json
import re
from rapidfuzz import process, fuzz
import requests
from pydantic import BaseModel

app = FastAPI(title="PSM Graph DB Backend")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(BASE_DIR, "..", "..")
GRAPH_PATH = os.path.join(PROJECT_ROOT, "PSM_Master_Inputs.graphml")

# Global variables
G = None
FOUNDATIONAL_NODES = []

def load_graph():
    global G, FOUNDATIONAL_NODES
    if os.path.exists(GRAPH_PATH):
        G = nx.read_graphml(GRAPH_PATH)
        FOUNDATIONAL_NODES = [n for n, attr in G.nodes(data=True) if attr.get('type') in ['Equipment', 'Drawing', 'Node']]
        print(f"Graph loaded: {len(G.nodes)} nodes, {len(G.edges)} edges.")
    else:
        print("GraphML file not found!")

@app.on_event("startup")
async def startup_event():
    load_graph()

# Color map for 3D Graph
COLOR_MAP = {
    "Equipment": "#F39C12", "Node": "#3498DB", "Drawing": "#9B59B6",
    "Deviation": "#F1C40F", "Cause": "#E67E22", "Consequence": "#E74C3C",
    "Safeguard": "#2ECC71", "Unknown": "#BDC3C7"
}

@app.get("/api/graph")
def get_graph():
    if not G:
        raise HTTPException(status_code=404, detail="Graph not loaded")
    
    nodes = []
    for n, d in G.nodes(data=True):
        n_type = d.get('type', 'Unknown')
        nodes.append({
            "id": n,
            "name": d.get('label', n),
            "title": d.get('title', ''),
            "group": n_type,
            "color": COLOR_MAP.get(n_type, "#FFFFFF"),
            "val": 2 if n_type == "Consequence" else 1, # Size mapping
            "degree": G.degree(n),
            "severity": d.get("severity", "0"),
            "likelihood": d.get("likelihood", "0"),
            "risk": d.get("risk", "0")
        })
        
    links = []
    for u, v, d in G.edges(data=True):
        links.append({
            "source": u,
            "target": v,
            "relation": d.get('relation', 'CONNECTED_TO'),
            "color": "rgba(255,255,255,0.2)"
        })
        
    return {"nodes": nodes, "links": links}

@app.get("/api/analytics")
def get_analytics():
    if not G:
        raise HTTPException(status_code=404, detail="Graph not loaded")
    
    # Calculate Risk Matrix (Severity vs Likelihood)
    risk_matrix = []
    for n, d in G.nodes(data=True):
        if d.get('type') == 'Consequence':
            try: s = float(d.get('severity', 0))
            except: s = 0.0
            try: l = int(float(d.get('likelihood', 0)))
            except: l = 0
            risk_matrix.append({"severity": s, "likelihood": l})
            
    # Equipment Vulnerability (Top 10 by degree)
    equip = [(n, G.degree(n), d.get('label', n)) for n, d in G.nodes(data=True) if d.get('type') == 'Equipment']
    equip = sorted(equip, key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "metrics": {"nodes": len(G.nodes), "edges": len(G.edges)},
        "risk_matrix": risk_matrix,
        "equipment_vulnerability": [{"id": e[0], "degree": e[1], "label": e[2]} for e in equip]
    }

# Replicate subgraph builder for LLM
def build_semantic_subgraph(G_source, target_node, depth=1):
    subG = nx.DiGraph()
    if target_node not in G_source: return subG
    subG.add_node(target_node, **G_source.nodes[target_node])
    
    for u, v, data in G_source.edges(data=True):
        if u == target_node or v == target_node:
            subG.add_node(u, **G_source.nodes[u])
            subG.add_node(v, **G_source.nodes[v])
            subG.add_edge(u, v, **data)
    return subG

@app.post("/api/chat")
def chat_with_ollama(payload: dict = Body(...)):
    user_query = payload.get("query", "")
    model = payload.get("model", "llama3.2")
    
    if not G:
        return {"response": "Graph DB offline."}
        
    matched_nodes = set()
    node_matches = re.findall(r'(?i)\bnode\s*(\d+)\b', user_query)
    for num in node_matches:
        target_node = f"Node {num}"
        if target_node in G:
            matched_nodes.add(target_node)
            
    if not matched_nodes:
        potential_tags = re.findall(r'\b[A-Za-z]{1,4}[- ]?\d{2,5}[A-Za-z]?\b', user_query)
        for ptag in potential_tags:
            match = process.extractOne(ptag.upper(), FOUNDATIONAL_NODES, scorer=fuzz.token_sort_ratio, score_cutoff=80)
            if match:
                matched_nodes.add(match[0])
                
    if not matched_nodes:
        query_terms = set(user_query.lower().replace('?','').split())
        for n, attr in G.nodes(data=True):
            node_text = f"{n} {attr.get('title', '')}".lower()
            if any(term in node_text for term in query_terms if len(term) > 4):
                matched_nodes.add(n)
                
    context_lines = ["--- EXTRACTED SEMANTIC TOPOLOGY ---"]
    if matched_nodes:
        for start_node in list(matched_nodes)[:2]:
            start_type = G.nodes[start_node].get('type', 'Unknown')
            context_lines.append(f"\n[FOCUS ENTITY: {start_node} ({start_type})]")
            local_subgraph = build_semantic_subgraph(G, start_node)
            for s, t, data in local_subgraph.edges(data=True):
                rel = data.get('relation', 'CONNECTED_TO')
                context_lines.append(f"  {s} ({local_subgraph.nodes[s].get('type')}) -> [{rel}] -> {t} ({local_subgraph.nodes[t].get('type')})")
            context_lines.append("  -- Metadata --")
            for node in local_subgraph.nodes():
                title = local_subgraph.nodes[node].get('title', '')
                if title and local_subgraph.nodes[node].get('type') in ['Consequence', 'Cause', 'Safeguard']:
                    context_lines.append(f"  {node}: {title[:150]}...")
    else:
        context_lines.append("No specific topological context found. Answer generically.")

    context_str = "\n".join(context_lines)
    full_prompt = f"Context:\n{context_str}\n\nUser Question:\n{user_query}\n\nAnswer concisely as a Process Safety expert using ONLY the provided context."

    try:
        r = requests.post(f"http://localhost:11434/api/generate", json={
            "model": model,
            "prompt": full_prompt,
            "stream": False
        }, timeout=45)
        r.raise_for_status()
        resp_data = r.json()
        return {"response": resp_data.get("response", "Error getting response.")}
    except Exception as e:
        return {"response": f"Ollama Connection Error: {str(e)}"}

@app.post("/api/path")
def get_path(payload: dict = Body(...)):
    if not G: return {"paths": [], "count": 0}
    source = payload.get("source")
    target = payload.get("target")
    if source not in G or target not in G: return {"paths": [], "count": 0}
    
    try:
        paths = list(nx.all_shortest_paths(G.to_undirected(), source=source, target=target))
        paths = paths[:20]
        
        path_nodes = set()
        for p in paths: path_nodes.update(p)
        
        nodes = []
        for n in path_nodes:
            d = G.nodes[n]
            n_type = d.get('type', 'Unknown')
            nodes.append({
                "id": n, "name": d.get('label', n), "group": n_type,
                "color": COLOR_MAP.get(n_type, "#95A5A6"), "val": 2 if n_type == "Consequence" else 1
            })
            
        links = []
        added_edges = set()
        for p in paths:
            for i in range(len(p)-1):
                u, v = p[i], p[i+1]
                if (u, v) in added_edges or (v, u) in added_edges: continue
                
                if G.has_edge(u, v):
                    rel = G.edges[u, v].get('relation', '')
                    c = "#E74C3C" if rel not in ["MITIGATES", "REFERENCES_EQUIPMENT", "CONTAINS", "APPEARS_ON"] else "#95A5A6"
                    links.append({"source": u, "target": v, "relation": rel, "color": c})
                    added_edges.add((u, v))
                elif G.has_edge(v, u):
                    rel = G.edges[v, u].get('relation', '')
                    c = "#3498DB" if rel not in ["MITIGATES", "REFERENCES_EQUIPMENT", "CONTAINS", "APPEARS_ON"] else "#95A5A6"
                    links.append({"source": v, "target": u, "relation": rel + " (Reversed)", "color": c})
                    added_edges.add((v, u))
                    
        return {"nodes": nodes, "links": links, "count": len(paths)}
    except nx.NetworkXNoPath:
        return {"paths": [], "count": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
