import os
import sys
import json
import threading
import time
from datetime import datetime
from pathlib import Path
import base64
import io

sys.path.append(str(Path(__file__).parent.parent))

import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import uuid

from src.simulation_orchestrator import SimulationOrchestrator


app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME])

orchestrator = SimulationOrchestrator()
simulation_results = {}
simulation_status = {"running": False, "progress": 0, "message": "Ready"}
uploaded_data = {"load_profiles": None, "pv_profiles": None, "status": "No files uploaded"}

# Country-specific pricing data (€/kWh) - Based on 2023-2024 residential tariffs
# Sources: Eurostat, national regulatory authorities, major utility companies
COUNTRY_PRICES = {
    "italy": {
        "name": "Italy",
        "off_peak": 0.085,  # ARERA regulated tariff F1/F23 structure
        "on_peak": 0.265,   # Peak hours 8-19 Mon-Fri + Sat morning
        "export_ratio": 0.42, # Scambio sul Posto net metering
        "community_spread": 0.55,
        "currency": "€",
        "notes": "ARERA regulated tariffs (approx. values for research purposes)"
    },
    "germany": {
        "name": "Germany", 
        "off_peak": 0.28,   # Average residential including EEG surcharge
        "on_peak": 0.32,    # German prices are more flat, small peak premium
        "export_ratio": 0.08, # Very low feed-in tariff for new installations
        "community_spread": 0.50,
        "currency": "€",
        "notes": "Approximate German residential tariffs (research estimates)"
    },
    "spain": {
        "name": "Spain",
        "off_peak": 0.075,  # PVPC tariff P3 period (night/weekend)
        "on_peak": 0.195,   # PVPC P1 period (weekday peak)
        "export_ratio": 0.05, # Very low compensation for surplus
        "community_spread": 0.60,
        "currency": "€", 
        "notes": "PVPC time-of-use structure (approximate for research)"
    },
    "sweden": {
        "name": "Sweden",
        "off_peak": 0.08,   # Nord Pool + grid + taxes (low period)
        "on_peak": 0.12,    # Peak period surcharge
        "export_ratio": 0.70, # Good compensation for prosumers
        "community_spread": 0.45,
        "currency": "€",
        "notes": "Nord Pool market + grid tariffs (research approximation)"
    },
    "france": {
        "name": "France",
        "off_peak": 0.175,  # Tarif Bleu Heures Creuses
        "on_peak": 0.235,   # Tarif Bleu Heures Pleines
        "export_ratio": 0.10, # Obligation d'achat tariff
        "community_spread": 0.55,
        "currency": "€",
        "notes": "EDF Tarif Bleu regulated prices (approximate values)"
    },
    "custom": {
        "name": "Custom",
        "off_peak": 0.08,
        "on_peak": 0.25,
        "export_ratio": 0.40,
        "community_spread": 0.50,
        "currency": "€",
        "notes": "Custom pricing - adjust values manually for your research"
    }
}


def parse_uploaded_file(contents, filename):
    """Parse uploaded file and return data"""
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        if filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(decoded))
        elif filename.endswith('.json'):
            data = json.loads(decoded.decode('utf-8'))
            df = pd.DataFrame(data)
        else:
            return None, f"Unsupported file type: {filename}"
        
        return df, f"Successfully loaded {filename} ({df.shape[0]} rows, {df.shape[1]} columns)"
    
    except Exception as e:
        return None, f"Error parsing {filename}: {str(e)}"


def save_uploaded_data_to_framework(df, data_type):
    """Save uploaded data to the framework data directory"""
    try:
        data_dir = Path("data/input")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        if data_type == "load_profiles":
            filepath = data_dir / "load_profiles.csv"
            df.to_csv(filepath, index=False)
        elif data_type == "pv_profiles":
            filepath = data_dir / "pv_profiles.csv"
            df.to_csv(filepath, index=False)
        
        return True, str(filepath)
    except Exception as e:
        return False, str(e)


