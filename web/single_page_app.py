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

# Add custom CSS for tariff cards
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .tariff-card {
                transition: all 0.3s ease;
                border: 2px solid transparent;
                cursor: pointer;
            }
            .tariff-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                border-color: #007bff;
            }
            .tariff-card.selected {
                border-color: #28a745;
                background-color: #f8fff8;
                box-shadow: 0 5px 15px rgba(40, 167, 69, 0.3);
            }
            .tariff-card.selected .card-body {
                background-color: transparent;
            }
            .option-card {
                transition: all 0.3s ease;
                border: 2px solid transparent;
                cursor: pointer;
            }
            .option-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 6px 20px rgba(0,0,0,0.1);
                border-color: #007bff;
            }
            .option-card.selected {
                border-color: #28a745;
                background-color: #f8fff8 !important;
                box-shadow: 0 4px 12px rgba(40, 167, 69, 0.2);
            }
            .country-card {
                transition: all 0.3s ease;
                border: 2px solid transparent;
                cursor: pointer;
            }
            .country-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                border-color: #007bff;
            }
            .country-card.selected {
                border-color: #007bff;
                background-color: #f0f8ff !important;
                box-shadow: 0 3px 10px rgba(0, 123, 255, 0.2);
            }
            .analytics-tabs .nav-tabs {
                border: none;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                padding: 0.75rem;
                border-radius: 0.5rem;
                margin-bottom: 1.5rem;
            }
            .analytics-tabs .nav-link {
                border: none;
                border-radius: 0.375rem;
                margin: 0 0.25rem;
                padding: 0.75rem 1.25rem;
                transition: all 0.3s ease;
                background: transparent;
                position: relative;
                overflow: hidden;
            }
            .analytics-tabs .nav-link:hover {
                background: rgba(255, 255, 255, 0.7);
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            .analytics-tabs .nav-link.active {
                background: white;
                color: inherit !important;
            }
            
            /* Enhanced upload area styles */
            .upload-area:hover .border-2 {
                border-color: #0056b3 !important;
                background-color: #e6f3ff !important;
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0,123,255,0.15);
            }
            
            .upload-area:hover .fa-cloud-upload-alt {
                color: #0056b3 !important;
                transform: scale(1.1);
            }
            
            .upload-area:hover .text-primary {
                color: #0056b3 !important;
            }
            
            .upload-success {
                border-color: #28a745 !important;
                background-color: #f0f8f0 !important;
            }
            
            .upload-error {
                border-color: #dc3545 !important;
                background-color: #fff5f5 !important;
            }
            
            .file-item {
                transition: all 0.3s ease;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 8px;
                background: #f8f9fa;
                border-left: 4px solid #007bff;
            }
            
            .file-item:hover {
                background: #e9ecef;
                transform: translateX(4px);
            }
            
            .file-success {
                border-left-color: #28a745;
                background: #f0f8f0;
            }
            
            .file-error {
                border-left-color: #dc3545;
                background: #fff5f5;
            }
            
            .progress-bar {
                transition: width 0.3s ease;
                height: 4px;
                border-radius: 2px;
            }
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                transform: translateY(-2px);
            }
            .analytics-content {
                min-height: 400px;
                background: #fefefe;
                border-radius: 0.5rem;
                padding: 1.5rem;
                box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.05);
            }
        </style>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                // Ensure card clicks are properly handled
                window.dash_clientside = Object.assign({}, window.dash_clientside, {
                    clientside: {
                        handle_card_clicks: function() {
                            // This is handled by the Python callback
                            return window.dash_clientside.no_update;
                        }
                    }
                });
            });
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

orchestrator = SimulationOrchestrator()
simulation_results = {}
simulation_status = {"running": False, "progress": 0, "message": "Ready"}
uploaded_data = {"load_profiles": None, "pv_profiles": None, "status": "No files uploaded"}

