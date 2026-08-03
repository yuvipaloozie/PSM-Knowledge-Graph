import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import os

# --- Page Configuration ---
st.set_page_config(page_title="PSM Safety DB & Analytics", layout="wide")

st.markdown("""
    <style>
    .reportview-container .main .block-container{
        padding-top: 2rem;
    }
    h1, h2, h3 {
        color: #1f3b4d;
        font-family: 'sans serif';
    }
    </style>
""", unsafe_allow_html=True)

st.title("PSM PSM Reconciliation Dashboard")

# --- Database Connection ---
DB_PATH = os.path.join(os.path.dirname(__file__), "PSM_Master_Inputs.db")

@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

try:
    conn = get_connection()
except Exception as e:
    st.error(f"Could not connect to database at {DB_PATH}.\nError: {e}")
    st.stop()

# --- Tabs ---
tab_gap, tab_db, tab_csv = st.tabs(["Gap Analysis", "RDB Explorer", "CSV Explorer"])

# ---------------------------------------------------------
# TAB 1: GAP ANALYSIS DASHBOARD
# ---------------------------------------------------------
with tab_gap:
    st.header("HAZOP-AR Gap analysis")
    
    # Load Gap Data
    try:
        df_gap = pd.read_sql("SELECT * FROM Gap_Analysis_Report", conn)
        
        # --- Helper Functions for Binning ---
        def group_gap_category(val):
            val_upper = str(val).upper()
            if 'TIER 1' in val_upper: return 'Tier 1 Match'
            elif 'TIER 2' in val_upper: return 'Tier 2 Match'
            elif 'FUNCTIONAL GAP' in val_upper: return 'Functional Gap'
            elif 'PARTIAL GAP' in val_upper: return 'Partial Gap'
            else: return 'No Match (Gap)'

        def group_audit_category(val):
            val_upper = str(val).upper()
            if 'CRITICAL MISMATCH' in val_upper: return 'Critical Mismatch'
            elif 'UNDER-RATIONALIZED' in val_upper: return 'Under-Rationalized'
            elif 'UNRATIONALIZED' in val_upper: return 'Unrationalized'
            elif 'ALIGNED' in val_upper: return 'Aligned'
            else: return 'N/A (No Match)'
            
        df_gap['Viz_Gap_Category'] = df_gap['Gap_Category'].apply(group_gap_category)
        df_gap['Viz_Audit_Category'] = df_gap['Risk_Integrity_Audit'].apply(group_audit_category)

        # --- Filters ---
        st.subheader("Data Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            match_filter = st.multiselect(
                "Match Status",
                options=df_gap['Match_Status'].unique(),
                default=df_gap['Match_Status'].unique()
            )
            
        with col2:
            gap_cat_filter = st.multiselect(
                "Gap Category",
                options=df_gap['Viz_Gap_Category'].unique(),
                default=df_gap['Viz_Gap_Category'].unique()
            )
            
        with col3:
            audit_filter = st.multiselect(
                "Risk Integrity Audit",
                options=df_gap['Viz_Audit_Category'].unique(),
                default=df_gap['Viz_Audit_Category'].unique()
            )
            
        # Apply Filters
        filtered_gap = df_gap[
            (df_gap['Match_Status'].isin(match_filter)) &
            (df_gap['Viz_Gap_Category'].isin(gap_cat_filter)) &
            (df_gap['Viz_Audit_Category'].isin(audit_filter))
        ]
        
        st.markdown("---")

        # --- Visualizations ---
        row1_col1, row1_col2, row1_col3 = st.columns(3)
        
        with row1_col1:
            st.subheader("Match Status by Type")
            if not filtered_gap.empty:
                cat_counts = filtered_gap['Viz_Gap_Category'].value_counts().reset_index()
                cat_counts.columns = ['Viz_Gap_Category', 'Count']
                fig1 = px.bar(
                    cat_counts, 
                    x='Count', 
                    y='Viz_Gap_Category', 
                    orientation='h',
                    color='Viz_Gap_Category',
                    color_discrete_sequence=px.colors.sequential.Blues_r
                )
                fig1.update_layout(showlegend=False, xaxis_title="Number of Safeguards", yaxis_title="")
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.info("No data available.")
                
        with row1_col2:
            st.subheader("Severity Comparison Audit")
            if not filtered_gap.empty:
                audit_counts = filtered_gap['Viz_Audit_Category'].value_counts().reset_index()
                audit_counts.columns = ['Viz_Audit_Category', 'Count']
                
                # Custom colors mapping from prototype
                color_map = {
                    'Aligned': '#2ca02c', 
                    'N/A (No Match)': '#7f7f7f',
                    'Unrationalized': '#ff7f0e', 
                    'Under-Rationalized': '#d62728',
                    'Critical Mismatch': '#8c564b'
                }
                
                fig2 = px.pie(
                    audit_counts, 
                    names='Viz_Audit_Category', 
                    values='Count',
                    hole=0.4,
                    color='Viz_Audit_Category',
                    color_discrete_map=color_map
                )
                fig2.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.5, xanchor="center", x=0.5))
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No data available.")

        with row1_col3:
            st.subheader("Missing Alarms by Severity")
            unmatched = filtered_gap[filtered_gap['Match_Status'] == False].copy()
            if not unmatched.empty and 'S' in unmatched.columns:
                def clean_s(val):
                    try: return int(float(str(val).strip()))
                    except: return None
                unmatched['Plot_S'] = unmatched['S'].apply(clean_s)
                unmatched = unmatched.dropna(subset=['Plot_S'])
                unmatched['Plot_S'] = unmatched['Plot_S'].astype(int)
                
                if not unmatched.empty:
                    s_counts = unmatched['Plot_S'].value_counts().reset_index()
                    s_counts.columns = ['Severity', 'Count']
                    # Sort by Severity
                    s_counts = s_counts.sort_values(by='Severity')
                    s_counts['Severity'] = s_counts['Severity'].astype(str)
                    
                    fig3 = px.bar(
                        s_counts,
                        x='Severity',
                        y='Count',
                        color='Severity',
                        color_discrete_sequence=px.colors.sequential.Reds
                    )
                    fig3.update_layout(showlegend=False, xaxis_title="PHA Severity (S) [1-5]", yaxis_title="Count of Missing")
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.info("No numeric severity data available for missing alarms.")
            else:
                st.info("No missing alarms found in selection.")
                
        # --- Data Table ---
        st.subheader("Filtered Data Grid")
        st.dataframe(filtered_gap, use_container_width=True)
        
    except Exception as e:
        st.warning("Gap Analysis Report table not found in the database. Please ensure the pipeline has been run completely.")
        st.error(str(e))