app.layout = dbc.Container([
    dcc.Store(id='simulation-data'),
    dcc.Interval(id='interval-component', interval=2000, n_intervals=0),
    
    # Header
    dbc.Row([
        dbc.Col([
            html.H1([
                html.I(className="fas fa-bolt me-2"),
                "Dynamic Tariff Benchmarking Framework"
            ], className="text-center mb-2"),
            html.P("Optimize electricity costs and fairness in prosumer communities", 
                   className="text-center text-muted mb-4")
        ])
    ]),
    
    # Main content in two columns
    dbc.Row([
        # Left column - Configuration
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H4([html.I(className="fas fa-cog me-2"), "Configuration"], className="mb-0")
                ]),
                dbc.CardBody([
                    # Basic settings
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Buildings"),
                            dbc.Input(id="num-buildings", type="number", value=10, min=2, max=20)
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Time Steps"),
                            dbc.Input(id="time-horizon", type="number", value=96, min=24, max=288)
                        ], width=6)
                    ], className="mb-3"),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Scenarios"),
                            dbc.Input(id="num-scenarios", type="number", value=15, min=5, max=50)
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Rapid Evals"),
                            dbc.Input(id="rapid-eval", type="number", value=500, min=0, max=2000)
                        ], width=6)
                    ], className="mb-3"),
                    
                    # Country Selection
                    dbc.Label("Country"),
                    html.Small("Approximate pricing for research purposes", className="text-muted d-block mb-1"),
                    dcc.Dropdown([
                        {"label": "🇮🇹 Italy", "value": "italy"},
                        {"label": "🇩🇪 Germany", "value": "germany"},
                        {"label": "🇪🇸 Spain", "value": "spain"},
                        {"label": "🇸🇪 Sweden", "value": "sweden"},
                        {"label": "🇫🇷 France", "value": "france"},
                        {"label": "🔧 Custom", "value": "custom"}
                    ], value="italy", id="country-selector", className="mb-3"),
                    
                    # Tariff Selection
                    dbc.Label("Tariff Type"),
                    html.Small("Select one tariff structure to analyze", className="text-muted d-block mb-2"),
                    dcc.Dropdown([
                        {"label": "Time-of-Use (ToU) - Fixed peak/off-peak periods", "value": "tou"},
                        {"label": "Critical Peak Pricing (CPP) - Event-based pricing", "value": "cpp"},
                        {"label": "Real-Time Pricing (RTP) - Variable hourly rates", "value": "rtp"},
                        {"label": "Emergency Demand Response (EDR) - Extreme event pricing", "value": "edr"}
                    ], value="tou", id="tariff-type", className="mb-3"),
                    
                    # Country pricing info
                    html.Div(id="country-pricing-info", className="mb-3"),
                    
                    # Price Configuration
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Off-Peak (€/kWh)", size="sm"),
                            dbc.Input(id="off-peak-price", type="number", value=0.09, step=0.01, size="sm")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("On-Peak (€/kWh)", size="sm"),
                            dbc.Input(id="on-peak-price", type="number", value=0.28, step=0.01, size="sm")
                        ], width=6)
                    ], className="mb-2"),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Export Ratio", size="sm"),
                            dbc.Input(id="export-ratio", type="number", value=0.45, step=0.1, min=0, max=1, size="sm")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Community Spread", size="sm"),
                            dbc.Input(id="community-spread", type="number", value=0.55, step=0.1, min=0, max=1, size="sm")
                        ], width=6)
                    ], className="mb-3"),
                    
                    # Options
                    dbc.Label("Analysis Options"),
                    dbc.Checklist([
                        {"label": "P2P Trading", "value": "p2p"},
                        {"label": "Surrogate Model", "value": "surrogate"},
                        {"label": "Sensitivity Analysis", "value": "sensitivity"}
                    ], value=["p2p"], id="options", className="mb-3"),
                    
                    # File upload section
                    html.Hr(),
                    dbc.Label("Data Upload (Optional)"),
                    html.Small("Upload custom load profiles or PV generation data", className="text-muted d-block mb-2"),
                    
                    dcc.Upload(
                        id='upload-data',
                        children=dbc.Button([
                            html.I(className="fas fa-upload me-2"),
                            "Upload Data (.csv, .xlsx, .json)"
                        ], color="outline-primary", size="sm", className="w-100"),
                        style={
                            'marginBottom': '10px',
                            'borderRadius': '5px',
                            'borderStyle': 'dashed',
                            'borderColor': '#007bff',
                            'textAlign': 'center',
                            'padding': '5px'
                        },
                        accept='.csv,.xlsx,.json'
                    ),
                    
                    dbc.Collapse([
                        dbc.Alert([
                            html.H6("File Format Guide:", className="mb-2"),
                            html.Ul([
                                html.Li("CSV/Excel: Rows = time steps, Columns = buildings"),
                                html.Li("Include 'load' or 'demand' in filename for load profiles"),
                                html.Li("Include 'pv', 'solar', or 'generation' for PV data"),
                                html.Li("Data will be automatically resized to match simulation settings")
                            ], className="mb-0 small")
                        ], color="info", className="small py-2")
                    ], id="upload-help", is_open=False),
                    
                    dbc.Button("Show Format Help", id="help-toggle", color="link", size="sm", className="p-0 mb-2"),
                    html.Div(id='upload-status', className="mb-3"),
                    
                    # Control buttons
                    dbc.ButtonGroup([
                        dbc.Button("Start Simulation", id="start-btn", color="primary", size="lg"),
                        dbc.Button("Stop", id="stop-btn", color="danger", disabled=True)
                    ], className="w-100 mb-3"),
                    
                    # Status
                    html.Div(id="status-display"),
                    dbc.Progress(id="progress-bar", value=0, className="mb-2"),
                    
                    # Quick actions
                    html.Hr(),
                    dbc.Button("Download Results", id="download-btn", color="success", 
                              className="w-100 mb-2", disabled=True),
                    dbc.Button("Reset", id="reset-btn", color="secondary", className="w-100 mb-3"),
                    
                    # Data sources disclaimer
                    dbc.Collapse([
                        dbc.Alert([
                            html.H6("Data Sources & Disclaimer", className="mb-2"),
                            html.P("Pricing data are research approximations based on:", className="small mb-1"),
                            html.Ul([
                                html.Li("🇮🇹 ARERA regulated tariffs structure", className="small"),
                                html.Li("🇩🇪 Average residential tariffs + EEG surcharge", className="small"),
                                html.Li("🇪🇸 PVPC time-of-use structure", className="small"),
                                html.Li("🇸🇪 Nord Pool market + grid components", className="small"),
                                html.Li("🇫🇷 EDF Tarif Bleu regulated rates", className="small")
                            ], className="mb-2"),
                            html.P("⚠️ For research purposes only. Use real tariff data for commercial applications.", 
                                   className="small text-warning mb-0")
                        ], color="light", className="small py-2")
                    ], id="sources-info", is_open=False),
                    
                    dbc.Button("📚 Data Sources", id="sources-toggle", color="link", size="sm", className="p-0")
                ])
            ])
        ], width=4),
        
        # Right column - Results and Analysis
        dbc.Col([
            # Results summary cards
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("0", id="total-scenarios", className="text-primary"),
                            html.P("Scenarios", className="mb-0")
                        ], className="text-center")
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("€0.00", id="avg-cost", className="text-success"),
                            html.P("Avg Cost", className="mb-0")
                        ], className="text-center")
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("0.000", id="avg-fairness", className="text-warning"),
                            html.P("Fairness", className="mb-0")
                        ], className="text-center")
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("0%", id="p2p-savings", className="text-info"),
                            html.P("P2P Savings", className="mb-0")
                        ], className="text-center")
                    ])
                ], width=3)
            ], className="mb-4"),
            
            # Advanced Analytics Tabs
            dbc.Card([
                dbc.CardHeader([
                    html.H5([
                        html.I(className="fas fa-chart-line me-2"),
                        "Advanced Analytics Dashboard"
                    ], className="mb-0"),
                    html.Small(id="selected-tariffs-info", className="text-muted d-block mt-1")
                ]),
                dbc.CardBody([
                    dbc.Tabs([
                        dbc.Tab(label="📊 Overview", tab_id="overview-tab"),
                        dbc.Tab(label="💰 Cost Analysis", tab_id="cost-tab"),
                        dbc.Tab(label="⚖️ Fairness Analysis", tab_id="fairness-tab"),
                        dbc.Tab(label="🔄 P2P Trading", tab_id="p2p-tab"),
                        dbc.Tab(label="⚡ Energy Flow", tab_id="energy-tab"),
                        dbc.Tab(label="📈 Performance", tab_id="performance-tab")
                    ], id="analytics-tabs", active_tab="overview-tab", className="mb-3"),
                    
                    html.Div(id="analytics-content")
                ])
            ], className="mb-4"),
            
            # Results table with better explanations
            dbc.Card([
                dbc.CardHeader([
                    dbc.Row([
                        dbc.Col([
                            html.H5("📊 Scenario Results", className="mb-0"),
                            html.Small("Ranked by overall performance (lower cost + better fairness)", className="text-muted")
                        ], width=8),
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="fas fa-info-circle me-1"), "Help"], 
                                id="results-help-toggle", 
                                color="link", 
                                size="sm"
                            )
                        ], width=4, className="text-end")
                    ])
                ]),
                dbc.CardBody([
                    # Help collapse
                    dbc.Collapse([
                        dbc.Alert([
                            html.H6("📋 Understanding the Results", className="mb-2"),
                            html.Ul([
                                html.Li([html.Strong("Rank:"), " Best scenarios ranked #1, #2, #3... (lower rank = better)"]),
                                html.Li([html.Strong("Scenario:"), " Each scenario tests different tariff and building configurations"]),
                                html.Li([html.Strong("Total Cost:"), " Average electricity cost per building (€) - lower is better"]),
                                html.Li([html.Strong("Fairness:"), " How equal costs are across buildings (0.0-1.0) - lower is more fair"]),
                                html.Li([html.Strong("P2P Trading:"), " Whether peer-to-peer energy sharing is enabled"]),
                                html.Li([html.Strong("Savings:"), " Cost reduction compared to baseline scenario"]),
                                html.Li([html.Strong("Performance:"), " Overall score combining cost and fairness (★★★★★)"])
                            ], className="mb-2 small"),
                            html.P("💡 Green rows indicate P2P trading scenarios, which typically offer better cost savings.", 
                                   className="small text-success mb-0")
                        ], color="info", className="small py-2")
                    ], id="results-help", is_open=False),
                    
                    dash_table.DataTable(
                        id="results-table",
                        columns=[
                            {"name": "Rank", "id": "rank", "type": "numeric"},
                            {"name": "Scenario", "id": "scenario"},
                            {"name": "Total Cost (€)", "id": "cost", "type": "numeric", "format": {"specifier": ".2f"}},
                            {"name": "Fairness", "id": "fairness", "type": "numeric", "format": {"specifier": ".3f"}},
                            {"name": "P2P Trading", "id": "p2p"},
                            {"name": "Savings (%)", "id": "savings", "type": "numeric", "format": {"specifier": ".1f"}},
                            {"name": "Performance", "id": "performance"}
                        ],
                        data=[],
                        sort_action="native",
                        style_cell={
                            'textAlign': 'left', 
                            'fontSize': '13px',
                            'padding': '8px',
                            'whiteSpace': 'normal',
                            'height': 'auto'
                        },
                        style_header={
                            'backgroundColor': '#f8f9fa',
                            'fontWeight': 'bold',
                            'fontSize': '14px',
                            'color': '#495057',
                            'border': '1px solid #dee2e6'
                        },
                        style_data_conditional=[
                            {
                                'if': {'filter_query': '{p2p} = ✅ Yes'},
                                'backgroundColor': '#e8f5e8',
                            },
                            {
                                'if': {'column_id': 'rank', 'filter_query': '{rank} = 1'},
                                'backgroundColor': '#ffd700',
                                'fontWeight': 'bold'
                            },
                            {
                                'if': {'column_id': 'rank', 'filter_query': '{rank} = 2'},
                                'backgroundColor': '#f0f0f0',
                                'fontWeight': 'bold'
                            },
                            {
                                'if': {'column_id': 'rank', 'filter_query': '{rank} = 3'},
                                'backgroundColor': '#f5f5f5',
                                'fontWeight': 'bold'
                            }
                        ],
                        style_cell_conditional=[
                            {'if': {'column_id': 'rank'}, 'width': '60px', 'textAlign': 'center'},
                            {'if': {'column_id': 'scenario'}, 'width': '200px'},
                            {'if': {'column_id': 'cost'}, 'width': '120px', 'textAlign': 'right'},
                            {'if': {'column_id': 'fairness'}, 'width': '100px', 'textAlign': 'right'},
                            {'if': {'column_id': 'p2p'}, 'width': '100px', 'textAlign': 'center'},
                            {'if': {'column_id': 'savings'}, 'width': '100px', 'textAlign': 'right'},
                            {'if': {'column_id': 'performance'}, 'width': '120px', 'textAlign': 'center'}
                        ],
                        page_size=10,
                        style_table={'overflowX': 'auto'}
                    )
                ])
            ])
        ], width=8)
    ])
], fluid=True, className="py-4")