def load_existing_results():
    """Load existing simulation results from output directory"""
    import os
    import json
    
    output_dir = "data/output"
    result_files = ["benchmark_results.json", "example_results.json"]
    
    for file_name in result_files:
        file_path = os.path.join(output_dir, file_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Transform data structure from nested format to expected format
                if 'benchmark' in data and 'scenario_results' in data['benchmark']:
                    return data['benchmark']  # Return the benchmark data directly
                elif 'scenario_results' in data:
                    return data  # Already in expected format
                    
            except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
                print(f"Error loading {file_name}: {e}")
                continue
    
    return {}

# Load existing results on startup
existing_results = load_existing_results()
if existing_results:
    simulation_results.update(existing_results)
    print(f"Loaded existing results with {len(existing_results.get('scenario_results', {})) if existing_results else 0} scenarios")

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
                    
                    # Enhanced Country Selection
                    dbc.Label([
                        html.I(className="fas fa-globe-europe me-2"),
                        "Country Selection"
                    ], className="fw-bold"),
                    html.Small("Approximate pricing for research purposes", className="text-muted d-block mb-2"),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🇮🇹", className="mb-1"),
                                    html.H6("Italy", className="mb-1 text-dark"),
                                    html.P("ARERA regulated", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="italy-country", color="light", outline=True, className="country-card w-100 p-2 selected")
                        ], width=4, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🇩🇪", className="mb-1"),
                                    html.H6("Germany", className="mb-1 text-dark"),
                                    html.P("EEG surcharge", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="germany-country", color="light", outline=True, className="country-card w-100 p-2")
                        ], width=4, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🇪🇸", className="mb-1"),
                                    html.H6("Spain", className="mb-1 text-dark"),
                                    html.P("PVPC structure", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="spain-country", color="light", outline=True, className="country-card w-100 p-2")
                        ], width=4, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🇸🇪", className="mb-1"),
                                    html.H6("Sweden", className="mb-1 text-dark"),
                                    html.P("Nord Pool", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="sweden-country", color="light", outline=True, className="country-card w-100 p-2")
                        ], width=4, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🇫🇷", className="mb-1"),
                                    html.H6("France", className="mb-1 text-dark"),
                                    html.P("Tarif Bleu", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="france-country", color="light", outline=True, className="country-card w-100 p-2")
                        ], width=4, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.H4("🔧", className="mb-1"),
                                    html.H6("Custom", className="mb-1 text-dark"),
                                    html.P("User-defined", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="custom-country", color="light", outline=True, className="country-card w-100 p-2")
                        ], width=4, className="mb-2")
                    ], className="mb-3"),
                    
                    # Hidden dropdown for compatibility
                    dcc.Dropdown([
                        {"label": "🇮🇹 Italy", "value": "italy"},
                        {"label": "🇩🇪 Germany", "value": "germany"},
                        {"label": "🇪🇸 Spain", "value": "spain"},
                        {"label": "🇸🇪 Sweden", "value": "sweden"},
                        {"label": "🇫🇷 France", "value": "france"},
                        {"label": "🔧 Custom", "value": "custom"}
                    ], value="italy", id="country-selector", style={"display": "none"}),
                    
                    # Enhanced Tariff Selection
                    dbc.Label([
                        html.I(className="fas fa-bolt me-2"),
                        "Tariff Type Selection"
                    ], className="fw-bold"),
                    html.Small("Choose the electricity pricing structure for your analysis", className="text-muted d-block mb-2"),
                    
                    # Tariff cards with visual selection
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.Button([
                                    html.Div([
                                        html.I(className="fas fa-clock text-primary fa-2x mb-2"),
                                        html.H6("Time-of-Use (ToU)", className="card-title text-dark"),
                                        html.P("Fixed pricing periods with predictable peak/off-peak rates", className="card-text small text-muted"),
                                        dbc.Badge("Stable", color="success", className="mb-2"),
                                        html.Ul([
                                            html.Li("Off-peak: Night & weekend", className="small text-muted"),
                                            html.Li("Peak: Weekday evenings", className="small text-muted"),
                                            html.Li("Best for: Load shifting", className="small text-primary")
                                        ], className="small mb-0 text-start")
                                    ], className="text-center")
                                ], id="tou-card", color="light", outline=True, className="tariff-card h-100 w-100 selected p-3")
                            ], width=6, className="mb-3"),
                            
                            dbc.Col([
                                dbc.Button([
                                    html.Div([
                                        html.I(className="fas fa-exclamation-triangle text-warning fa-2x mb-2"),
                                        html.H6("Critical Peak Pricing", className="card-title text-dark"),
                                        html.P("Extreme price spikes during critical system events", className="card-text small text-muted"),
                                        dbc.Badge("Event-based", color="warning", className="mb-2"),
                                        html.Ul([
                                            html.Li("Base: ToU structure", className="small text-muted"),
                                            html.Li("Events: Up to €0.50/kWh", className="small text-muted"),
                                            html.Li("Best for: Emergency response", className="small text-primary")
                                        ], className="small mb-0 text-start")
                                    ], className="text-center")
                                ], id="cpp-card", color="light", outline=True, className="tariff-card h-100 w-100 p-3")
                            ], width=6, className="mb-3"),
                            
                            dbc.Col([
                                dbc.Button([
                                    html.Div([
                                        html.I(className="fas fa-chart-line text-info fa-2x mb-2"),
                                        html.H6("Real-Time Pricing", className="card-title text-dark"),
                                        html.P("Variable hourly rates following market patterns", className="card-text small text-muted"),
                                        dbc.Badge("Dynamic", color="info", className="mb-2"),
                                        html.Ul([
                                            html.Li("Prices: Change hourly", className="small text-muted"),
                                            html.Li("Pattern: Market-driven", className="small text-muted"),
                                            html.Li("Best for: Flexible systems", className="small text-primary")
                                        ], className="small mb-0 text-start")
                                    ], className="text-center")
                                ], id="rtp-card", color="light", outline=True, className="tariff-card h-100 w-100 p-3")
                            ], width=6, className="mb-3"),
                            
                            dbc.Col([
                                dbc.Button([
                                    html.Div([
                                        html.I(className="fas fa-shield-alt text-danger fa-2x mb-2"),
                                        html.H6("Emergency Demand Response", className="card-title text-dark"),
                                        html.P("Extreme crisis pricing for grid emergency situations", className="card-text small text-muted"),
                                        dbc.Badge("Crisis", color="danger", className="mb-2"),
                                        html.Ul([
                                            html.Li("Base: ToU structure", className="small text-muted"),
                                            html.Li("Emergency: Up to €1.00/kWh", className="small text-muted"),
                                            html.Li("Best for: Stress testing", className="small text-primary")
                                        ], className="small mb-0 text-start")
                                    ], className="text-center")
                                ], id="edr-card", color="light", outline=True, className="tariff-card h-100 w-100 p-3")
                            ], width=6, className="mb-3")
                        ])
                    ], className="mb-3"),
                    
                    # Hidden dropdown for compatibility
                    dcc.Dropdown([
                        {"label": "Time-of-Use (ToU)", "value": "tou"},
                        {"label": "Critical Peak Pricing (CPP)", "value": "cpp"},
                        {"label": "Real-Time Pricing (RTP)", "value": "rtp"},
                        {"label": "Emergency Demand Response (EDR)", "value": "edr"}
                    ], value="tou", id="tariff-type", style={"display": "none"}),
                    
                    # Selected tariff display with detailed info
                    dbc.Card([
                        dbc.CardHeader([
                            html.I(className="fas fa-check-circle text-success me-2"),
                            html.Strong("Selected Tariff")
                        ]),
                        dbc.CardBody([
                            html.H6("Time-of-Use (ToU)", id="selected-tariff-display", className="mb-2"),
                            html.P("Fixed pricing periods with predictable peak/off-peak rates", id="selected-tariff-description", className="text-muted mb-3"),
                            html.Div(id="tariff-details", children=[
                                # Default ToU details
                                dbc.Row([
                                    dbc.Col([
                                        html.H6("📅 Time Periods", className="text-primary"),
                                        html.Ul([
                                            html.Li("Off-peak: 00:00-07:00, 23:00-24:00"),
                                            html.Li("Mid-peak: 07:00-17:00, 20:00-23:00"), 
                                            html.Li("On-peak: 17:00-20:00")
                                        ], className="small")
                                    ], width=6),
                                    dbc.Col([
                                        html.H6("💡 Use Cases", className="text-info"),
                                        html.Ul([
                                            html.Li("Residential prosumer communities"),
                                            html.Li("Battery storage optimization"),
                                            html.Li("Predictable load shifting")
                                        ], className="small")
                                    ], width=6)
                                ])
                            ])
                        ])
                    ], className="mb-3"),
                    
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
                    
                    # Enhanced Analysis Options
                    dbc.Label([
                        html.I(className="fas fa-cogs me-2"),
                        "Analysis Options"
                    ], className="fw-bold mb-2"),
                    html.Small("Select analysis features to include in your simulation", className="text-muted d-block mb-3"),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.I(className="fas fa-handshake text-success fa-2x mb-2"),
                                    html.H6("P2P Trading", className="mb-1 text-dark"),
                                    html.P("Community energy sharing", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="p2p-option", color="light", outline=True, className="option-card h-100 w-100 p-3 selected")
                        ], width=4),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.I(className="fas fa-brain text-info fa-2x mb-2"),
                                    html.H6("Surrogate Model", className="mb-1 text-dark"),
                                    html.P("ML-based rapid evaluation", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="surrogate-option", color="light", outline=True, className="option-card h-100 w-100 p-3")
                        ], width=4),
                        dbc.Col([
                            dbc.Button([
                                html.Div([
                                    html.I(className="fas fa-chart-bar text-warning fa-2x mb-2"),
                                    html.H6("Sensitivity Analysis", className="mb-1 text-dark"),
                                    html.P("Parameter sensitivity", className="small text-muted mb-0")
                                ], className="text-center")
                            ], id="sensitivity-option", color="light", outline=True, className="option-card h-100 w-100 p-3")
                        ], width=4)
                    ], className="mb-3"),
                    
                    # Hidden checklist for compatibility
                    dbc.Checklist([
                        {"label": "P2P Trading", "value": "p2p"},
                        {"label": "Surrogate Model", "value": "surrogate"},
                        {"label": "Sensitivity Analysis", "value": "sensitivity"}
                    ], value=["p2p"], id="options", style={"display": "none"}),
                    
                    # Enhanced File upload section
                    html.Hr(),
                    dbc.Label([
                        html.I(className="fas fa-cloud-upload-alt me-2"),
                        "Data Upload"
                    ], className="fw-bold"),
                    dbc.Badge("Optional", color="secondary", className="ms-2 mb-2"),
                    html.Small("Upload custom load profiles or PV generation data to enhance simulation accuracy", className="text-muted d-block mb-3"),
                    
                    # Enhanced drag-and-drop upload area
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-cloud-upload-alt fa-3x text-primary mb-3"),
                                        html.H5("Drag & Drop Files Here", className="text-primary mb-2"),
                                        html.P("or click to browse files", className="text-muted mb-3"),
                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Badge("📊 CSV", color="info", className="me-1")
                                            ], width="auto"),
                                            dbc.Col([
                                                dbc.Badge("📈 Excel", color="success", className="me-1")
                                            ], width="auto"),
                                            dbc.Col([
                                                dbc.Badge("📄 JSON", color="warning", className="me-1")
                                            ], width="auto")
                                        ], justify="center", className="mb-3"),
                                        html.Small("Max file size: 50MB | Supported formats: .csv, .xlsx, .json", className="text-muted")
                                    ], className="text-center py-3")
                                ])
                            ], className="border-2 border-primary", style={"borderStyle": "dashed", "backgroundColor": "#f8f9ff"})
                        ]),
                        style={
                            'borderRadius': '8px',
                            'cursor': 'pointer',
                            'transition': 'all 0.3s ease'
                        },
                        accept='.csv,.xlsx,.xls,.json',
                        className="upload-area mb-3"
                    ),
                    
                    # Enhanced format help section
                    dbc.Row([
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-info-circle me-2"),
                                "Format Guide"
                            ], id="help-toggle", color="info", size="sm", outline=True, className="w-100")
                        ], width=6),
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-download me-2"),
                                "Sample Files"
                            ], color="outline-secondary", size="sm", className="w-100", disabled=True)
                        ], width=6)
                    ], className="mb-3"),
                    
                    dbc.Collapse([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6([
                                    html.I(className="fas fa-file-alt me-2 text-info"),
                                    "File Format Requirements"
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.H6("📊 Data Structure", className="text-primary mb-2"),
                                            html.Ul([
                                                html.Li("Rows = Time steps (hourly/15-min intervals)"),
                                                html.Li("Columns = Buildings (Building_1, Building_2, etc.)"),
                                                html.Li("First row should contain column headers"),
                                                html.Li("Data values should be numeric (kWh)")
                                            ], className="small")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.H6("🏷️ File Naming", className="text-success mb-2"),
                                            html.Ul([
                                                html.Li([html.Strong("Load data:"), " Include 'load', 'demand', or 'consumption'"]),
                                                html.Li([html.Strong("PV data:"), " Include 'pv', 'solar', or 'generation'"]),
                                                html.Li([html.Strong("Examples:"), " load_profiles.csv, pv_generation.xlsx"])
                                            ], className="small")
                                        ])
                                    ], width=6)
                                ]),
                                dbc.Alert([
                                    html.I(className="fas fa-magic me-2"),
                                    "Data will be automatically resized and validated to match your simulation settings."
                                ], color="info", className="small mt-3 mb-0")
                            ])
                        ], className="border-0 bg-light")
                    ], id="upload-help", is_open=False),
                    
                    # Enhanced upload status area
                    html.Div(id='upload-status', className="mb-3"),
                    
                    # Enhanced Control buttons
                    dbc.Row([
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-play me-2"),
                                "Start Simulation"
                            ], id="start-btn", color="success", size="lg", className="w-100 shadow-sm")
                        ], width=8),
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-stop me-2"),
                                "Stop"
                            ], id="stop-btn", color="danger", size="lg", disabled=True, className="w-100 shadow-sm")
                        ], width=4)
                    ], className="mb-3"),
                    
                    # Status
                    html.Div(id="status-display"),
                    dbc.Progress(id="progress-bar", value=0, className="mb-2"),
                    
                    # Enhanced Quick actions
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-download me-2"),
                                "Download Results"
                            ], id="download-btn", color="success", className="w-100 shadow-sm", disabled=True)
                        ], width=6, className="mb-2"),
                        dbc.Col([
                            dbc.Button([
                                html.I(className="fas fa-redo me-2"),
                                "Reset"
                            ], id="reset-btn", color="outline-secondary", className="w-100 shadow-sm")
                        ], width=6, className="mb-2")
                    ], className="mb-3"),
                    
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
                    
                    dbc.Button([
                        html.I(className="fas fa-database me-2"),
                        "Data Sources"
                    ], id="sources-toggle", color="info", size="sm", outline=True)
                ])
            ])
        ], width=4),
        
        # Right column - Results and Analysis
        dbc.Col([
            # Enhanced Results summary cards
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-list-ol text-primary fa-2x mb-2"),
                                html.H3("0", id="total-scenarios", className="text-primary mb-1"),
                                html.P("Scenarios", className="text-muted small mb-0"),
                                html.P("Total evaluated", className="text-muted small mb-0")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm border-0 h-100")
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-euro-sign text-success fa-2x mb-2"),
                                html.H3("€0.00", id="avg-cost", className="text-success mb-1"),
                                html.P("Avg Cost", className="text-muted small mb-0"),
                                html.P("Per building", className="text-muted small mb-0")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm border-0 h-100")
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-balance-scale text-warning fa-2x mb-2"),
                                html.H3("0.000", id="avg-fairness", className="text-warning mb-1"),
                                html.P("Fairness", className="text-muted small mb-0"),
                                html.P("Lower is better", className="text-muted small mb-0")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm border-0 h-100")
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-chart-line text-info fa-2x mb-2"),
                                html.H3("0%", id="p2p-savings", className="text-info mb-1"),
                                html.P("P2P Savings", className="text-muted small mb-0"),
                                html.P("vs Grid Only", className="text-muted small mb-0")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm border-0 h-100")
                ], width=3)
            ], className="mb-4"),
            
            # Enhanced Advanced Analytics Dashboard
            dbc.Card([
                dbc.CardHeader([
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.H4([
                                    html.I(className="fas fa-chart-line me-3 text-primary"),
                                    "Advanced Analytics Dashboard"
                                ], className="mb-2"),
                                html.P([
                                    html.I(className="fas fa-info-circle me-2 text-muted"),
                                    "Comprehensive analysis of simulation results with interactive visualizations"
                                ], className="text-muted mb-2 small"),
                                dbc.Badge(id="selected-tariffs-info", color="light", className="px-3 py-1")
                            ])
                        ], width=8),
                        dbc.Col([
                            html.Div([
                                dbc.Button([
                                    html.I(className="fas fa-compass me-2"),
                                    "Guide"
                                ], id="dashboard-guide-toggle", color="primary", size="sm", outline=True, className="mb-2"),
                                html.Div([
                                    html.I(className="fas fa-circle text-success me-1"),
                                    html.Small("Ready for analysis", className="text-muted")
                                ], className="d-flex align-items-center")
                            ], className="text-end")
                        ], width=4)
                    ])
                ], className="bg-light border-0"),
                dbc.CardBody([
                    # Enhanced Dashboard Guide
                    dbc.Collapse([
                        dbc.Card([
                            dbc.CardBody([
                                html.Div([
                                    html.H5([
                                        html.I(className="fas fa-graduation-cap me-2 text-primary"),
                                        "Dashboard Guide"
                                    ], className="mb-4 text-center"),
                                    
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-chart-pie fa-2x text-primary mb-2"),
                                                        html.H6("Overview", className="text-primary"),
                                                        html.P("High-level view of all scenarios with key trade-offs and summary statistics.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-primary border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3"),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-euro-sign fa-2x text-success mb-2"),
                                                        html.H6("Cost Analysis", className="text-success"),
                                                        html.P("Deep dive into cost patterns, P2P savings, and economic performance.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-success border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3"),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-balance-scale fa-2x text-warning mb-2"),
                                                        html.H6("Fairness", className="text-warning"),
                                                        html.P("Understand cost distribution equality across buildings in each scenario.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-warning border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3")
                                    ]),
                                    
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-handshake fa-2x text-info mb-2"),
                                                        html.H6("P2P Trading", className="text-info"),
                                                        html.P("Analyze impact and benefits of peer-to-peer energy trading.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-info border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3"),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-bolt fa-2x text-danger mb-2"),
                                                        html.H6("Energy Flow", className="text-danger"),
                                                        html.P("Visualize energy generation, consumption, and sharing patterns.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-danger border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3"),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.Div([
                                                        html.I(className="fas fa-trophy fa-2x text-secondary mb-2"),
                                                        html.H6("Performance", className="text-secondary"),
                                                        html.P("Compare overall scenario performance using combined metrics.", className="small text-muted")
                                                    ], className="text-center")
                                                ])
                                            ], className="h-100 border-secondary border-2", style={"borderStyle": "dashed"})
                                        ], width=4, className="mb-3")
                                    ])
                                ])
                            ])
                        ], className="border-0 shadow-sm bg-light")
                    ], id="dashboard-guide", is_open=False),
                    
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(label="📊 Overview", tab_id="overview-tab", 
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#007bff", "fontWeight": "bold"}),
                            dbc.Tab(label="💰 Cost Analysis", tab_id="cost-tab",
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#28a745", "fontWeight": "bold"}),
                            dbc.Tab(label="⚖️ Fairness", tab_id="fairness-tab",
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#ffc107", "fontWeight": "bold"}),
                            dbc.Tab(label="🔄 P2P Trading", tab_id="p2p-tab",
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#17a2b8", "fontWeight": "bold"}),
                            dbc.Tab(label="⚡ Energy Flow", tab_id="energy-tab",
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#dc3545", "fontWeight": "bold"}),
                            dbc.Tab(label="🏆 Performance", tab_id="performance-tab",
                                   label_style={"color": "#495057", "fontWeight": "500"}, 
                                   active_label_style={"color": "#6f42c1", "fontWeight": "bold"})
                        ], id="analytics-tabs", active_tab="overview-tab", className="analytics-tabs"),
                    ], className="mb-3"),
                    
                    html.Div(id="analytics-content", className="analytics-content")
                ])
            ], className="shadow-sm mb-4"),
            
            # Results table with better explanations
            dbc.Card([
                dbc.CardHeader([
                    dbc.Row([
                        dbc.Col([
                            html.H5("📊 Scenario Results", className="mb-0"),
                            html.Small("Ranked by overall performance (lower cost + better fairness)", className="text-muted")
                        ], width=8),
                        dbc.Col([
                            dbc.ButtonGroup([
                                dbc.Button([
                                    html.I(className="fas fa-refresh me-2"), 
                                    "Refresh"
                                ], id="refresh-results-btn", color="success", size="sm", outline=True),
                                dbc.Button([
                                    html.I(className="fas fa-info-circle me-2"), 
                                    "Help"
                                ], id="results-help-toggle", color="info", size="sm", outline=True)
                            ])
                        ], width=4, className="text-end")
                    ])
                ]),
                dbc.CardBody([
                    # Enhanced Help collapse
                    dbc.Collapse([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6([
                                    html.I(className="fas fa-question-circle me-2 text-info"),
                                    "Understanding the Results"
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.H6("📊 Key Metrics", className="text-primary mb-2"),
                                            html.Ul([
                                                html.Li([html.Strong("Rank:"), " Best scenarios ranked #1, #2, #3..."]),
                                                html.Li([html.Strong("Total Cost:"), " Average electricity cost per building (€)"]),
                                                html.Li([html.Strong("Fairness:"), " Cost equality across buildings (lower = more fair)"])
                                            ], className="small")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.H6("🎯 Performance", className="text-success mb-2"),
                                            html.Ul([
                                                html.Li([html.Strong("P2P Trading:"), " Energy sharing enabled/disabled"]),
                                                html.Li([html.Strong("Savings:"), " Cost reduction vs baseline"]),
                                                html.Li([html.Strong("Performance:"), " Combined score (★★★★★)"])
                                            ], className="small")
                                        ])
                                    ], width=6)
                                ]),
                                dbc.Alert([
                                    html.I(className="fas fa-lightbulb me-2"),
                                    "Green rows indicate P2P trading scenarios with community energy sharing benefits."
                                ], color="success", className="small mt-3 mb-0")
                            ])
                        ], className="border-0 bg-light")
                    ], id="results-help", is_open=False),
                    
                    # Results filter section
                    dbc.Row([
                        dbc.Col([
                            html.Label("Filter Results:", className="small fw-bold mb-2"),
                            dcc.Dropdown(
                                id="results-filter",
                                options=[
                                    {"label": "📊 All Scenarios (Both P2P & Non-P2P)", "value": "all"},
                                    {"label": "✅ P2P Trading Only", "value": "p2p_only"},
                                    {"label": "❌ No P2P Trading", "value": "no_p2p"},
                                    {"label": "🔄 P2P vs Non-P2P Comparison", "value": "comparison"}
                                ],
                                value="all",
                                clearable=False,
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            html.Div([
                                html.Small("Showing scenarios from your 15 base configurations", className="text-muted"),
                                html.Br(),
                                html.Small("Each tested with and without P2P trading", className="text-muted")
                            ], className="mt-4")
                        ], width=6)
                    ], className="mb-3"),
                    
                    # Results content with conditional rendering
                    html.Div(id="results-table-container", children=[
                        dash_table.DataTable(
                            id="results-table",
                            columns=[
                                {"name": "🏆 Rank", "id": "rank", "type": "numeric"},
                                {"name": "📋 Scenario", "id": "scenario"},
                                {"name": "💰 Total Cost (€)", "id": "cost", "type": "numeric", "format": {"specifier": ".2f"}},
                                {"name": "⚖️ Fairness", "id": "fairness", "type": "numeric", "format": {"specifier": ".3f"}},
                                {"name": "🔄 P2P Trading", "id": "p2p"},
                                {"name": "📈 Savings (%)", "id": "savings", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "⭐ Performance", "id": "performance"}
                            ],
                            data=[],
                            sort_action="native",
                            filter_action="native",
                            style_cell={
                                'textAlign': 'left', 
                                'fontSize': '14px',
                                'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'fontFamily': 'system-ui, -apple-system, sans-serif'
                            },
                            style_header={
                                'backgroundColor': '#f8f9fa',
                                'fontWeight': 'bold',
                                'fontSize': '14px',
                                'color': '#495057',
                                'border': '1px solid #dee2e6',
                                'textAlign': 'center'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'backgroundColor': '#ffffff'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{p2p} = ✅ Yes'},
                                    'backgroundColor': '#e8f5e8',
                                    'border': '1px solid #28a745'
                                },
                                {
                                    'if': {'column_id': 'rank', 'filter_query': '{rank} = 1'},
                                    'backgroundColor': '#ffd700',
                                    'fontWeight': 'bold',
                                    'color': '#8B4513'
                                },
                                {
                                    'if': {'column_id': 'rank', 'filter_query': '{rank} = 2'},
                                    'backgroundColor': '#C0C0C0',
                                    'fontWeight': 'bold',
                                    'color': '#444444'
                                },
                                {
                                    'if': {'column_id': 'rank', 'filter_query': '{rank} = 3'},
                                    'backgroundColor': '#CD7F32',
                                    'fontWeight': 'bold',
                                    'color': '#ffffff'
                                }
                            ],
                            style_cell_conditional=[
                                {'if': {'column_id': 'rank'}, 'width': '80px', 'textAlign': 'center'},
                                {'if': {'column_id': 'scenario'}, 'width': '220px', 'textAlign': 'left'},
                                {'if': {'column_id': 'cost'}, 'width': '140px', 'textAlign': 'right'},
                                {'if': {'column_id': 'fairness'}, 'width': '120px', 'textAlign': 'right'},
                                {'if': {'column_id': 'p2p'}, 'width': '120px', 'textAlign': 'center'},
                                {'if': {'column_id': 'savings'}, 'width': '120px', 'textAlign': 'right'},
                                {'if': {'column_id': 'performance'}, 'width': '150px', 'textAlign': 'center'}
                            ],
                            page_size=15,
                            style_table={
                                'overflowX': 'auto',
                                'border': '1px solid #dee2e6',
                                'borderRadius': '0.375rem',
                                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
                            }
                        )
                    ])
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