# ---------------------------------------------------------
# TAB 2: RAW DATABASE EXPLORER
# ---------------------------------------------------------
with tab_db:
    st.header("Relational Database Viewer")
    
    tables_df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
    table_names = tables_df['name'].tolist()
    
    if table_names:
        selected_table = st.selectbox("Select a Table to View:", table_names)
        
        if selected_table:
            df_table = pd.read_sql(f"SELECT * FROM {selected_table}", conn)
            st.dataframe(df_table, use_container_width=True)
            st.caption(f"Table: {selected_table} | Total Records: {len(df_table)}")
            
        st.markdown("---")
        st.subheader("Custom SQL Query")
        query = st.text_area("Enter SQL:", value="SELECT * FROM Nodes LIMIT 10;")
        
        if st.button("Execute Query"):
            try:
                query_result = pd.read_sql(query, conn)
                st.success("Query Executed Successfully")
                st.dataframe(query_result, use_container_width=True)
            except Exception as e:
                st.error(f"SQL Error: {e}")
    else:
        st.info("No tables found in the database. Please run the pipeline.")

# ---------------------------------------------------------
# TAB 3: RAW CSV EXPLORER
# ---------------------------------------------------------
with tab_csv:
    st.header("Source Data Explorer")
    st.write("Inspect the raw flat files generated by the NLP and ETL pipeline.")
    
    csv_dir = os.path.join(os.path.dirname(__file__), "Script Outputs")
    if os.path.exists(csv_dir):
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
        
        if csv_files:
            selected_csv = st.selectbox("Select a CSV file to view:", csv_files)
            if selected_csv:
                csv_path = os.path.join(csv_dir, selected_csv)
                try:
                    df_csv = pd.read_csv(csv_path)
                    st.dataframe(df_csv, use_container_width=True)
                    st.caption(f"File: {selected_csv} | Total Records: {len(df_csv)}")
                except Exception as e:
                    st.error(f"Error loading {selected_csv}: {e}")
        else:
            st.info("No CSV files found in 'Script Outputs' folder.")
    else:
        st.error("The 'Script Outputs' folder does not exist.")