@app.callback(
    [Output("country-pricing-info", "children"),
     Output("off-peak-price", "value"),
     Output("on-peak-price", "value"),
     Output("export-ratio", "value"),
     Output("community-spread", "value"),
     Output("off-peak-price", "disabled"),
     Output("on-peak-price", "disabled"),
     Output("export-ratio", "disabled"),
     Output("community-spread", "disabled")],
    [Input("country-selector", "value")]
)
def update_country_pricing(country):
    if not country or country not in COUNTRY_PRICES:
        country = "italy"
    
    pricing = COUNTRY_PRICES[country]
    is_custom = country == "custom"
    
    # Create pricing info display
    info_card = dbc.Alert([
        html.H6(f"{pricing['name']} Electricity Prices", className="mb-2"),
        html.P(pricing['notes'], className="mb-2 small"),
        html.Div([
            dbc.Badge(f"Off-Peak: {pricing['off_peak']:.3f} {pricing['currency']}/kWh", color="success", className="me-2"),
            dbc.Badge(f"On-Peak: {pricing['on_peak']:.3f} {pricing['currency']}/kWh", color="warning")
        ])
    ], color="info", className="small py-2")
    
    return (info_card,
            pricing['off_peak'],
            pricing['on_peak'], 
            pricing['export_ratio'],
            pricing['community_spread'],
            not is_custom,  # disabled when not custom
            not is_custom,
            not is_custom,
            not is_custom)