# Tariff card selection callbacks
@app.callback(
    [Output("tariff-type", "value"),
     Output("selected-tariff-display", "children"),
     Output("selected-tariff-description", "children"),
     Output("tariff-details", "children"),
     Output("tou-card", "className"),
     Output("cpp-card", "className"),
     Output("rtp-card", "className"),
     Output("edr-card", "className")],
    [Input("tou-card", "n_clicks"),
     Input("cpp-card", "n_clicks"),
     Input("rtp-card", "n_clicks"),
     Input("edr-card", "n_clicks")],
    prevent_initial_call=True
)
def update_tariff_selection(tou_clicks, cpp_clicks, rtp_clicks, edr_clicks):
    def create_tariff_details(tariff_type):
        if tariff_type == "tou":
            return dbc.Row([
                dbc.Col([
                    html.H6("📅 Time Periods", className="text-primary"),
                    html.Ul([
                        html.Li("Off-peak: 00:00-07:00, 23:00-24:00"),
                        html.Li("Mid-peak: 07:00-17:00, 20:00-23:00"), 
                        html.Li("On-peak: 17:00-20:00")
                    ], className="small")
                ], width=6),
                dbc.Col([
                    html.H6("💡 Use Cases", className="text-info"),
                    html.Ul([
                        html.Li("Residential prosumer communities"),
                        html.Li("Battery storage optimization"),
                        html.Li("Predictable load shifting")
                    ], className="small")
                ], width=6)
            ])
        elif tariff_type == "cpp":
            return dbc.Row([
                dbc.Col([
                    html.H6("⚠️ Event Structure", className="text-warning"),
                    html.Ul([
                        html.Li("Base: ToU pricing structure"),
                        html.Li("Critical events: Tue-Thu, 5-8 PM"),
                        html.Li("Critical price: Up to €0.50/kWh")
                    ], className="small")
                ], width=6),
                dbc.Col([
                    html.H6("🎯 Applications", className="text-info"),
                    html.Ul([
                        html.Li("Emergency demand response"),
                        html.Li("Grid stability testing"),
                        html.Li("High-flexibility systems")
                    ], className="small")
                ], width=6)
            ])
        elif tariff_type == "rtp":
            return dbc.Row([
                dbc.Col([
                    html.H6("📈 Price Dynamics", className="text-info"),
                    html.Ul([
                        html.Li("Hourly price updates"),
                        html.Li("Market-driven volatility"),
                        html.Li("Daily pattern variations")
                    ], className="small")
                ], width=6),
                dbc.Col([
                    html.H6("⚡ Best For", className="text-success"),
                    html.Ul([
                        html.Li("Smart home automation"),
                        html.Li("Flexible industrial loads"),
                        html.Li("Advanced energy management")
                    ], className="small")
                ], width=6)
            ])
        elif tariff_type == "edr":
            return dbc.Row([
                dbc.Col([
                    html.H6("🚨 Emergency Events", className="text-danger"),
                    html.Ul([
                        html.Li("Base: ToU structure"),
                        html.Li("Emergency: €1.00/kWh"),
                        html.Li("Probability: 5% per day")
                    ], className="small")
                ], width=6),
                dbc.Col([
                    html.H6("🔬 Research Value", className="text-primary"),
                    html.Ul([
                        html.Li("Extreme scenario testing"),
                        html.Li("System resilience analysis"),
                        html.Li("Crisis response modeling")
                    ], className="small")
                ], width=6)
            ])
    
    # Check which card was clicked
    ctx = callback_context
    selected_tariff = "tou"  # Default
    
    if ctx.triggered:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        print(f"DEBUG: Card clicked - {trigger_id}")
        
        if trigger_id == "tou-card" and tou_clicks:
            selected_tariff = "tou"
        elif trigger_id == "cpp-card" and cpp_clicks:
            selected_tariff = "cpp"
        elif trigger_id == "rtp-card" and rtp_clicks:
            selected_tariff = "rtp"
        elif trigger_id == "edr-card" and edr_clicks:
            selected_tariff = "edr"
    
    # Define tariff information
    tariff_info = {
        "tou": ("Time-of-Use (ToU)", "Fixed pricing periods with predictable peak/off-peak rates"),
        "cpp": ("Critical Peak Pricing (CPP)", "Extreme price spikes during critical system events"),
        "rtp": ("Real-Time Pricing (RTP)", "Variable hourly rates following market patterns"),
        "edr": ("Emergency Demand Response (EDR)", "Extreme crisis pricing for grid emergency situations")
    }
    
    display_name, description = tariff_info[selected_tariff]
    details = create_tariff_details(selected_tariff)
    
    # Set button classes
    tou_class = "tariff-card h-100 w-100 selected p-3" if selected_tariff == "tou" else "tariff-card h-100 w-100 p-3"
    cpp_class = "tariff-card h-100 w-100 selected p-3" if selected_tariff == "cpp" else "tariff-card h-100 w-100 p-3"
    rtp_class = "tariff-card h-100 w-100 selected p-3" if selected_tariff == "rtp" else "tariff-card h-100 w-100 p-3"
    edr_class = "tariff-card h-100 w-100 selected p-3" if selected_tariff == "edr" else "tariff-card h-100 w-100 p-3"
    
    return selected_tariff, display_name, description, details, tou_class, cpp_class, rtp_class, edr_class


