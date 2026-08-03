import React, { useState, useEffect, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';
import { Network, BarChart2, GitCommit, MessageSquare, Search, Play, Filter } from 'lucide-react';
import './index.css';

const API_BASE = 'http://localhost:8001/api';

function App() {
  const [activeTab, setActiveTab] = useState('graph');
  
  // Graph State
  const [fullGraphData, setFullGraphData] = useState({ nodes: [], links: [] });
  const [renderGraphData, setRenderGraphData] = useState({ nodes: [], links: [] });
  const [analytics, setAnalytics] = useState(null);
  
  // Window Resizing
  const [windowSize, setWindowSize] = useState({ width: window.innerWidth, height: window.innerHeight });
  
  // Semantic Filter State
  const entityTypes = ["All Entities", "Equipment", "Node", "Deviation", "Cause", "Consequence", "Safeguard"];
  const [filterClass, setFilterClass] = useState('All Entities');
  const [filterInstance, setFilterInstance] = useState('');
  
  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  
  // Traversal State
  const [pathSource, setPathSource] = useState('');
  const [pathTarget, setPathTarget] = useState('');
  const [pathData, setPathData] = useState(null);
  const [pathLoading, setPathLoading] = useState(false);

  const fgRef = useRef();
  const pathFgRef = useRef();

  // Handle Window Resizing
  useEffect(() => {
    const handleResize = () => setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Initial Fetch
  useEffect(() => {
    axios.get(`${API_BASE}/graph`).then(res => {
      setFullGraphData(res.data);
      setRenderGraphData(res.data);
    }).catch(console.error);
    
    axios.get(`${API_BASE}/analytics`).then(res => setAnalytics(res.data)).catch(console.error);
  }, []);

  // Semantic Graph Extraction (Client-Side)
  useEffect(() => {
    if (filterClass === 'All Entities' || !filterInstance) {
      setRenderGraphData(fullGraphData);
      return;
    }
    
    // Depth=1 Bowtie Extraction
    const targetId = filterInstance;
    const relatedLinks = fullGraphData.links.filter(l => {
      const srcId = l.source.id || l.source;
      const tgtId = l.target.id || l.target;
      return srcId === targetId || tgtId === targetId;
    });
    
    const nodeIds = new Set([targetId]);
    relatedLinks.forEach(l => {
      nodeIds.add(l.source.id || l.source);
      nodeIds.add(l.target.id || l.target);
    });
    
    const relatedNodes = fullGraphData.nodes.filter(n => nodeIds.has(n.id));
    setRenderGraphData({ nodes: relatedNodes, links: relatedLinks });
    
  }, [filterClass, filterInstance, fullGraphData]);

  // Handle cascading dropdown reset
  useEffect(() => {
    setFilterInstance('');
  }, [filterClass]);

  const handleChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const newMessages = [...chatMessages, { role: 'user', content: chatInput }];
    setChatMessages(newMessages);
    const query = chatInput;
    setChatInput('');
    try {
      const res = await axios.post(`${API_BASE}/chat`, { query: query, model: 'llama3.2' });
      setChatMessages([...newMessages, { role: 'assistant', content: res.data.response }]);
    } catch (err) {
      setChatMessages([...newMessages, { role: 'assistant', content: "Connection Error." }]);
    }
  };

  const handleTraversal = async () => {
    if(!pathSource || !pathTarget) return;
    setPathLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/path`, { source: pathSource, target: pathTarget });
      setPathData(res.data);
    } catch(err) {
      console.error(err);
    }
    setPathLoading(false);
  };

  return (
    <div id="root">
      {/* SIDEBAR NAVIGATION */}
      <div className="sidebar-nav">
        <div className="sidebar-header">
          <h2>KMGP OS</h2>
          <p>Process Safety Dashboard</p>
        </div>
        
        <div style={{marginTop: '20px'}}>
          <div className={`nav-item ${activeTab === 'graph' ? 'active' : ''}`} onClick={() => setActiveTab('graph')}>
            <Network size={18}/> Knowledge Graph
          </div>
          <div className={`nav-item ${activeTab === 'analytics' ? 'active' : ''}`} onClick={() => setActiveTab('analytics')}>
            <BarChart2 size={18}/> Graph Analytics
          </div>
          <div className={`nav-item ${activeTab === 'traversal' ? 'active' : ''}`} onClick={() => setActiveTab('traversal')}>
            <GitCommit size={18}/> Traversal Engine
          </div>
          <div className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>
            <MessageSquare size={18}/> Graph DB Copilot
          </div>
        </div>
      </div>

      {/* WORKSPACE */}
      <div className="workspace">
        
        {/* TAB 1: KNOWLEDGE GRAPH */}
        <div style={{ display: activeTab === 'graph' ? 'block' : 'none', height: '100%', width: '100%', position: 'relative' }}>
          <div className="controls-overlay panel fade-in">
            <h3 style={{display: 'flex', alignItems: 'center', gap: '8px'}}><Filter size={18}/> Target Isolation</h3>
            
            <label>Entity Class</label>
            <select value={filterClass} onChange={e => setFilterClass(e.target.value)}>
              {entityTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            
            {filterClass !== 'All Entities' && (
              <div className="fade-in">
                <label>Entity Instance</label>
                <select value={filterInstance} onChange={e => setFilterInstance(e.target.value)}>
                  <option value="">-- Select {filterClass} --</option>
                  {fullGraphData.nodes
                    .filter(n => n.group === filterClass)
                    .sort((a,b) => a.id.localeCompare(b.id))
                    .map(n => <option key={n.id} value={n.id}>{n.id}</option>)
                  }
                </select>
              </div>
            )}
            
            <div style={{marginTop: '20px'}}>
              <button onClick={() => fgRef.current.zoomToFit(400)} style={{width: '100%'}}>
                <Search size={14}/> Recenter Topography
              </button>
            </div>
          </div>
          
          <div className="graph-canvas">
            <ForceGraph2D
              ref={fgRef}
              width={windowSize.width - 260} // Sidebar width
              height={windowSize.height}
              graphData={renderGraphData}
              nodeLabel="name"
              nodeColor={n => n.color}
              nodeRelSize={4}
              nodeVal={n => n.val * 3}
              linkColor={() => '#cbd5e1'}
              backgroundColor="#f8fafc"
              onNodeClick={(node) => fgRef.current.centerAt(node.x, node.y, 1000)}
            />
          </div>
        </div>

        {/* TAB 2: ANALYTICS */}
        {activeTab === 'analytics' && (
          <div className="fade-in" style={{padding: '32px', overflowY: 'auto', height: '100%'}}>
            <h2>Graph Analytics</h2>
            
            <div style={{display: 'flex', gap: '24px', marginTop: '24px'}}>
              <div className="panel" style={{flex: 1}}>
                <h3>System Density</h3>
                {analytics ? (
                  <div>
                    <h1 style={{color: 'var(--accent-blue)', margin: '16px 0', fontSize: '36px'}}>{analytics.metrics.nodes} Nodes</h1>
                    <h1 style={{color: 'var(--text-light)', fontSize: '24px'}}>{analytics.metrics.edges} Vectors</h1>
                  </div>
                ) : <p>Loading...</p>}
              </div>
              
              <div className="panel" style={{flex: 2}}>
                <h3>Equipment Vulnerability</h3>
                <div style={{display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '20px'}}>
                  {analytics?.equipment_vulnerability.map((eq, i) => (
                    <div key={i} style={{display: 'flex', alignItems: 'center', gap: '16px'}}>
                      <div className="mono-tag" style={{width: '140px', textAlign: 'center'}}>{eq.label}</div>
                      <div style={{flex: 1, background: '#e2e8f0', height: '12px', borderRadius: '6px'}}>
                        <div style={{width: `${(eq.degree / analytics.equipment_vulnerability[0].degree) * 100}%`, background: 'var(--hazard-red)', height: '100%', borderRadius: '6px'}}></div>
                      </div>
                      <div style={{fontSize: '13px', width: '60px', fontWeight: 600, color: 'var(--text-light)'}}>{eq.degree} vectors</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: TRAVERSAL */}
        {activeTab === 'traversal' && (
          <div className="fade-in" style={{height: '100%', display: 'flex', flexDirection: 'column'}}>
            <div className="panel" style={{margin: '24px', display: 'flex', gap: '20px', alignItems: 'flex-end'}}>
              <div style={{flex: 1}}>
                <label>Origin Node ID</label>
                <input value={pathSource} onChange={e => setPathSource(e.target.value)} placeholder="e.g. Node 3" style={{marginBottom: 0}}/>
              </div>
              <div style={{flex: 1}}>
                <label>Target Node ID</label>
                <input value={pathTarget} onChange={e => setPathTarget(e.target.value)} placeholder="e.g. CON_123" style={{marginBottom: 0}}/>
              </div>
              <button className="primary" onClick={handleTraversal} disabled={pathLoading} style={{marginBottom: 0}}>
                <Play size={16}/> {pathLoading ? 'Computing...' : 'Execute Trace'}
              </button>
            </div>
            
            <div className="graph-canvas" style={{flex: 1, borderTop: '1px solid var(--border-light)'}}>
              {pathData && pathData.nodes.length > 0 ? (
                <ForceGraph2D
                  ref={pathFgRef}
                  width={windowSize.width - 260}
                  height={windowSize.height - 150}
                  graphData={pathData}
                  nodeLabel="name"
                  nodeColor={n => n.color}
                  linkColor={l => l.color}
                  linkDirectionalArrowLength={4}
                  linkDirectionalArrowRelPos={1}
                  backgroundColor="#ffffff"
                />
              ) : (
                <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-light)', background: '#f8fafc'}}>
                  {pathData ? 'No direct path found.' : 'Enter an Origin and Target to visualize causal chains.'}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: CHAT */}
        {activeTab === 'chat' && (
          <div className="fade-in chat-window panel">
            <div style={{borderBottom: '1px solid var(--border-light)', paddingBottom: '20px', marginBottom: '20px'}}>
              <h2>Graph DB Copilot</h2>
              <p style={{margin: 0, fontSize: '14px', color: 'var(--text-light)'}}>Powered by graph semantic extraction and Llama3.2 Edge.</p>
            </div>
            
            <div className="chat-messages">
              {chatMessages.length === 0 && (
                <div style={{textAlign: 'center', color: 'var(--text-light)', marginTop: '60px'}}>
                  System ready. Query the knowledge graph.
                </div>
              )}
              {chatMessages.map((msg, i) => (
                <div key={i} className={`chat-msg ${msg.role === 'user' ? 'msg-user' : 'msg-assistant'}`}>
                  {msg.content}
                </div>
              ))}
            </div>
            
            <form onSubmit={handleChat} style={{display: 'flex', gap: '16px', marginTop: 'auto'}}>
              <input type="text" value={chatInput} onChange={e => setChatInput(e.target.value)} placeholder="Query system topology..." style={{marginBottom: 0, flex: 1}}/>
              <button type="submit" className="primary"><Send size={16}/> Send Query</button>
            </form>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;