@app.callback(
    Output("selected-tariffs-info", "children"),
    [Input("tariff-type", "value"),
     Input("country-selector", "value"),
     Input("off-peak-price", "value"),
     Input("on-peak-price", "value")]
)
def update_tariff_info(tariff_type, country, off_peak, on_peak):
    if not tariff_type:
        return "No tariff selected"
    
    tariff_names = {
        'tou': 'Time-of-Use',
        'cpp': 'Critical Peak Pricing', 
        'rtp': 'Real-Time Pricing',
        'edr': 'Emergency Demand Response'
    }
    
    country_names = {
        'italy': '🇮🇹 Italy',
        'germany': '🇩🇪 Germany',
        'spain': '🇪🇸 Spain', 
        'sweden': '🇸🇪 Sweden',
        'france': '🇫🇷 France',
        'custom': '🔧 Custom'
    }
    
    tariff_name = tariff_names.get(tariff_type, tariff_type)
    country_name = country_names.get(country, country)
    price_info = f" | {off_peak or 0.08:.3f}-{on_peak or 0.25:.3f} €/kWh" if off_peak and on_peak else ""
    
    return f"{tariff_name} - {country_name}{price_info}"


@app.callback(
    Output("sources-info", "is_open"),
    [Input("sources-toggle", "n_clicks")],
    [State("sources-info", "is_open")]
)
def toggle_sources_info(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


@app.callback(
    Output("upload-help", "is_open"),
    [Input("help-toggle", "n_clicks")],
    [State("upload-help", "is_open")]
)
def toggle_upload_help(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


@app.callback(
    Output("results-help", "is_open"),
    [Input("results-help-toggle", "n_clicks")],
    [State("results-help", "is_open")]
)
def toggle_results_help(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


@app.callback(
    Output('upload-status', 'children'),
    [Input('upload-data', 'contents')],
    [State('upload-data', 'filename')]
)
def update_upload_status(contents, filename):
    if contents is None:
        return dbc.Alert("No file uploaded", color="light", className="small py-1")
    
    global uploaded_data
    
    df, message = parse_uploaded_file(contents, filename)
    
    if df is not None:
        # Determine if it's load profiles or PV profiles based on filename or content
        if 'load' in filename.lower() or 'demand' in filename.lower():
            success, filepath = save_uploaded_data_to_framework(df, "load_profiles")
            if success:
                uploaded_data["load_profiles"] = df
                uploaded_data["status"] = f"Load profiles: {message}"
                return dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    f"Load profiles uploaded: {df.shape[0]} time steps, {df.shape[1]} buildings"
                ], color="success", className="small py-1")
        
        elif 'pv' in filename.lower() or 'solar' in filename.lower() or 'generation' in filename.lower():
            success, filepath = save_uploaded_data_to_framework(df, "pv_profiles")
            if success:
                uploaded_data["pv_profiles"] = df
                uploaded_data["status"] = f"PV profiles: {message}"
                return dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    f"PV profiles uploaded: {df.shape[0]} time steps, {df.shape[1]} buildings"
                ], color="success", className="small py-1")
        
        else:
            # Default to load profiles if unclear
            success, filepath = save_uploaded_data_to_framework(df, "load_profiles")
            if success:
                uploaded_data["load_profiles"] = df
                uploaded_data["status"] = f"Data (assumed load profiles): {message}"
                return dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    f"Data uploaded as load profiles: {df.shape[0]} time steps, {df.shape[1]} buildings"
                ], color="info", className="small py-1")
    
    return dbc.Alert([
        html.I(className="fas fa-exclamation-triangle me-2"),
        message
    ], color="danger", className="small py-1")


def run_simulation_thread(config):
    global simulation_status, simulation_results
    
    try:
        simulation_status = {"running": True, "progress": 10, "message": "Initializing..."}
        
        orchestrator.num_buildings = config['num_buildings']
        orchestrator.time_horizon = config['time_horizon']
        
        # Check if we have uploaded data to use
        if uploaded_data["load_profiles"] is not None:
            simulation_status["message"] = "Using uploaded load profiles..."
        
        # Configure tariff manager with custom settings
        orchestrator.tariff_manager.create_default_tariffs()
        
        # Update tariff prices based on user configuration
        tariff_type = config['tariff_type']
        country = config['country']
        
        if tariff_type == 'tou':
            tou_tariff = orchestrator.tariff_manager.get_tariff('Time-of-Use')
            if tou_tariff:
                tou_tariff.off_peak_price = config['off_peak_price']
                tou_tariff.on_peak_price = config['on_peak_price']
        
        orchestrator.initialize()
        
        simulation_status["progress"] = 30
        country_name = COUNTRY_PRICES.get(country, {}).get('name', country)
        simulation_status["message"] = f"Running {tariff_type.upper()} scenarios for {country_name}..."
        
        results = orchestrator.benchmark_tariff_scenarios(
            num_scenarios=config['num_scenarios'],
            include_p2p_comparison=config['include_p2p']
        )
        
        simulation_status["progress"] = 70
        simulation_status["message"] = "Processing results..."
        
        if config['train_surrogate']:
            surrogate_results = orchestrator.train_surrogate_model()
            results['surrogate'] = surrogate_results
            simulation_status["progress"] = 85
        
        if config['rapid_eval'] > 0:
            rapid_results = orchestrator.rapid_scenario_evaluation(config['rapid_eval'])
            results['rapid_evaluation'] = rapid_results
            simulation_status["progress"] = 95
        
        simulation_results = results
        simulation_status = {"running": False, "progress": 100, "message": "Completed successfully!"}
        
    except Exception as e:
        simulation_status = {"running": False, "progress": 0, "message": f"Error: {str(e)}"}