# Analysis options selection callback
@app.callback(
    [Output("options", "value"),
     Output("p2p-option", "className"),
     Output("surrogate-option", "className"),
     Output("sensitivity-option", "className")],
    [Input("p2p-option", "n_clicks"),
     Input("surrogate-option", "n_clicks"),
     Input("sensitivity-option", "n_clicks")],
    [State("options", "value")],
    prevent_initial_call=True
)
def update_analysis_options(p2p_clicks, surrogate_clicks, sensitivity_clicks, current_options):
    ctx = callback_context
    if not ctx.triggered:
        # Default state
        selected_options = ["p2p"]
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        selected_options = current_options.copy() if current_options else []
        
        if trigger_id == "p2p-option":
            if "p2p" in selected_options:
                selected_options.remove("p2p")
            else:
                selected_options.append("p2p")
        elif trigger_id == "surrogate-option":
            if "surrogate" in selected_options:
                selected_options.remove("surrogate")
            else:
                selected_options.append("surrogate")
        elif trigger_id == "sensitivity-option":
            if "sensitivity" in selected_options:
                selected_options.remove("sensitivity")
            else:
                selected_options.append("sensitivity")
    
    # Set button classes based on selection
    p2p_class = "option-card h-100 w-100 p-3 selected" if "p2p" in selected_options else "option-card h-100 w-100 p-3"
    surrogate_class = "option-card h-100 w-100 p-3 selected" if "surrogate" in selected_options else "option-card h-100 w-100 p-3"
    sensitivity_class = "option-card h-100 w-100 p-3 selected" if "sensitivity" in selected_options else "option-card h-100 w-100 p-3"
    
    return selected_options, p2p_class, surrogate_class, sensitivity_class


