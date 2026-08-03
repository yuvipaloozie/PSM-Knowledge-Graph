import streamlit as st
import networkx as nx
from pyvis.network import Network
import os
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
import requests
import json
import pickle
import re
from rapidfuzz import process, fuzz

# --- 1. PAGE CONFIG & CUSTOM CSS ---
st.set_page_config(layout="wide", page_title="PSM Process Safety OS")

st.markdown("""
<style>
    /* Professional Engineering Typography & Layout */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
    h1, h2, h3 { color: #2C3E50; font-weight: 600; }
    
    /* Clean Tab Styling */
    .st-tabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 2px solid #E0E0E0; }
    .st-tabs [data-baseweb="tab"] {
        padding-top: 12px; padding-bottom: 12px; padding-left: 20px; padding-right: 20px;
        background-color: #F8F9FA; border: 1px solid #E0E0E0; border-bottom: none;
        border-radius: 4px 4px 0 0; color: #546E7A; font-weight: 600; font-size: 14px;
    }
    .st-tabs [aria-selected="true"] { background-color: #FFFFFF; color: #2980B9; border-top: 3px solid #2980B9; }
    
    /* Custom Chat UI (No Avatars, Color-Coded Boxes) */
    [data-testid="stChatMessageAvatar"] { display: none !important; }
    [data-testid="stChatMessage"] { border-radius: 6px; padding: 15px; margin-bottom: 12px; font-size: 14px; }
    /* User Message Box */
    [data-testid="stChatMessage"]:nth-child(odd) { background-color: #F4F6F6; border-left: 4px solid #7F8C8D; }
    /* System Message Box */
    [data-testid="stChatMessage"]:nth-child(even) { background-color: #EBF5FB; border-left: 4px solid #2980B9; }
</style>
""", unsafe_allow_html=True)

st.title("PSM PSM Graph DB")

# --- 2. DATA LOADING & CACHING ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "Script Outputs")

@st.cache_data
def load_graph():
    graph_path = os.path.join(BASE_DIR, "PSM_Master_Inputs.graphml")
    G = nx.read_graphml(graph_path)
        
    for n, d in G.nodes(data=True):
        d['degree'] = G.degree(n)
        if d.get('type') == 'Consequence':
            try: d['severity'] = float(d.get('severity', 0))
            except: d['severity'] = 0.0
    return G

try:
    G = load_graph()
except Exception as e:
    st.error(f"Data missing or failed to load. Ensure PSM_Master_Inputs.graphml exists. Error: {e}")
    st.stop()

# --- 3. SIDEBAR: GLOBAL CONTROLS ---
st.sidebar.header("Graph Controls")

entity_types = ["Drawing", "Node", "Equipment", "Deviation", "Cause", "Consequence", "Safeguard"]
target_class = st.sidebar.selectbox("Filter by Entity Class:", ["All Entities"] + entity_types)

if target_class == "All Entities":
    node_choices = ["Entire Facility"] + sorted(list(G.nodes()))
else:
    filtered_nodes = sorted([n for n, attr in G.nodes(data=True) if attr.get('type') == target_class])
    node_choices = ["Entire Facility"] + filtered_nodes
    
selected_node = st.sidebar.selectbox("Isolate Specific Entity:", node_choices)

st.sidebar.markdown("---")
st.sidebar.markdown("**Graph Optimization**")
min_severity = st.sidebar.slider("Minimum Severity (Consequences):", 1, 5, 1)
enable_physics = st.sidebar.toggle("Enable Live Physics", value=False)