@app.callback(
    [Output("status-display", "children"),
     Output("progress-bar", "value"),
     Output("start-btn", "disabled"),
     Output("stop-btn", "disabled"),
     Output("download-btn", "disabled"),
     Output("simulation-data", "data")],
    [Input("interval-component", "n_intervals"),
     Input("start-btn", "n_clicks"),
     Input("stop-btn", "n_clicks"),
     Input("reset-btn", "n_clicks")],
    [State("num-buildings", "value"),
     State("time-horizon", "value"),
     State("num-scenarios", "value"),
     State("rapid-eval", "value"),
     State("options", "value"),
     State("tariff-type", "value"),
     State("country-selector", "value"),
     State("off-peak-price", "value"),
     State("on-peak-price", "value"),
     State("export-ratio", "value"),
     State("community-spread", "value")]
)
def update_simulation_control(n_intervals, start_clicks, stop_clicks, reset_clicks,
                            num_buildings, time_horizon, num_scenarios, rapid_eval, options,
                            tariff_type, country, off_peak_price, on_peak_price, export_ratio, community_spread):
    global simulation_status, simulation_results
    
    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if trigger_id == 'start-btn' and start_clicks and not simulation_status["running"]:
        config = {
            'num_buildings': num_buildings or 10,
            'time_horizon': time_horizon or 96,
            'num_scenarios': num_scenarios or 15,
            'rapid_eval': rapid_eval or 0,
            'include_p2p': 'p2p' in (options or []),
            'train_surrogate': 'surrogate' in (options or []),
            'sensitivity': 'sensitivity' in (options or []),
            'tariff_type': tariff_type or 'tou',
            'country': country or 'italy',
            'off_peak_price': off_peak_price or 0.08,
            'on_peak_price': on_peak_price or 0.25,
            'export_ratio': export_ratio or 0.4,
            'community_spread': community_spread or 0.5
        }
        
        thread = threading.Thread(target=run_simulation_thread, args=(config,), daemon=True)
        thread.start()
    
    elif trigger_id == 'stop-btn':
        simulation_status = {"running": False, "progress": 0, "message": "Stopped by user"}
    
    elif trigger_id == 'reset-btn':
        simulation_status = {"running": False, "progress": 0, "message": "Ready"}
        simulation_results = {}
    
    # Status display
    if simulation_status["running"]:
        status_color = "primary"
        status_text = f"{simulation_status['message']} ({simulation_status['progress']}%)"
    elif simulation_status["progress"] == 100:
        status_color = "success"
        status_text = simulation_status['message']
    elif "Error" in simulation_status['message']:
        status_color = "danger"
        status_text = simulation_status['message']
    else:
        status_color = "secondary"
        status_text = simulation_status['message']
    
    status_badge = dbc.Badge(status_text, color=status_color, className="w-100 p-2")
    
    return (status_badge,
            simulation_status['progress'],
            simulation_status['running'],
            not simulation_status['running'],
            len(simulation_results) == 0,
            simulation_results)


@app.callback(
    [Output("total-scenarios", "children"),
     Output("avg-cost", "children"),
     Output("avg-fairness", "children"),
     Output("p2p-savings", "children")],
    [Input("simulation-data", "data")]
)
def update_summary_cards(simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return "0", "€0.00", "0.000", "0%"
    
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    if not successful:
        return "0", "€0.00", "0.000", "0%"
    
    total_scenarios = len(successful)
    avg_cost = np.mean([v['total_cost'] for v in successful.values()])
    avg_fairness = np.mean([v['fairness'] for v in successful.values()])
    
    # Calculate P2P savings
    p2p_scenarios = {k: v for k, v in successful.items() if v.get('with_p2p', False)}
    no_p2p_scenarios = {k: v for k, v in successful.items() if not v.get('with_p2p', True)}
    
    if p2p_scenarios and no_p2p_scenarios:
        p2p_avg = np.mean([v['total_cost'] for v in p2p_scenarios.values()])
        no_p2p_avg = np.mean([v['total_cost'] for v in no_p2p_scenarios.values()])
        savings_pct = ((no_p2p_avg - p2p_avg) / no_p2p_avg) * 100 if no_p2p_avg > 0 else 0
    else:
        savings_pct = 0
    
    return (str(total_scenarios),
            f"€{avg_cost:.2f}",
            f"{avg_fairness:.3f}",
            f"{savings_pct:.1f}%")


@app.callback(
    Output("analytics-content", "children"),
    [Input("analytics-tabs", "active_tab"),
     Input("simulation-data", "data")]
)
def render_analytics_tab(active_tab, simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return dbc.Alert(
            "No simulation data available. Please run a simulation to view analytics.",
            color="info", className="text-center"
        )
    
    if active_tab == "overview-tab":
        return create_overview_analytics(simulation_data)
    elif active_tab == "cost-tab":
        return create_cost_analytics(simulation_data)
    elif active_tab == "fairness-tab":
        return create_fairness_analytics(simulation_data)
    elif active_tab == "p2p-tab":
        return create_p2p_analytics(simulation_data)
    elif active_tab == "energy-tab":
        return create_energy_analytics(simulation_data)
    elif active_tab == "performance-tab":
        return create_performance_analytics(simulation_data)
    
    return html.Div("Select an analytics tab")


def create_overview_analytics(simulation_data):
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    if not successful:
        return dbc.Alert("No successful scenarios to analyze", color="warning")
    
    names = list(successful.keys())
    costs = [v['total_cost'] for v in successful.values()]
    fairness = [v['fairness'] for v in successful.values()]
    p2p_status = ['P2P Trading' if v.get('with_p2p', False) else 'Grid Only' for v in successful.values()]
    
    # Create cost vs fairness scatter plot
    scatter_fig = px.scatter(
        x=costs, y=fairness, color=p2p_status, hover_name=names,
        title="🎯 Cost vs Fairness Trade-off Analysis",
        labels={'x': 'Total Cost (€)', 'y': 'Fairness (Coefficient of Variation)'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    scatter_fig.update_layout(height=400)
    
    # Create cost distribution
    cost_hist = px.histogram(
        x=costs, nbins=8, color=p2p_status,
        title="💰 Cost Distribution Across Scenarios",
        labels={'x': 'Total Cost (€)', 'y': 'Number of Scenarios'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    cost_hist.update_layout(height=350)
    
    # Create summary metrics
    avg_cost = np.mean(costs)
    avg_fairness = np.mean(fairness)
    best_scenario = min(successful.items(), key=lambda x: x[1]['total_cost'])
    most_fair = min(successful.items(), key=lambda x: x[1]['fairness'])
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=scatter_fig)
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("📋 Quick Insights"),
                dbc.CardBody([
                    html.H6("Best Cost Scenario:", className="text-primary"),
                    html.P(f"{best_scenario[0][:30]}...", className="small mb-2"),
                    html.P(f"€{best_scenario[1]['total_cost']:.2f}", className="h5 text-success mb-3"),
                    
                    html.H6("Most Fair Scenario:", className="text-primary"),
                    html.P(f"{most_fair[0][:30]}...", className="small mb-2"),
                    html.P(f"{most_fair[1]['fairness']:.3f} CoV", className="h5 text-info mb-3"),
                    
                    html.Hr(),
                    html.P([html.Strong("Average Cost: "), f"€{avg_cost:.2f}"], className="mb-1"),
                    html.P([html.Strong("Average Fairness: "), f"{avg_fairness:.3f}"], className="mb-1"),
                    html.P([html.Strong("Total Scenarios: "), f"{len(successful)}"], className="mb-0")
                ])
            ])
        ], width=4),
        dbc.Col([
            dcc.Graph(figure=cost_hist)
        ], width=12, className="mt-3")
    ])