# Country selection callback
@app.callback(
    [Output("country-selector", "value"),
     Output("italy-country", "className"),
     Output("germany-country", "className"),
     Output("spain-country", "className"),
     Output("sweden-country", "className"),
     Output("france-country", "className"),
     Output("custom-country", "className")],
    [Input("italy-country", "n_clicks"),
     Input("germany-country", "n_clicks"),
     Input("spain-country", "n_clicks"),
     Input("sweden-country", "n_clicks"),
     Input("france-country", "n_clicks"),
     Input("custom-country", "n_clicks")],
    prevent_initial_call=True
)
def update_country_selection(italy_clicks, germany_clicks, spain_clicks, sweden_clicks, france_clicks, custom_clicks):
    ctx = callback_context
    selected_country = "italy"  # Default
    
    if ctx.triggered:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        country_map = {
            "italy-country": "italy",
            "germany-country": "germany", 
            "spain-country": "spain",
            "sweden-country": "sweden",
            "france-country": "france",
            "custom-country": "custom"
        }
        
        selected_country = country_map.get(trigger_id, "italy")
    
    # Set button classes
    italy_class = "country-card w-100 p-2 selected" if selected_country == "italy" else "country-card w-100 p-2"
    germany_class = "country-card w-100 p-2 selected" if selected_country == "germany" else "country-card w-100 p-2"
    spain_class = "country-card w-100 p-2 selected" if selected_country == "spain" else "country-card w-100 p-2"
    sweden_class = "country-card w-100 p-2 selected" if selected_country == "sweden" else "country-card w-100 p-2"
    france_class = "country-card w-100 p-2 selected" if selected_country == "france" else "country-card w-100 p-2"
    custom_class = "country-card w-100 p-2 selected" if selected_country == "custom" else "country-card w-100 p-2"
    
    return selected_country, italy_class, germany_class, spain_class, sweden_class, france_class, custom_class


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
    Output("dashboard-guide", "is_open"),
    [Input("dashboard-guide-toggle", "n_clicks")],
    [State("dashboard-guide", "is_open")]
)
def toggle_dashboard_guide(n_clicks, is_open):
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
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-cloud-upload-alt text-muted", style={"fontSize": "24px"}),
                        html.P("Ready to upload files", className="text-muted mb-0 mt-2")
                    ], className="text-center py-2")
                ])
            ], className="border-light bg-light")
        ])
    
    global uploaded_data
    
    df, message = parse_uploaded_file(contents, filename)
    
    if df is not None:
        # Create enhanced success feedback with file preview
        file_size = len(contents) if contents else 0
        file_size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
        
        # Data statistics
        data_stats = {
            'rows': df.shape[0],
            'columns': df.shape[1],
            'total_values': df.shape[0] * df.shape[1],
            'missing_values': df.isnull().sum().sum() if hasattr(df, 'isnull') else 0,
            'numeric_columns': len([col for col in df.columns if df[col].dtype in ['int64', 'float64']]) if hasattr(df, 'columns') else df.shape[1]
        }
        
        # Determine file type and create appropriate feedback
        if 'load' in filename.lower() or 'demand' in filename.lower():
            success, filepath = save_uploaded_data_to_framework(df, "load_profiles")
            if success:
                uploaded_data["load_profiles"] = df
                uploaded_data["status"] = f"Load profiles: {message}"
                file_type = "Load Profiles"
                file_icon = "fas fa-chart-line"
                file_color = "success"
        
        elif 'pv' in filename.lower() or 'solar' in filename.lower() or 'generation' in filename.lower():
            success, filepath = save_uploaded_data_to_framework(df, "pv_profiles")
            if success:
                uploaded_data["pv_profiles"] = df
                uploaded_data["status"] = f"PV profiles: {message}"
                file_type = "PV Generation"
                file_icon = "fas fa-solar-panel"
                file_color = "success"
        
        else:
            # Default to load profiles if unclear
            success, filepath = save_uploaded_data_to_framework(df, "load_profiles")
            if success:
                uploaded_data["load_profiles"] = df
                uploaded_data["status"] = f"Data (assumed load profiles): {message}"
                file_type = "Load Profiles (Auto-detected)"
                file_icon = "fas fa-info-circle"
                file_color = "info"
        
        # Create enhanced success card with file preview
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    # Header with file info
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.I(className=f"{file_icon} me-2", style={"fontSize": "20px"}),
                                html.Strong(filename),
                                dbc.Badge(file_type, color=file_color, className="ms-2")
                            ])
                        ], width=8),
                        dbc.Col([
                            html.Small(file_size_str, className="text-muted")
                        ], width=4, className="text-end")
                    ], className="mb-3"),
                    
                    # Success progress bar
                    dbc.Progress(value=100, color=file_color, className="mb-3", style={"height": "6px"}),
                    
                    # Data preview stats
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.I(className="fas fa-table me-2 text-primary"),
                                html.Strong(f"{data_stats['rows']:,}"),
                                html.Small(" time steps", className="text-muted")
                            ], className="file-item file-success")
                        ], width=6),
                        dbc.Col([
                            html.Div([
                                html.I(className="fas fa-building me-2 text-primary"),
                                html.Strong(f"{data_stats['columns']:,}"),
                                html.Small(" buildings", className="text-muted")
                            ], className="file-item file-success")
                        ], width=6)
                    ], className="mb-2"),
                    
                    # Additional stats
                    dbc.Row([
                        dbc.Col([
                            html.Small([
                                html.I(className="fas fa-check-circle text-success me-1"),
                                f"{data_stats['numeric_columns']} numeric columns"
                            ], className="text-muted")
                        ], width=6),
                        dbc.Col([
                            html.Small([
                                html.I(className="fas fa-database text-info me-1"),
                                f"{data_stats['total_values']:,} data points"
                            ], className="text-muted")
                        ], width=6)
                    ])
                ])
            ], className="border-success bg-light", style={"borderLeft": "4px solid #28a745"})
        ])
    
    # Enhanced error feedback
    return html.Div([
        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-exclamation-triangle me-2", style={"fontSize": "20px"}),
                            html.Strong(filename if filename else "Upload Error"),
                            dbc.Badge("Failed", color="danger", className="ms-2")
                        ])
                    ], width=12)
                ], className="mb-3"),
                
                # Error progress bar
                dbc.Progress(value=100, color="danger", className="mb-3", style={"height": "6px"}),
                
                # Error message
                html.Div([
                    html.I(className="fas fa-times-circle text-danger me-2"),
                    html.Span(message, className="text-danger"),
                ], className="file-item file-error"),
                
                # Help text
                html.Small([
                    html.I(className="fas fa-lightbulb me-1"),
                    "Ensure your file is in CSV, Excel, or JSON format with numeric data"
                ], className="text-muted mt-2")
            ])
        ], className="border-danger bg-light", style={"borderLeft": "4px solid #dc3545"})
    ])


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
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-chart-line fa-4x text-muted mb-3"),
                        html.H4("No Analytics Data Available", className="text-muted mb-3"),
                        html.P("Run a simulation to generate analytics and visualizations", className="text-muted mb-4"),
                        dbc.Button([
                            html.I(className="fas fa-play me-2"),
                            "Start Your First Simulation"
                        ], color="primary", size="lg", outline=True, className="mb-3"),
                        html.Hr(),
                        html.H6("What you'll see here:", className="text-muted mb-2"),
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.I(className="fas fa-chart-pie me-2 text-primary"),
                                    "Cost vs Fairness Analysis"
                                ], className="small text-muted mb-1")
                            ], width=6),
                            dbc.Col([
                                html.Div([
                                    html.I(className="fas fa-handshake me-2 text-success"),
                                    "P2P Trading Benefits"
                                ], className="small text-muted mb-1")
                            ], width=6),
                            dbc.Col([
                                html.Div([
                                    html.I(className="fas fa-bolt me-2 text-warning"),
                                    "Energy Flow Patterns"
                                ], className="small text-muted mb-1")
                            ], width=6),
                            dbc.Col([
                                html.Div([
                                    html.I(className="fas fa-trophy me-2 text-info"),
                                    "Performance Rankings"
                                ], className="small text-muted mb-1")
                            ], width=6)
                        ])
                    ], className="text-center py-5")
                ])
            ], className="border-0 bg-light")
        ])
    
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
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-exclamation-triangle fa-3x text-warning mb-3"),
                        html.H4("No Successful Scenarios", className="text-warning mb-3"),
                        html.P("The simulation completed but no scenarios were successful.", className="text-muted mb-3"),
                        html.P("This might happen due to:", className="text-muted mb-2"),
                        html.Ul([
                            html.Li("Configuration issues with the optimization parameters", className="text-muted small"),
                            html.Li("Invalid price ranges or tariff settings", className="text-muted small"),
                            html.Li("Insufficient time horizon or building count", className="text-muted small")
                        ], className="text-start mb-4"),
                        dbc.Button([
                            html.I(className="fas fa-redo me-2"),
                            "Try Different Settings"
                        ], color="warning", outline=True)
                    ], className="text-center py-4")
                ])
            ], className="border-warning")
        ])
    
    names = list(successful.keys())
    costs = [v['total_cost'] for v in successful.values()]
    fairness = [v['fairness'] for v in successful.values()]
    p2p_status = ['P2P Trading' if v.get('with_p2p', False) else 'Grid Only' for v in successful.values()]
    
    # Enhanced scatter plot with annotations and trend
    scatter_fig = px.scatter(
        x=costs, y=fairness, color=p2p_status, hover_name=names,
        title="🎯 Cost vs Fairness Trade-off Analysis",
        labels={'x': 'Total Cost (€/building)', 'y': 'Fairness (Coefficient of Variation)'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    
    # Add ideal zone annotation
    scatter_fig.add_shape(type="rect", x0=min(costs), y0=0, x1=np.percentile(costs, 25), y1=0.2,
                         fillcolor="lightgreen", opacity=0.1, line_width=0)
    scatter_fig.add_annotation(x=np.percentile(costs, 12.5), y=0.1, text="Ideal Zone<br>(Low Cost + High Fairness)",
                              showarrow=False, font=dict(size=10, color="green"))
    
    # Add average lines
    scatter_fig.add_hline(y=np.mean(fairness), line_dash="dash", annotation_text=f"Avg Fairness: {np.mean(fairness):.3f}")
    scatter_fig.add_vline(x=np.mean(costs), line_dash="dash", annotation_text=f"Avg Cost: €{np.mean(costs):.2f}")
    scatter_fig.update_layout(height=450)
    
    # Enhanced cost distribution with statistics
    cost_hist = px.histogram(
        x=costs, nbins=10, color=p2p_status,
        title="💰 Cost Distribution with Statistical Insights",
        labels={'x': 'Total Cost (€/building)', 'y': 'Number of Scenarios'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    
    # Add statistical lines
    cost_hist.add_vline(x=np.mean(costs), line_dash="dash", annotation_text="Mean")
    cost_hist.add_vline(x=np.median(costs), line_dash="dot", annotation_text="Median")
    cost_hist.update_layout(height=350)
    
    # Enhanced summary metrics
    avg_cost = np.mean(costs)
    avg_fairness = np.mean(fairness)
    best_scenario = min(successful.items(), key=lambda x: x[1]['total_cost'])
    most_fair = min(successful.items(), key=lambda x: x[1]['fairness'])
    cost_std = np.std(costs)
    fairness_std = np.std(fairness)
    
    # Pareto frontier analysis
    pareto_scenarios = []
    for name, result in successful.items():
        is_pareto = True
        for other_name, other_result in successful.items():
            if (other_result['total_cost'] < result['total_cost'] and 
                other_result['fairness'] <= result['fairness']):
                is_pareto = False
                break
        if is_pareto:
            pareto_scenarios.append(name)
    
    return dbc.Row([
        # Explanation Panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H6([html.I(className="fas fa-info-circle me-2"), "Overview Analysis Explained"], className="mb-0")
                ]),
                dbc.CardBody([
                    html.P([
                        html.Strong("Purpose: "), "This overview provides a comprehensive view of all simulation scenarios, "
                        "highlighting the fundamental trade-off between cost minimization and fairness maximization."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("Scatter Plot: "), "Each dot represents a scenario. The ideal zone (green) shows scenarios "
                        "with both low costs and high fairness. Green dots indicate P2P trading scenarios."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("Histogram: "), "Shows the distribution of costs across all scenarios. "
                        "Multiple peaks may indicate distinct solution clusters."
                    ], className="small mb-0")
                ])
            ])
        ], width=12, className="mb-3"),
        
        # Main scatter plot
        dbc.Col([
            dcc.Graph(figure=scatter_fig)
        ], width=8),
        
        # Enhanced insights panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("🎯 Key Insights"),
                dbc.CardBody([
                    html.H6("🏆 Best Performers:", className="text-success mb-2"),
                    html.P([html.Strong("Lowest Cost: "), f"{best_scenario[0][:25]}..."], className="small mb-1"),
                    html.P(f"€{best_scenario[1]['total_cost']:.2f}", className="h6 text-success mb-2"),
                    
                    html.P([html.Strong("Most Fair: "), f"{most_fair[0][:25]}..."], className="small mb-1"),
                    html.P(f"{most_fair[1]['fairness']:.3f} CoV", className="h6 text-info mb-3"),
                    
                    html.H6("📊 Statistics:", className="text-primary mb-2"),
                    html.P([html.Strong("Scenarios: "), f"{len(successful)}"], className="small mb-1"),
                    html.P([html.Strong("Avg Cost: "), f"€{avg_cost:.2f} ± {cost_std:.2f}"], className="small mb-1"),
                    html.P([html.Strong("Avg Fairness: "), f"{avg_fairness:.3f} ± {fairness_std:.3f}"], className="small mb-1"),
                    html.P([html.Strong("Pareto Optimal: "), f"{len(pareto_scenarios)}"], className="small mb-3"),
                    
                    html.H6("💡 Insights:", className="text-warning mb-2"),
                    html.P("P2P trading scenarios typically cluster in the lower-cost region, "
                           "demonstrating economic benefits of energy sharing.", className="small")
                ])
            ])
        ], width=4),
        
        # Enhanced histogram
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
    
    # Enhanced cost comparison with ranking
    sorted_data = sorted(zip(names, costs, p2p_status), key=lambda x: x[1])
    sorted_names = [x[0][:15] + "..." if len(x[0]) > 15 else x[0] for x in sorted_data]
    sorted_costs = [x[1] for x in sorted_data]
    sorted_p2p = [x[2] for x in sorted_data]
    
    bar_fig = px.bar(
        x=sorted_costs, y=sorted_names, color=sorted_p2p, orientation='h',
        title="💰 Cost Ranking - Best to Worst Performance",
        labels={'x': 'Total Cost (€/building)', 'y': 'Scenario'},
        color_discrete_map={'P2P Trading': '#28a745', 'Grid Only': '#dc3545'}
    )
    bar_fig.update_layout(height=max(400, len(sorted_names) * 20))
    
    # Enhanced box plot with violin overlay
    box_fig = go.Figure()
    
    p2p_costs = [cost for cost, p2p in zip(costs, p2p_status) if p2p == 'P2P Trading']
    grid_costs = [cost for cost, p2p in zip(costs, p2p_status) if p2p == 'Grid Only']
    
    if p2p_costs:
        box_fig.add_trace(go.Violin(y=p2p_costs, name='P2P Trading', fillcolor='rgba(40, 167, 69, 0.3)',
                                   line_color='#28a745', box_visible=True, meanline_visible=True))
    if grid_costs:
        box_fig.add_trace(go.Violin(y=grid_costs, name='Grid Only', fillcolor='rgba(220, 53, 69, 0.3)',
                                   line_color='#dc3545', box_visible=True, meanline_visible=True))
    
    box_fig.update_layout(
        title="📊 Cost Distribution Analysis with Statistical Details",
        yaxis_title="Total Cost (€/building)",
        height=400
    )
    
    # Calculate detailed statistics
    if p2p_costs and grid_costs:
        avg_p2p = np.mean(p2p_costs)
        avg_grid = np.mean(grid_costs)
        savings = ((avg_grid - avg_p2p) / avg_grid) * 100
        median_p2p = np.median(p2p_costs)
        median_grid = np.median(grid_costs)
        std_p2p = np.std(p2p_costs)
        std_grid = np.std(grid_costs)
    else:
        savings = 0
        avg_p2p = avg_grid = median_p2p = median_grid = std_p2p = std_grid = 0
    
    # Cost breakdown analysis
    cost_ranges = {
        'Low Cost (Bottom 25%)': len([c for c in costs if c <= np.percentile(costs, 25)]),
        'Medium Cost (25-75%)': len([c for c in costs if np.percentile(costs, 25) < c <= np.percentile(costs, 75)]),
        'High Cost (Top 25%)': len([c for c in costs if c > np.percentile(costs, 75)])
    }
    
    pie_fig = px.pie(
        values=list(cost_ranges.values()),
        names=list(cost_ranges.keys()),
        title="🥧 Cost Range Distribution",
        color_discrete_map={
            'Low Cost (Bottom 25%)': '#28a745',
            'Medium Cost (25-75%)': '#ffc107',
            'High Cost (Top 25%)': '#dc3545'
        }
    )
    pie_fig.update_layout(height=300)
    
    return dbc.Row([
        # Explanation Panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H6([html.I(className="fas fa-euro-sign me-2"), "Cost Analysis Explained"], className="mb-0")
                ]),
                dbc.CardBody([
                    html.P([
                        html.Strong("Purpose: "), "Detailed economic analysis comparing costs across all scenarios "
                        "and quantifying the financial benefits of P2P energy trading."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("Ranking Chart: "), "Scenarios sorted by cost from lowest (best) to highest (worst). "
                        "Green bars indicate P2P trading scenarios."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("Distribution Analysis: "), "Violin plots show the full cost distribution, "
                        "including median, quartiles, and outliers for each trading type."
                    ], className="small mb-0")
                ])
            ])
        ], width=12, className="mb-3"),
        
        # Cost ranking chart
        dbc.Col([
            dcc.Graph(figure=bar_fig)
        ], width=8),
        
        # Cost range pie chart
        dbc.Col([
            dcc.Graph(figure=pie_fig)
        ], width=4),
        
        # Statistical distribution
        dbc.Col([
            dcc.Graph(figure=box_fig)
        ], width=8),
        
        # Enhanced insights panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("💰 Economic Insights"),
                dbc.CardBody([
                    html.H4(f"{savings:.1f}%", className="text-success"),
                    html.P("Average P2P Savings", className="text-muted mb-3"),
                    
                    html.H6("📊 P2P Trading:", className="text-success mb-2"),
                    html.P([html.Strong("Average: "), f"€{avg_p2p:.2f}" if p2p_costs else "N/A"], className="small mb-1"),
                    html.P([html.Strong("Median: "), f"€{median_p2p:.2f}" if p2p_costs else "N/A"], className="small mb-1"),
                    html.P([html.Strong("Std Dev: "), f"±€{std_p2p:.2f}" if p2p_costs else "N/A"], className="small mb-3"),
                    
                    html.H6("🏢 Grid Only:", className="text-danger mb-2"),
                    html.P([html.Strong("Average: "), f"€{avg_grid:.2f}" if grid_costs else "N/A"], className="small mb-1"),
                    html.P([html.Strong("Median: "), f"€{median_grid:.2f}" if grid_costs else "N/A"], className="small mb-1"),
                    html.P([html.Strong("Std Dev: "), f"±€{std_grid:.2f}" if grid_costs else "N/A"], className="small mb-3"),
                    
                    html.H6("🎯 Key Findings:", className="text-primary mb-2"),
                    html.P([html.Strong("Best: "), f"€{min(costs):.2f}"], className="small mb-1"),
                    html.P([html.Strong("Worst: "), f"€{max(costs):.2f}"], className="small mb-1"),
                    html.P([html.Strong("Range: "), f"€{max(costs) - min(costs):.2f}"], className="small")
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
    # Enhanced energy flow data based on realistic prosumer community patterns
    hours = list(range(24))
    hour_labels = [f"{h:02d}:00" for h in hours]
    
    # Realistic residential demand profile (kWh per building average)
    building_demand = [
        1.2, 1.0, 0.9, 0.8, 0.8, 1.0, 1.5, 2.5, 3.2, 2.8, 2.5, 2.3,
        2.1, 2.0, 2.2, 2.8, 3.8, 5.2, 4.8, 4.2, 3.5, 2.8, 2.2, 1.6
    ]
    
    # Realistic PV generation profile (kWh per building with solar)
    pv_generation = [
        0, 0, 0, 0, 0, 0.1, 0.8, 2.2, 4.1, 6.2, 7.8, 8.5,
        8.9, 8.3, 7.1, 5.4, 3.2, 1.5, 0.3, 0, 0, 0, 0, 0
    ]
    
    # P2P trading: excess PV shared within community
    p2p_export = [max(0, gen - dem) * 0.85 for gen, dem in zip(pv_generation, building_demand)]
    p2p_import = [max(0, dem - gen) * 0.3 for dem, gen in zip(building_demand, pv_generation)]
    net_p2p = [exp if exp > 0 else -imp for exp, imp in zip(p2p_export, p2p_import)]
    
    # Grid interaction after P2P trading
    grid_import = [max(0, dem - gen - imp) for dem, gen, imp in zip(building_demand, pv_generation, p2p_import)]
    grid_export = [max(0, gen - dem - exp) for gen, dem, exp in zip(pv_generation, building_demand, p2p_export)]
    
    # Enhanced energy flow visualization
    energy_fig = go.Figure()
    
    # Add demand
    energy_fig.add_trace(go.Scatter(
        x=hour_labels, y=building_demand, name='Total Demand',
        line=dict(color='#dc3545', width=3), mode='lines+markers'
    ))
    
    # Add PV generation
    energy_fig.add_trace(go.Scatter(
        x=hour_labels, y=pv_generation, name='PV Generation',
        line=dict(color='#ffa500', width=3), mode='lines+markers',
        fill='tonexty', fillcolor='rgba(255, 165, 0, 0.1)'
    ))
    
    # Add P2P trading flow
    energy_fig.add_trace(go.Scatter(
        x=hour_labels, y=[abs(p) for p in net_p2p], name='P2P Trading Volume',
        line=dict(color='#28a745', width=2, dash='dot'), mode='lines+markers'
    ))
    
    # Add peak demand threshold
    peak_threshold = max(building_demand) * 0.8
    energy_fig.add_hline(y=peak_threshold, line_dash="dash", line_color="red",
                        annotation_text=f"Peak Threshold: {peak_threshold:.1f} kWh")
    
    energy_fig.update_layout(
        title="⚡ Comprehensive Daily Energy Flow Analysis",
        xaxis_title="Hour of Day",
        yaxis_title="Energy (kWh per building)",
        height=450,
        hovermode='x unified'
    )
    
    # Enhanced energy balance with multiple scenarios
    total_demand = sum(building_demand)
    total_pv = sum(pv_generation)
    total_p2p_vol = sum(abs(p) for p in net_p2p)
    total_grid_import = sum(grid_import)
    total_grid_export = sum(grid_export)
    
    # Energy sources pie chart
    balance_fig = px.pie(
        values=[total_pv - total_grid_export, total_grid_import, total_p2p_vol],
        names=['Local PV (Self-Consumed)', 'Grid Import', 'P2P Trading'],
        title="📊 Energy Source Mix",
        color_discrete_map={
            'Local PV (Self-Consumed)': '#ffa500',
            'Grid Import': '#dc3545',
            'P2P Trading': '#28a745'
        }
    )
    balance_fig.update_layout(height=350)
    
    # P2P trading pattern
    p2p_pattern_fig = go.Figure()
    p2p_pattern_fig.add_trace(go.Bar(
        x=hour_labels, y=p2p_export, name='P2P Export',
        marker_color='#28a745', opacity=0.7
    ))
    p2p_pattern_fig.add_trace(go.Bar(
        x=hour_labels, y=[-x for x in p2p_import], name='P2P Import',
        marker_color='#17a2b8', opacity=0.7
    ))
    
    p2p_pattern_fig.update_layout(
        title="🔄 P2P Trading Flow Pattern",
        xaxis_title="Hour of Day",
        yaxis_title="Energy Flow (kWh)",
        height=350,
        barmode='relative'
    )
    
    # Calculate key metrics
    self_sufficiency = (total_pv / total_demand) * 100
    p2p_utilization = (total_p2p_vol / total_pv) * 100 if total_pv > 0 else 0
    grid_dependency = (total_grid_import / total_demand) * 100
    export_ratio = (total_grid_export / total_pv) * 100 if total_pv > 0 else 0
    
    return dbc.Row([
        # Explanation Panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H6([html.I(className="fas fa-bolt me-2"), "Energy Flow Analysis Explained"], className="mb-0")
                ]),
                dbc.CardBody([
                    html.P([
                        html.Strong("Purpose: "), "Analyze energy generation, consumption, and trading patterns "
                        "to understand the community's energy dynamics and self-sufficiency potential."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("Main Chart: "), "Shows hourly demand vs PV generation profiles. "
                        "The gap between them indicates when grid import or P2P trading occurs."
                    ], className="small mb-2"),
                    html.P([
                        html.Strong("P2P Pattern: "), "Green bars show energy exported to neighbors, "
                        "blue bars show energy imported from neighbors during different hours."
                    ], className="small mb-0")
                ])
            ])
        ], width=12, className="mb-3"),
        
        # Main energy flow chart
        dbc.Col([
            dcc.Graph(figure=energy_fig)
        ], width=8),
        
        # Energy balance pie chart
        dbc.Col([
            dcc.Graph(figure=balance_fig)
        ], width=4),
        
        # P2P trading pattern
        dbc.Col([
            dcc.Graph(figure=p2p_pattern_fig)
        ], width=8),
        
        # Enhanced metrics panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("⚡ Energy Performance Metrics"),
                dbc.CardBody([
                    html.H6("🏠 Community Metrics:", className="text-primary mb-2"),
                    html.P([html.Strong("Self-Sufficiency: "), f"{self_sufficiency:.1f}%"], className="mb-1"),
                    html.P([html.Strong("Grid Dependency: "), f"{grid_dependency:.1f}%"], className="mb-1"),
                    html.P([html.Strong("P2P Utilization: "), f"{p2p_utilization:.1f}%"], className="mb-1"),
                    html.P([html.Strong("Export Ratio: "), f"{export_ratio:.1f}%"], className="mb-3"),
                    
                    html.H6("⏰ Peak Hours Analysis:", className="text-warning mb-2"),
                    html.P([html.Strong("Demand Peak: "), "18:00-19:00 (5.2 kWh)"], className="small mb-1"),
                    html.P([html.Strong("Generation Peak: "), "12:00-13:00 (8.9 kWh)"], className="small mb-1"),
                    html.P([html.Strong("P2P Peak: "), "11:00-15:00"], className="small mb-3"),
                    
                    html.H6("💡 Key Insights:", className="text-info mb-2"),
                    html.P("Morning: High import needs", className="small mb-1"),
                    html.P("Midday: Excess PV → P2P export", className="small mb-1"),
                    html.P("Evening: High demand + low PV", className="small")
                ])
            ])
        ], width=4)
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
    [Output("results-table", "data"),
     Output("results-table-container", "children")],
    [Input("simulation-data", "data"),
     Input("refresh-results-btn", "n_clicks"),
     Input("results-filter", "value")]
)
def update_results_table(simulation_data, n_clicks, filter_value):
    # Create the default table component
    default_table = dash_table.DataTable(
        id="results-table",
        columns=[
            {"name": "🏆 Rank", "id": "rank", "type": "numeric"},
            {"name": "📋 Scenario", "id": "scenario"},
            {"name": "💰 Total Cost (€)", "id": "cost", "type": "numeric", "format": {"specifier": ".2f"}},
            {"name": "⚖️ Fairness", "id": "fairness", "type": "numeric", "format": {"specifier": ".3f"}},
            {"name": "🔄 P2P Trading", "id": "p2p"},
            {"name": "📈 Savings (%)", "id": "savings", "type": "numeric", "format": {"specifier": ".1f"}},
            {"name": "⭐ Performance", "id": "performance"}
        ],
        data=[],
        sort_action="native",
        filter_action="native",
        style_cell={
            'textAlign': 'left', 
            'fontSize': '14px',
            'padding': '12px',
            'whiteSpace': 'normal',
            'height': 'auto',
            'fontFamily': 'system-ui, -apple-system, sans-serif'
        },
        style_header={
            'backgroundColor': '#f8f9fa',
            'fontWeight': 'bold',
            'fontSize': '14px',
            'color': '#495057',
            'border': '1px solid #dee2e6',
            'textAlign': 'center'
        },
        style_data={
            'border': '1px solid #dee2e6',
            'backgroundColor': '#ffffff'
        },
        style_data_conditional=[
            {
                'if': {'filter_query': '{p2p} = ✅ Yes'},
                'backgroundColor': '#e8f5e8',
                'border': '1px solid #28a745'
            },
            {
                'if': {'column_id': 'rank', 'filter_query': '{rank} = 1'},
                'backgroundColor': '#ffd700',
                'fontWeight': 'bold',
                'color': '#8B4513'
            },
            {
                'if': {'column_id': 'rank', 'filter_query': '{rank} = 2'},
                'backgroundColor': '#C0C0C0',
                'fontWeight': 'bold',
                'color': '#444444'
            },
            {
                'if': {'column_id': 'rank', 'filter_query': '{rank} = 3'},
                'backgroundColor': '#CD7F32',
                'fontWeight': 'bold',
                'color': '#ffffff'
            }
        ],
        style_cell_conditional=[
            {'if': {'column_id': 'rank'}, 'width': '80px', 'textAlign': 'center'},
            {'if': {'column_id': 'scenario'}, 'width': '220px', 'textAlign': 'left'},
            {'if': {'column_id': 'cost'}, 'width': '140px', 'textAlign': 'right'},
            {'if': {'column_id': 'fairness'}, 'width': '120px', 'textAlign': 'right'},
            {'if': {'column_id': 'p2p'}, 'width': '120px', 'textAlign': 'center'},
            {'if': {'column_id': 'savings'}, 'width': '120px', 'textAlign': 'right'},
            {'if': {'column_id': 'performance'}, 'width': '150px', 'textAlign': 'center'}
        ],
        page_size=15,
        style_table={
            'overflowX': 'auto',
            'border': '1px solid #dee2e6',
            'borderRadius': '0.375rem',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
        }
    )
    
    # Use either fresh simulation data or loaded results
    global simulation_results
    
    # Reload existing results if refresh button was clicked
    if n_clicks:
        fresh_results = load_existing_results()
        if fresh_results:
            simulation_results.update(fresh_results)
    
    # Determine which data source to use
    data_source = None
    if simulation_data and 'scenario_results' in simulation_data:
        data_source = simulation_data  # Use fresh simulation data
    elif simulation_results and 'scenario_results' in simulation_results:
        data_source = simulation_results  # Use loaded results
    
    if not data_source:
        empty_state = html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-table fa-3x text-muted mb-3"),
                        html.H5("No Results Available", className="text-muted mb-3"),
                        html.P("Run a simulation to see scenario results and rankings here.", className="text-muted mb-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button([
                                    html.I(className="fas fa-play me-2"),
                                    "Start Simulation"
                                ], color="primary", outline=True, href="#configuration")
                            ], width="auto"),
                            dbc.Col([
                                dbc.Button([
                                    html.I(className="fas fa-refresh me-2"),
                                    "Load Existing Results"
                                ], id="refresh-results-btn", color="info", outline=True)
                            ], width="auto")
                        ], justify="center", className="g-2")
                    ], className="text-center py-4")
                ])
            ], className="border-0 bg-light")
        ])
        return [], empty_state
    
    scenario_results = data_source['scenario_results']
    successful = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    # Apply filtering based on user selection
    if filter_value == "p2p_only":
        successful = {k: v for k, v in successful.items() if v.get('with_p2p', False)}
    elif filter_value == "no_p2p":
        successful = {k: v for k, v in successful.items() if not v.get('with_p2p', False)}
    elif filter_value == "comparison":
        # Group by base name and only show pairs where both P2P and non-P2P exist
        from collections import defaultdict
        base_groups = defaultdict(list)
        for name, result in successful.items():
            base_name = name.replace('_with_p2p', '').replace('_without_p2p', '')
            base_groups[base_name].append((name, result))
        
        # Only keep complete pairs (both P2P and non-P2P)
        filtered_successful = {}
        for base_name, scenarios in base_groups.items():
            if len(scenarios) == 2:  # Both P2P and non-P2P exist
                for name, result in scenarios:
                    filtered_successful[name] = result
        successful = filtered_successful
    # filter_value == "all" shows everything (no filtering)
    
    if not successful:
        no_data_state = html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-exclamation-triangle fa-3x text-warning mb-3"),
                        html.H5("No Successful Scenarios", className="text-warning mb-3"),
                        html.P("The simulation completed but no scenarios were successful. Please check your configuration and try again.", className="text-muted mb-3"),
                        dbc.Button([
                            html.I(className="fas fa-cog me-2"),
                            "Adjust Settings"
                        ], color="warning", outline=True)
                    ], className="text-center py-4")
                ])
            ], className="border-warning")
        ])
        return [], no_data_state
    
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
            'performance': performance,
            'score': score  # Keep score for sorting
        })
    
    # Sort by score (best first)
    table_data.sort(key=lambda x: x['score'], reverse=True)
    
    # Add rank column
    for i, row in enumerate(table_data):
        row['rank'] = i + 1
    
    # Update the table data and return the populated table
    default_table.data = table_data
    
    return table_data, default_table


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