# --- 4. SEMANTIC ISOLATION ENGINE ---
def build_semantic_subgraph(G, root_node):
    subgraph_nodes = set([root_node])
    root_type = G.nodes[root_node].get('type', 'Unknown')
    
    def walk_up_to_node(start_node):
        """Walks upstream strictly to find the parent Process Node and its drawings."""
        curr = start_node
        while curr:
            parents = [p for p in G.predecessors(curr) if G.edges[p, curr].get('relation') in ['CONTAINS', 'EXPERIENCES', 'CAUSED_BY', 'RESULTS_IN']]
            if not parents: break
            curr = parents[0]
            subgraph_nodes.add(curr)
            if G.nodes[curr].get('type') == 'Node':
                # Grab drawings for this node
                for succ in G.successors(curr):
                    if G.edges[curr, succ].get('relation') == 'APPEARS_ON':
                        subgraph_nodes.add(succ)
                break

    def walk_down_bowtie(start_node):
        """Walks downstream to find Causes, Consequences, and mitigating Safeguards."""
        for child in G.successors(start_node):
            rel = G.edges[start_node, child].get('relation')
            if rel in ['CAUSED_BY', 'RESULTS_IN']:
                subgraph_nodes.add(child)
                walk_down_bowtie(child)
                
                # If child is a consequence, grab its safeguards
                if G.nodes[child].get('type') == 'Consequence':
                    for p in G.predecessors(child):
                        if G.edges[p, child].get('relation') == 'MITIGATES':
                            subgraph_nodes.add(p)

    def extract_equipment_refs(nodes_set):
        """Finds any Equipment referenced by the current set of nodes."""
        refs = set()
        for n in list(nodes_set):
            for succ in G.successors(n):
                if G.edges[n, succ].get('relation') == 'REFERENCES_EQUIPMENT':
                    refs.add(succ)
        subgraph_nodes.update(refs)

    if root_type == 'Drawing':
        # Find all nodes that appear on this drawing
        for pred in G.predecessors(root_node):
            if G.edges[pred, root_node].get('relation') == 'APPEARS_ON':
                subgraph_nodes.add(pred)
                # For each node, grab equipment and hazards
                for succ in G.successors(pred):
                    if G.edges[pred, succ].get('relation') == 'CONTAINS':
                        subgraph_nodes.add(succ)
                    if G.edges[pred, succ].get('relation') == 'EXPERIENCES':
                        subgraph_nodes.add(succ)
                        walk_down_bowtie(succ)
        extract_equipment_refs(subgraph_nodes)

    elif root_type == 'Node':
        # Grab Drawings
        for succ in G.successors(root_node):
            if G.edges[root_node, succ].get('relation') == 'APPEARS_ON':
                subgraph_nodes.add(succ)
        # Grab local equipment
        for succ in G.successors(root_node):
            if G.edges[root_node, succ].get('relation') == 'CONTAINS':
                subgraph_nodes.add(succ)
        # Grab all hazards stemming from this node
        for dev in G.successors(root_node):
            if G.edges[root_node, dev].get('relation') == 'EXPERIENCES':
                subgraph_nodes.add(dev)
                walk_down_bowtie(dev)
        extract_equipment_refs(subgraph_nodes)

    elif root_type == 'Equipment':
        walk_up_to_node(root_node)
        # Find hazard scenarios that reference this equipment
        for pred in G.predecessors(root_node):
            if G.edges[pred, root_node].get('relation') == 'REFERENCES_EQUIPMENT':
                subgraph_nodes.add(pred)
                walk_up_to_node(pred)
                walk_down_bowtie(pred)
                
    elif root_type == 'Deviation':
        walk_up_to_node(root_node)
        walk_down_bowtie(root_node)
        extract_equipment_refs(subgraph_nodes)
        
    elif root_type == 'Cause':
        walk_up_to_node(root_node)
        walk_down_bowtie(root_node)
        extract_equipment_refs(subgraph_nodes)
        
    elif root_type == 'Consequence':
        walk_up_to_node(root_node)
        for p in G.predecessors(root_node):
            if G.edges[p, root_node].get('relation') == 'MITIGATES':
                subgraph_nodes.add(p)
        extract_equipment_refs(subgraph_nodes)
        
    elif root_type == 'Safeguard':
        for succ in G.successors(root_node):
            if G.edges[root_node, succ].get('relation') == 'MITIGATES':
                subgraph_nodes.add(succ)
                walk_up_to_node(succ)
        extract_equipment_refs(subgraph_nodes)
                
    return G.subgraph(subgraph_nodes).copy()