def create_cost_analytics(simulation_data):
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    names = list(successful.keys())
    costs = [v['total_cost'] for v in successful.values()]
    p2p_status = ['P2P Trading' if v.get('with_p2p', False) else 'Grid Only' for v in successful.values()]
    
    # Cost comparison bar chart
    bar_fig = px.bar(
        x=names, y=costs, color=p2p_status,
        title="💰 Detailed Cost Comparison by Scenario",
        labels={'x': 'Scenario', 'y': 'Total Cost (€)'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    bar_fig.update_xaxes(tickangle=45)
    bar_fig.update_layout(height=450)
    
    # Box plot for P2P vs Grid Only comparison
    box_fig = px.box(
        x=p2p_status, y=costs,
        title="📦 Cost Distribution: P2P Trading vs Grid Only",
        labels={'x': 'Trading Type', 'y': 'Total Cost (€)'},
        color=p2p_status,
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    box_fig.update_layout(height=350)
    
    # Calculate savings
    p2p_costs = [cost for cost, p2p in zip(costs, p2p_status) if p2p == 'P2P Trading']
    grid_costs = [cost for cost, p2p in zip(costs, p2p_status) if p2p == 'Grid Only']
    
    if p2p_costs and grid_costs:
        avg_p2p = np.mean(p2p_costs)
        avg_grid = np.mean(grid_costs)
        savings = ((avg_grid - avg_p2p) / avg_grid) * 100
    else:
        savings = 0
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=bar_fig)
        ], width=12),
        dbc.Col([
            dcc.Graph(figure=box_fig)
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("💡 Cost Insights"),
                dbc.CardBody([
                    html.H4(f"{savings:.1f}%", className="text-success"),
                    html.P("Average P2P Savings", className="text-muted mb-3"),
                    
                    html.P([html.Strong("P2P Average: "), f"€{np.mean(p2p_costs):.2f}" if p2p_costs else "N/A"], className="mb-1"),
                    html.P([html.Strong("Grid Average: "), f"€{np.mean(grid_costs):.2f}" if grid_costs else "N/A"], className="mb-1"),
                    html.P([html.Strong("Best Cost: "), f"€{min(costs):.2f}"], className="mb-1"),
                    html.P([html.Strong("Worst Cost: "), f"€{max(costs):.2f}"], className="mb-0")
                ])
            ])
        ], width=4)
    ])


def create_fairness_analytics(simulation_data):
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    names = list(successful.keys())
    fairness = [v['fairness'] for v in successful.values()]
    costs = [v['total_cost'] for v in successful.values()]
    p2p_status = ['P2P Trading' if v.get('with_p2p', False) else 'Grid Only' for v in successful.values()]
    
    # Fairness histogram
    hist_fig = px.histogram(
        x=fairness, nbins=10, color=p2p_status,
        title="⚖️ Fairness Distribution (Coefficient of Variation)",
        labels={'x': 'Fairness (CoV) - Lower is More Fair', 'y': 'Number of Scenarios'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    hist_fig.add_vline(x=np.mean(fairness), line_dash="dash", annotation_text="Average")
    hist_fig.update_layout(height=400)
    
    # Fairness vs Cost scatter with trend
    trend_fig = px.scatter(
        x=fairness, y=costs, color=p2p_status, hover_name=names,
        title="📈 Fairness vs Cost Relationship",
        labels={'x': 'Fairness (CoV)', 'y': 'Total Cost (€)'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'},
        trendline="ols"
    )
    trend_fig.update_layout(height=400)
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=hist_fig)
        ], width=6),
        dbc.Col([
            dcc.Graph(figure=trend_fig)
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("📊 Fairness Metrics"),
                dbc.CardBody([
                    html.P([html.Strong("Most Fair: "), f"{min(fairness):.3f} CoV"], className="text-success mb-2"),
                    html.P([html.Strong("Least Fair: "), f"{max(fairness):.3f} CoV"], className="text-danger mb-2"),
                    html.P([html.Strong("Average: "), f"{np.mean(fairness):.3f} CoV"], className="mb-2"),
                    html.Hr(),
                    html.H6("Interpretation:", className="text-primary"),
                    html.Ul([
                        html.Li("CoV < 0.2: Very Fair", className="small text-success"),
                        html.Li("CoV 0.2-0.4: Moderately Fair", className="small text-warning"),
                        html.Li("CoV > 0.4: Less Fair", className="small text-danger")
                    ])
                ])
            ])
        ], width=12, className="mt-3")
    ])