if selected_node != "Entire Facility":
    G_render = build_semantic_subgraph(G, selected_node)
else:
    G_render = G.copy()

nodes_to_remove = []
for n, attr in G_render.nodes(data=True):
    if n == selected_node: continue
    if attr.get('type') == 'Consequence' and attr.get('severity', 0) < min_severity:
        nodes_to_remove.append(n)
G_render.remove_nodes_from(nodes_to_remove)

# --- 5. TAB LAYOUT ---
tab_graph, tab_dash, tab_path, tab_chat, tab_raw = st.tabs([
    "Knowledge Graph", "Graph Analytics", "Graph Traversal", "Graph LLM", "Raw Data Master"
])

# ==========================================
# TAB 1: TOPOLOGY VIEWER
# ==========================================
with tab_graph:
    net = Network(height="750px", width="100%", directed=True, bgcolor="#F8F9FA", font_color="#2C3E50")
    
    color_map = {
        "Drawing": "#8E44AD", "Node": "#2E5B88", "Equipment": "#7F8C8D", "Deviation": "#F39C12", 
        "Cause": "#D35400", "Consequence": "#C0392B", "Safeguard": "#16A085"
    }

    for node_id, node_attrs in G_render.nodes(data=True):
        n_type = node_attrs.get("type", "Unknown")
        deg = node_attrs.get("degree", 1)
        
        # Sizing rules
        if n_type == "Consequence": size = 28
        elif n_type == "Drawing": size = 35 # Make drawings permanently visible
        else: size = 15 + (deg * 1.5)
        
        if size > 40: size = 40
        
        # Label rules
        if n_type == "Drawing":
            raw_label = f"P&ID: {node_attrs.get('label', node_id)}"
        else:
            raw_label = str(node_attrs.get("label", node_id))
            
        final_label = raw_label[:25] + "..." if len(raw_label) > 25 else raw_label
        
        net.add_node(
            node_id, label=final_label, 
            title=node_attrs.get("title", node_id), color=color_map.get(n_type, "#000"),
            size=size, group=n_type, degree=deg,
            severity=node_attrs.get("severity", "N/A"),
            likelihood=node_attrs.get("likelihood", "N/A"),
            risk=node_attrs.get("risk", "N/A")
        )

    for source, target, edge_attrs in G_render.edges(data=True):
        rel = edge_attrs.get("relation", "")
        e_color = "#E74C3C" if rel == "REFERENCES_EQUIPMENT" else "#BDC3C7"
        e_width = 2 if rel == "REFERENCES_EQUIPMENT" else 1
        net.add_edge(source, target, title=rel, color=e_color, width=e_width)

    physics_string = "true" if enable_physics else "false"
    net.set_options(f"""
    var options = {{
      "physics": {{ "enabled": {physics_string}, "forceAtlas2Based": {{"gravitationalConstant": -60, "springLength": 120}}, "minVelocity": 0.75, "solver": "forceAtlas2Based" }}
    }}
    """)

    net.save_graph("temp_graph.html")
    with open("temp_graph.html", "r", encoding="utf-8") as f: source_code = f.read()

    custom_css = """
    <style>
        #info-panel {
            position: absolute; top: 20px; left: 20px; width: 360px;
            background: rgba(255, 255, 255, 0.98); border: 1px solid #CFD8DC;
            border-radius: 6px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            font-family: 'Inter', sans-serif; z-index: 9999; backdrop-filter: blur(5px);
        }
        #info-panel h3 { margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #2980B9; color: #2C3E50; font-size: 15px; text-transform: uppercase; letter-spacing: 1px; }
        .prop-row { display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid #ECEFF1; padding-bottom: 6px; }
        .prop-label { font-weight: 600; color: #546E7A; font-size: 12px; text-transform: uppercase; }
        .prop-value { font-family: 'Consolas', monospace; color: #263238; font-size: 13px; text-align: right; max-width: 65%; word-wrap: break-word; }
        .prop-desc { margin-top: 15px; font-size: 13px; color: #37474F; line-height: 1.5; background: #F4F6F6; padding: 12px; border-left: 4px solid #2980B9; border-radius: 0 4px 4px 0; }
    </style>
    <div id="info-panel">
        <h3>Component Inspector</h3>
        <div style="color: #7F8C8D; font-size: 13px;">Select a topological entity or edge to view properties.</div>
    </div>
    """
    custom_js = """
    network.on("click", function (p) { 
        var pan = document.getElementById('info-panel'); 
        if (p.nodes.length > 0) { 
            var n = nodes.get(p.nodes[0]); 
            pan.innerHTML = "<h3>Entity Properties</h3>" +
                "<div class='prop-row'><span class='prop-label'>Identifier</span><span class='prop-value'>" + n.id + "</span></div>" +
                "<div class='prop-row'><span class='prop-label'>Classification</span><span class='prop-value'>" + n.group + "</span></div>" +
                "<div class='prop-row'><span class='prop-label'>Connections</span><span class='prop-value'>" + n.degree + "</span></div>" +
                (n.group === "Consequence" ? 
                  "<div class='prop-row'><span class='prop-label' style='color:#C0392B'>Severity (S)</span><span class='prop-value'>" + n.severity + "</span></div>" +
                  "<div class='prop-row'><span class='prop-label' style='color:#C0392B'>Likelihood (L)</span><span class='prop-value'>" + n.likelihood + "</span></div>" +
                  "<div class='prop-row'><span class='prop-label' style='color:#C0392B'>Risk (R)</span><span class='prop-value'>" + n.risk + "</span></div>" : "") +
                "<div class='prop-desc'><strong>Description:</strong><br/>" + n.title + "</div>"; 
        } else if (p.edges.length > 0) { 
            var e = edges.get(p.edges[0]); 
            pan.innerHTML = "<h3>Vector Properties</h3>" +
                "<div class='prop-row'><span class='prop-label'>Relation</span><span class='prop-value'>" + e.title + "</span></div>" +
                "<div class='prop-row'><span class='prop-label'>Origin</span><span class='prop-value'>" + e.from + "</span></div>" +
                "<div class='prop-row'><span class='prop-label'>Target</span><span class='prop-value'>" + e.to + "</span></div>"; 
        } else { 
            pan.innerHTML = "<h3>Component Inspector</h3><div style='color: #7F8C8D; font-size: 13px;'>Select a topological entity or edge to view properties.</div>"; 
        } 
    });
    """
    source_code = source_code.replace("<body>", f"<body>\n{custom_css}")
    source_code = source_code.replace("network = new vis.Network(container, data, options);", f"network = new vis.Network(container, data, options);\n{custom_js}")
    components.html(source_code, height=760)

# ==========================================
# TAB 2: RISK ANALYTICS DASHBOARD
# ==========================================
with tab_dash:
    node_data = [{"ID": n, **attr} for n, attr in G_render.nodes(data=True)]
    df_graph = pd.DataFrame(node_data)
    
    if df_graph.empty:
        st.warning("No data available for the current filters.")
    else:
        col_f1, col_f2 = st.columns(2)
        filter_type = col_f1.multiselect("Filter by Entity Type:", df_graph['type'].unique(), default=df_graph['type'].unique())
        df_filtered = df_graph[df_graph['type'].isin(filter_type)]
        
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Entity Distribution Profile**")
            fig_bar = px.histogram(df_filtered, x='type', color='type', color_discrete_map=color_map, template="simple_white")
            fig_bar.update_layout(xaxis_title="Entity Classification", yaxis_title="Count", showlegend=False)
            st.plotly_chart(fig_bar, width="stretch")
            
        with c2:
            st.markdown("**Top Critical Safeguards (By Connections)**")
            safeguards = df_graph[df_graph['type'] == 'Safeguard'].sort_values('degree', ascending=False).head(10)
            if not safeguards.empty:
                fig_sg = px.bar(safeguards, x='degree', y='ID', orientation='h', color='degree', color_continuous_scale='Teal', template="simple_white")
                fig_sg.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
                st.plotly_chart(fig_sg, width="stretch")
                
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Risk Matrix (S vs L)**")
            cons = df_graph[df_graph['type'] == 'Consequence'].copy()
            if not cons.empty:
                # Clean Likelihood
                def clean_l(val):
                    try: return int(float(str(val).strip()))
                    except: return 0
                cons['likelihood_clean'] = cons['likelihood'].apply(clean_l)
                # Aggregate for heatmap
                matrix_data = cons.groupby(['severity', 'likelihood_clean']).size().reset_index(name='count')
                if not matrix_data.empty:
                    fig_heat = px.density_heatmap(matrix_data, x='likelihood_clean', y='severity', z='count',
                                                 color_continuous_scale="Reds", text_auto=True,
                                                 labels={'likelihood_clean': 'Likelihood (L)', 'severity': 'Severity (S)'})
                    fig_heat.update_layout(xaxis=dict(tickmode='linear', dtick=1), yaxis=dict(tickmode='linear', dtick=1))
                    st.plotly_chart(fig_heat, width="stretch")
        with c4:
            st.markdown("**Equipment Vulnerability Profiles**")
            equip = df_graph[df_graph['type'] == 'Equipment'].sort_values('degree', ascending=False).head(10)
            if not equip.empty:
                fig_eq = px.bar(equip, x='degree', y='ID', orientation='h', color='degree', color_continuous_scale='Oranges', template="simple_white")
                fig_eq.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
                st.plotly_chart(fig_eq, width="stretch")