def create_p2p_analytics(simulation_data):
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    # Separate P2P and Grid scenarios
    p2p_scenarios = {k: v for k, v in successful.items() if v.get('with_p2p', False)}
    grid_scenarios = {k: v for k, v in successful.items() if not v.get('with_p2p', True)}
    
    if not p2p_scenarios:
        return dbc.Alert("No P2P trading scenarios found", color="info")
    
    # P2P Impact Analysis
    p2p_costs = [v['total_cost'] for v in p2p_scenarios.values()]
    grid_costs = [v['total_cost'] for v in grid_scenarios.values()] if grid_scenarios else []
    
    # Create comparison chart
    comparison_data = []
    if grid_costs:
        comparison_data.extend([{'Type': 'Grid Only', 'Cost': cost} for cost in grid_costs])
    comparison_data.extend([{'Type': 'P2P Trading', 'Cost': cost} for cost in p2p_costs])
    
    df_comparison = pd.DataFrame(comparison_data)
    
    violin_fig = px.violin(
        df_comparison, x='Type', y='Cost',
        title="🔄 P2P Trading Impact on Costs",
        labels={'Cost': 'Total Cost (€)'},
        color='Type',
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    violin_fig.update_layout(height=400)
    
    # P2P Benefits breakdown
    if grid_costs and p2p_costs:
        avg_savings = ((np.mean(grid_costs) - np.mean(p2p_costs)) / np.mean(grid_costs)) * 100
        min_savings = ((max(grid_costs) - min(p2p_costs)) / max(grid_costs)) * 100
    else:
        avg_savings = 0
        min_savings = 0
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=violin_fig)
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("🔄 P2P Trading Benefits"),
                dbc.CardBody([
                    html.H4(f"{avg_savings:.1f}%", className="text-success"),
                    html.P("Average Cost Savings", className="text-muted mb-3"),
                    
                    html.H5(f"{min_savings:.1f}%", className="text-info"),
                    html.P("Maximum Potential Savings", className="text-muted mb-3"),
                    
                    html.Hr(),
                    html.P([html.Strong("P2P Scenarios: "), f"{len(p2p_scenarios)}"], className="mb-1"),
                    html.P([html.Strong("Grid Scenarios: "), f"{len(grid_scenarios)}"], className="mb-1"),
                    
                    html.Hr(),
                    html.H6("Key Benefits:", className="text-primary"),
                    html.Ul([
                        html.Li("Lower average costs", className="small"),
                        html.Li("Better resource utilization", className="small"),
                        html.Li("Reduced grid dependency", className="small"),
                        html.Li("Community energy sharing", className="small")
                    ])
                ])
            ])
        ], width=4)
    ])


def create_energy_analytics(simulation_data):
    # Simulated energy flow data for demonstration
    time_steps = list(range(1, 25))  # 24 hours
    building_demand = [2.5, 2.0, 1.8, 1.5, 1.3, 1.5, 2.0, 3.5, 4.0, 3.8, 3.5, 3.2, 3.0, 2.8, 3.0, 3.5, 4.2, 5.0, 4.5, 4.0, 3.5, 3.0, 2.8, 2.5]
    pv_generation = [0, 0, 0, 0, 0, 0.5, 1.5, 3.0, 5.0, 6.5, 7.0, 7.5, 7.8, 7.5, 7.0, 6.0, 4.5, 2.0, 0.5, 0, 0, 0, 0, 0]
    p2p_trading = [max(0, gen - dem) * 0.7 for gen, dem in zip(pv_generation, building_demand)]
    
    # Energy flow chart
    energy_fig = go.Figure()
    energy_fig.add_trace(go.Scatter(x=time_steps, y=building_demand, name='Demand', line=dict(color='red')))
    energy_fig.add_trace(go.Scatter(x=time_steps, y=pv_generation, name='PV Generation', line=dict(color='orange')))
    energy_fig.add_trace(go.Scatter(x=time_steps, y=p2p_trading, name='P2P Trading', line=dict(color='green'), fill='tonexty'))
    
    energy_fig.update_layout(
        title="⚡ Daily Energy Flow Profile",
        xaxis_title="Hour of Day",
        yaxis_title="Energy (kWh)",
        height=400
    )
    
    # Energy balance pie chart
    total_demand = sum(building_demand)
    total_pv = sum(pv_generation)
    total_p2p = sum(p2p_trading)
    grid_import = max(0, total_demand - total_pv)
    
    balance_fig = px.pie(
        values=[total_pv, grid_import, total_p2p],
        names=['PV Generation', 'Grid Import', 'P2P Trading'],
        title="📊 Energy Source Breakdown",
        color_discrete_map={'PV Generation': '#ffa500', 'Grid Import': '#dc3545', 'P2P Trading': '#28a745'}
    )
    balance_fig.update_layout(height=350)
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=energy_fig)
        ], width=8),
        dbc.Col([
            dcc.Graph(figure=balance_fig)
        ], width=4),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("⚡ Energy Metrics"),
                dbc.CardBody([
                    html.P([html.Strong("Self-Sufficiency: "), f"{(total_pv/total_demand)*100:.1f}%"], className="mb-2"),
                    html.P([html.Strong("P2P Contribution: "), f"{(total_p2p/total_demand)*100:.1f}%"], className="mb-2"),
                    html.P([html.Strong("Grid Dependency: "), f"{(grid_import/total_demand)*100:.1f}%"], className="mb-2"),
                    html.Hr(),
                    html.H6("Peak Hours:", className="text-primary"),
                    html.P("• Demand: 17:00-19:00", className="small mb-1"),
                    html.P("• Generation: 12:00-14:00", className="small mb-1"),
                    html.P("• P2P Trading: 10:00-16:00", className="small")
                ])
            ])
        ], width=12, className="mt-3")
    ])