# ==========================================
# TAB 3: TRACEABILITY ENGINE (Shortest Path)
# ==========================================
with tab_path:
    st.markdown("### Traversal Engine")
    st.markdown("Determine the most direct physical or hazard failure paths between two entities. **Red Arrows** indicate downstream progression, **Blue Arrows** indicate upstream backtracking, and **Grey Arrows** indicate structural links.")
    
    col_s1, col_s2, col_t1, col_t2 = st.columns([1, 2, 1, 2])
    
    with col_s1:
        src_type = st.selectbox("Origin Entity Type", entity_types, index=2, key="src_type")
    with col_s2:
        src_nodes = sorted([n for n, d in G.nodes(data=True) if d.get('type') == src_type])
        source_node = st.selectbox("Origin Instance", src_nodes, key="source_select")
        
    with col_t1:
        tgt_type = st.selectbox("Target Entity Type", entity_types, index=5, key="tgt_type")
    with col_t2:
        tgt_nodes = sorted([n for n, d in G.nodes(data=True) if d.get('type') == tgt_type])
        target_node = st.selectbox("Target Instance", tgt_nodes, key="target_select")
        
    if st.button("Execute Path Analysis", type="primary"):
        try:
            # We use undirected shortest paths to find the most direct routing
            try:
                paths = list(nx.all_shortest_paths(G.to_undirected(), source=source_node, target=target_node))
            except nx.NetworkXNoPath:
                paths = []
            
            if not paths:
                st.error(f"Topological Disconnect: No physical or hazard path exists between {source_node} and {target_node}.")
            else:
                paths = paths[:20] # Safety limit
                st.success(f"Paths Found: {len(paths)} most direct failure mechanisms or causal chains (capped at 20).")
                
                path_nodes = set()
                for p in paths: path_nodes.update(p)
                path_subgraph = G.subgraph(path_nodes)
                
                net_path = Network(height="400px", width="100%", directed=True, bgcolor="#F8F9FA")
                
                for node_id, node_attrs in path_subgraph.nodes(data=True):
                    n_type = node_attrs.get("type", "Unknown")
                    net_path.add_node(
                        node_id, label=str(node_attrs.get("label", node_id))[:20], 
                        title=node_attrs.get("title", node_id), color=color_map.get(n_type, "#000"), size=20,
                        group=n_type, degree=node_attrs.get("degree", 1),
                        severity=node_attrs.get("severity", "N/A"),
                        likelihood=node_attrs.get("likelihood", "N/A"),
                        risk=node_attrs.get("risk", "N/A")
                    )
                    
                # Explicit directional semantic coloring
                added_edges = set()
                for p in paths:
                    for i in range(len(p)-1):
                        u, v = p[i], p[i+1]
                        if (u, v) in added_edges or (v, u) in added_edges:
                            continue
                            
                        # Check native orientation
                        if G.has_edge(u, v):
                            # Forward direction -> Down the bowtie
                            rel = G.edges[u, v].get('relation', '')
                            e_color = "#E74C3C" # Red (Downwards)
                            if rel in ["MITIGATES", "REFERENCES_EQUIPMENT", "CONTAINS", "APPEARS_ON"]:
                                e_color = "#BDC3C7" # Grey (Structural/Mitigation)
                            net_path.add_edge(u, v, title=rel, color=e_color, width=2)
                            added_edges.add((u, v))
                        elif G.has_edge(v, u):
                            # Backward direction -> Up the bowtie
                            rel = G.edges[v, u].get('relation', '')
                            e_color = "#3498DB" # Blue (Upwards)
                            if rel in ["MITIGATES", "REFERENCES_EQUIPMENT", "CONTAINS", "APPEARS_ON"]:
                                e_color = "#BDC3C7" # Grey (Structural/Mitigation)
                            # Draw directed edge backwards to signify traversal direction relative to causal graph
                            net_path.add_edge(v, u, title=rel + " (Reversed Traversal)", color=e_color, width=2)
                            added_edges.add((v, u))
                    
                net_path.set_options('{"physics": {"enabled": true, "forceAtlas2Based": {"gravitationalConstant": -60, "springLength": 120}, "minVelocity": 0.75, "solver": "forceAtlas2Based"}}')
                net_path.save_graph("temp_path.html")
                
                with open("temp_path.html", "r", encoding="utf-8") as f:
                    path_html = f.read()
                    
                path_html = path_html.replace("<body>", f"<body>\n{custom_css}")
                path_html = path_html.replace("network = new vis.Network(container, data, options);", f"network = new vis.Network(container, data, options);\n{custom_js}")
                
                components.html(path_html, height=420)
                    
                with st.expander("View Text Chains"):
                    for i, p in enumerate(paths):
                        chain_text = " -> ".join([f"`{n}`" for n in p])
                        st.markdown(f"**Chain {i+1}:** {chain_text}")
                
        except nx.NodeNotFound:
            st.error("One of the selected entities is missing from the active graph.")

# ==========================================
# TAB 4: AI SAFETY CO-PILOT (LOCAL OLLAMA)
# ==========================================
with tab_chat:
    st.markdown("### Graph DB Copilot")
    st.markdown("Ask natural language questions about the facility's topology, hazards, and safeguards.")
    
    col_cfg1, col_cfg2 = st.columns([1, 3])
    with col_cfg1:
        ollama_model = st.text_input("Local Ollama Model:", value="llama3.2")
    with col_cfg2:
        st.info("Ensure Ollama is running in the background ('ollama run llama3.2').")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    def retrieve_graph_context(user_query, G):
        """Advanced Semantic Graph Traversal for Edge Logic"""
        matched_nodes = set()
        
        # 1. Regex Extraction for "Node X"
        node_matches = re.findall(r'(?i)\bnode\s*(\d+)\b', user_query)
        for num in node_matches:
            target_node = f"Node {num}"
            if target_node in G:
                matched_nodes.add(target_node)
                
        # 2. Fuzzy Ontology Match for Equipment/Drawings
        # Only check against explicit foundational IDs, not giant hazard strings
        if not matched_nodes:
            foundational_nodes = [n for n, attr in G.nodes(data=True) if attr.get('type') in ['Equipment', 'Drawing', 'Node']]
            
            # Find potential tags in query (like P-100 or 40-PI-9004)
            potential_tags = re.findall(r'\b[A-Za-z]{1,4}[- ]?\d{2,5}[A-Za-z]?\b', user_query)
            for ptag in potential_tags:
                match = process.extractOne(ptag.upper(), foundational_nodes, scorer=fuzz.token_sort_ratio, score_cutoff=80)
                if match:
                    matched_nodes.add(match[0])
                    
        # 3. Fallback: Generic Keyword Search (if nothing found)
        if not matched_nodes:
            query_terms = set(user_query.lower().replace('?','').split())
            for n, attr in G.nodes(data=True):
                node_text = f"{n} {attr.get('title', '')}".lower()
                if any(term in node_text for term in query_terms if len(term) > 4):
                    matched_nodes.add(n)
                    
        if not matched_nodes:
            return "No specific topological matches found. Answer based on general Process Safety Knowledge."
            
        context_lines = ["--- EXTRACTED SEMANTIC TOPOLOGY ---"]
        
        # Limit to 2 nodes to avoid exploding context window
        for start_node in list(matched_nodes)[:2]:
            start_type = G.nodes[start_node].get('type', 'Unknown')
            context_lines.append(f"\n[FOCUS ENTITY: {start_node} ({start_type})]")
            
            # Fetch local semantic bowtie to feed to the LLM
            local_subgraph = build_semantic_subgraph(G, start_node)
            for s, t, data in local_subgraph.edges(data=True):
                rel = data.get('relation', 'CONNECTED_TO')
                context_lines.append(f"  {s} ({local_subgraph.nodes[s].get('type')}) -> [{rel}] -> {t} ({local_subgraph.nodes[t].get('type')})")
                
            context_lines.append("  -- Metadata --")
            for node in local_subgraph.nodes():
                 title = local_subgraph.nodes[node].get('title', '')
                 if title and local_subgraph.nodes[node].get('type') in ['Consequence', 'Cause', 'Safeguard']:
                     context_lines.append(f"  {node}: {title[:150]}...")

        return "\n".join(context_lines)

    # Input form locked at the top
    with st.form("chat_form", clear_on_submit=True):
        prompt = st.text_input("Query the system topology...")
        submitted = st.form_submit_button("Send")

    # Render previous messages below the input
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(f"**{message['role'].capitalize()}:**\n{message['content']}")

    if submitted and prompt:
        with st.chat_message("user"):
            st.markdown(f"**User:**\n{prompt}")
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.spinner("Extracting topological context from Knowledge Graph..."):
            graph_context = retrieve_graph_context(prompt, G)
        
        system_prompt = f"""You are an expert Process Safety Management (PSM) AI Assistant.
You answer questions using ONLY the provided extracted graph topology below. 
Do not hallucinate external engineering facts. If the graph does not contain the answer, say so.
Be highly concise, professional, and use bullet points.

{graph_context}
"""
        with st.chat_message("assistant"):
            st.markdown("**System:**")
            message_placeholder = st.empty()
            full_response = ""
            
            payload = {
                "model": ollama_model,
                "prompt": f"{system_prompt}\n\nUser Question: {prompt}",
                "stream": True
            }
            
            try:
                response = requests.post("http://localhost:11434/api/generate", json=payload, stream=True)
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        if "response" in chunk:
                            full_response += chunk["response"]
                            message_placeholder.markdown(full_response + "▌")
                            
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                
                with st.expander("View Extracted Graph Context"):
                    st.text(graph_context)
                    
            except requests.exceptions.ConnectionError:
                st.error("Connection Error: Could not reach Ollama. Is the Ollama app running on your machine?")
            except Exception as e:
                st.error(f"An error occurred: {e}")

# ==========================================
# TAB 5: RELATIONAL DATABASE MASTER
# ==========================================
with tab_raw:
    
    db_path = os.path.join(BASE_DIR, "PSM_Master_Inputs.db")
    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        
        tables = ["Drawings", "Nodes", "Equipment", "Hazard_Scenarios", "Safeguards", "Node_Drawing_Map", "Node_Equipment_Map", "Scenario_Safeguard_Map"]
        tabs_db = st.tabs(tables)
        
        for i, table in enumerate(tables):
            with tabs_db[i]:
                try:
                    df_table = pd.read_sql_query(f"SELECT * FROM {table}", conn)
                    st.dataframe(df_table, height=600)
                except Exception as e:
                    st.error(f"Error loading {table}: {e}")
                    
        conn.close()
    else:
        st.error("PSM_Master_Inputs.db not found.")