def create_performance_analytics(simulation_data):
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    names = list(successful.keys())
    costs = [v['total_cost'] for v in successful.values()]
    fairness = [v['fairness'] for v in successful.values()]
    p2p_status = ['P2P Trading' if v.get('with_p2p', False) else 'Grid Only' for v in successful.values()]
    
    # Calculate performance scores
    min_cost, max_cost = min(costs), max(costs)
    min_fair, max_fair = min(fairness), max(fairness)
    
    scores = []
    for cost, fair in zip(costs, fairness):
        norm_cost = (cost - min_cost) / (max_cost - min_cost + 1e-6)
        norm_fair = (fair - min_fair) / (max_fair - min_fair + 1e-6)
        score = 1 - (0.7 * norm_cost + 0.3 * norm_fair)  # Higher is better
        scores.append(score)
    
    # Performance ranking chart
    df_performance = pd.DataFrame({
        'Scenario': [name[:20] + '...' if len(name) > 20 else name for name in names],
        'Score': scores,
        'Type': p2p_status,
        'Cost': costs,
        'Fairness': fairness
    }).sort_values('Score', ascending=False)
    
    rank_fig = px.bar(
        df_performance.head(10), x='Score', y='Scenario', color='Type',
        orientation='h',
        title="📈 Top 10 Performance Rankings",
        labels={'Score': 'Performance Score (0-1)', 'Scenario': ''},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    rank_fig.update_layout(height=500)
    
    # Performance matrix heatmap
    import plotly.graph_objects as go
    
    # Create performance matrix
    performance_matrix = []
    cost_bins = np.linspace(min(costs), max(costs), 5)
    fair_bins = np.linspace(min(fairness), max(fairness), 5)
    
    for i in range(4):
        row = []
        for j in range(4):
            # Count scenarios in this bin
            count = sum(1 for c, f in zip(costs, fairness) 
                       if cost_bins[i] <= c < cost_bins[i+1] and fair_bins[j] <= f < fair_bins[j+1])
            row.append(count)
        performance_matrix.append(row)
    
    heatmap_fig = go.Figure(data=go.Heatmap(
        z=performance_matrix,
        x=[f'Fair {i+1}' for i in range(4)],
        y=[f'Cost {i+1}' for i in range(4)],
        colorscale='RdYlGn',
        title="🎯 Performance Distribution Matrix"
    ))
    heatmap_fig.update_layout(height=350)
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=rank_fig)
        ], width=7),
        dbc.Col([
            dcc.Graph(figure=heatmap_fig)
        ], width=5),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("🏆 Performance Summary"),
                dbc.CardBody([
                    html.H6("Top Performer:", className="text-success"),
                    html.P(f"{df_performance.iloc[0]['Scenario']}", className="small mb-1"),
                    html.P(f"Score: {df_performance.iloc[0]['Score']:.3f}", className="mb-3"),
                    
                    html.H6("Performance Metrics:", className="text-primary"),
                    html.P([html.Strong("Cost Weight: "), "70%"], className="small mb-1"),
                    html.P([html.Strong("Fairness Weight: "), "30%"], className="small mb-1"),
                    html.P([html.Strong("Best Score: "), f"{max(scores):.3f}"], className="small mb-1"),
                    html.P([html.Strong("Average Score: "), f"{np.mean(scores):.3f}"], className="small")
                ])
            ])
        ], width=12, className="mt-3")
    ])


@app.callback(
    Output("results-table", "data"),
    [Input("simulation-data", "data")]
)
def update_results_table(simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return []
    
    scenario_results = simulation_data['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    if not successful:
        return []
    
    # Calculate scores and baseline for savings
    costs = [v['total_cost'] for v in successful.values()]
    fairness_vals = [v['fairness'] for v in successful.values()]
    
    min_cost, max_cost = min(costs), max(costs)
    min_fair, max_fair = min(fairness_vals), max(fairness_vals)
    
    # Use highest cost as baseline for savings calculation
    baseline_cost = max_cost
    
    table_data = []
    for name, result in successful.items():
        # Normalize and combine metrics (0-1 scale, lower is better)
        norm_cost = (result['total_cost'] - min_cost) / (max_cost - min_cost + 1e-6)
        norm_fair = (result['fairness'] - min_fair) / (max_fair - min_fair + 1e-6)
        score = 1 - (0.7 * norm_cost + 0.3 * norm_fair)  # Higher score is better
        
        # Calculate savings percentage compared to baseline
        savings = ((baseline_cost - result['total_cost']) / baseline_cost) * 100 if baseline_cost > 0 else 0
        
        # Create performance stars based on score
        stars = "★" * min(5, max(1, int(score * 5 + 0.5)))
        performance = f"{stars} ({score:.2f})"
        
        table_data.append({
            'scenario': name[:30] + "..." if len(name) > 30 else name,
            'cost': result['total_cost'],
            'fairness': result['fairness'],
            'p2p': '✅ Yes' if result.get('with_p2p', False) else '❌ No',
            'savings': savings,
            'performance': performance
        })
    
    # Sort by score (best first)
    table_data.sort(key=lambda x: x['performance'], reverse=True)
    
    # Add rank column
    for i, row in enumerate(table_data):
        row['rank'] = i + 1
    
    return table_data


@app.callback(
    Output("download-btn", "href"),
    [Input("simulation-data", "data")]
)
def update_download_link(simulation_data):
    if not simulation_data:
        return ""
    
    # Create download data
    import json
    from urllib.parse import quote
    
    # Convert to JSON string and create data URL
    json_str = json.dumps(simulation_data, indent=2, default=str)
    data_url = f"data:application/json;charset=utf-8,{quote(json_str)}"
    
    return data_url


if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8050)