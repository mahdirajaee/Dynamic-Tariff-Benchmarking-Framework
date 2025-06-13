import os
import sys
import json
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, send_file, session
import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table, ClientsideFunction
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import io
import base64
import uuid

from src.simulation_orchestrator import SimulationOrchestrator
from dashboard_components import (
    create_advanced_config_tab, create_basic_config_panel, 
    create_tariff_config_panel, create_p2p_config_panel,
    create_results_overview_tab, create_interactive_analysis_tab,
    create_detailed_scenario_view, create_export_controls
)


server = Flask(__name__)
server.secret_key = 'prosumer-framework-secret-key'

app = dash.Dash(__name__, 
                server=server,
                url_base_pathname='/dashboard/',
                external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
                suppress_callback_exceptions=True)

orchestrator = SimulationOrchestrator()
simulation_results = {}
simulation_status = {"running": False, "progress": 0, "message": "Ready", "task": None}
active_simulations = {}


@server.route('/')
def index():
    return render_template('index.html')

@server.route('/api/status')
def get_status():
    return jsonify(simulation_status)

@server.route('/api/start_simulation', methods=['POST'])
def start_simulation():
    global simulation_status, simulation_results, active_simulations
    
    if simulation_status["running"]:
        return jsonify({"error": "Simulation already running"}), 400
    
    config = request.json
    simulation_id = str(uuid.uuid4())
    
    def run_simulation():
        global simulation_status, simulation_results
        
        try:
            simulation_status = {"running": True, "progress": 5, "message": "Initializing framework...", "task": "init"}
            
            orchestrator.num_buildings = config.get('num_buildings', 10)
            orchestrator.time_horizon = config.get('time_horizon', 96)
            orchestrator.initialize()
            
            simulation_status["progress"] = 20
            simulation_status["message"] = "Framework initialized. Starting benchmark..."
            simulation_status["task"] = "benchmark"
            
            results = orchestrator.benchmark_tariff_scenarios(
                num_scenarios=config.get('num_scenarios', 20),
                include_p2p_comparison=config.get('include_p2p', True)
            )
            
            simulation_status["progress"] = 60
            simulation_status["message"] = "Benchmark completed. Processing results..."
            simulation_status["task"] = "processing"
            
            if config.get('train_surrogate', False):
                simulation_status["message"] = "Training surrogate model..."
                simulation_status["task"] = "surrogate"
                surrogate_results = orchestrator.train_surrogate_model()
                results['surrogate'] = surrogate_results
                simulation_status["progress"] = 80
            
            if config.get('rapid_eval', 0) > 0:
                simulation_status["message"] = "Running rapid evaluations..."
                simulation_status["task"] = "rapid"
                rapid_results = orchestrator.rapid_scenario_evaluation(config['rapid_eval'])
                results['rapid_evaluation'] = rapid_results
                simulation_status["progress"] = 90
            
            if config.get('sensitivity', False):
                simulation_status["message"] = "Running sensitivity analysis..."
                simulation_status["task"] = "sensitivity"
                sensitivity_ranges = {
                    'export_ratio': [0.2, 0.3, 0.4, 0.5, 0.6],
                    'community_spread': [0.3, 0.4, 0.5, 0.6, 0.7]
                }
                sensitivity_results = orchestrator.sensitivity_analysis(sensitivity_ranges)
                results['sensitivity'] = sensitivity_results
            
            summary_stats = orchestrator.get_summary_statistics()
            results['summary_statistics'] = summary_stats
            
            simulation_results = results
            simulation_status = {"running": False, "progress": 100, "message": "Simulation completed successfully!", "task": "completed"}
            
        except Exception as e:
            simulation_status = {"running": False, "progress": 0, "message": f"Error: {str(e)}", "task": "error"}
    
    thread = threading.Thread(target=run_simulation)
    thread.start()
    active_simulations[simulation_id] = thread
    
    return jsonify({"message": "Simulation started", "simulation_id": simulation_id})

@server.route('/api/stop_simulation', methods=['POST'])
def stop_simulation():
    global simulation_status
    simulation_status = {"running": False, "progress": 0, "message": "Simulation stopped by user", "task": "stopped"}
    return jsonify({"message": "Simulation stopped"})

@server.route('/api/results')
def get_results():
    return jsonify(simulation_results)


app.layout = dbc.Container([
    dcc.Store(id='simulation-data', storage_type='session'),
    dcc.Store(id='config-data', storage_type='session'),
    dcc.Interval(id='status-interval', interval=1000, n_intervals=0),
    dcc.Location(id='url', refresh=False),
    
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Configuration", href="#", id="nav-config")),
            dbc.NavItem(dbc.NavLink("Results", href="#", id="nav-results")),
            dbc.NavItem(dbc.NavLink("Analysis", href="#", id="nav-analysis")),
            dbc.NavItem(dbc.NavLink("Export", href="#", id="nav-export")),
        ],
        brand="Prosumer Energy Dashboard",
        brand_href="/",
        color="primary",
        dark=True,
        className="mb-4"
    ),
    
    dbc.Tabs([
        dbc.Tab(label="Configuration", tab_id="config", id="tab-config"),
        dbc.Tab(label="Results Overview", tab_id="results", id="tab-results"),
        dbc.Tab(label="Interactive Analysis", tab_id="analysis", id="tab-analysis"),
        dbc.Tab(label="Scenario Details", tab_id="details", id="tab-details"),
        dbc.Tab(label="Export & Download", tab_id="export", id="tab-export")
    ], id="main-tabs", active_tab="config"),
    
    html.Div(id="main-content", className="mt-4"),
    
    dbc.Modal([
        dbc.ModalHeader("Simulation Progress"),
        dbc.ModalBody([
            html.Div(id="modal-status-message"),
            dbc.Progress(id="modal-progress-bar", className="mb-3"),
            html.Div(id="modal-task-details")
        ]),
        dbc.ModalFooter([
            dbc.Button("Stop Simulation", id="modal-stop-btn", color="danger"),
            dbc.Button("Hide", id="modal-close-btn", color="secondary")
        ])
    ], id="progress-modal", is_open=False, backdrop="static")
    
], fluid=True)


@app.callback(
    Output("main-content", "children"),
    Input("main-tabs", "active_tab"),
    Input("simulation-data", "data")
)
def render_main_content(active_tab, simulation_data):
    if active_tab == "config":
        return render_config_content()
    elif active_tab == "results":
        return render_results_content(simulation_data)
    elif active_tab == "analysis":
        return render_analysis_content(simulation_data)
    elif active_tab == "details":
        return render_details_content(simulation_data)
    elif active_tab == "export":
        return render_export_content()
    
    return html.Div("Select a tab to begin")


def render_config_content():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H4("Simulation Configuration", className="mb-0")),
                    dbc.CardBody([
                        dbc.Tabs([
                            dbc.Tab(label="Basic Settings", tab_id="basic-config"),
                            dbc.Tab(label="Tariff Configuration", tab_id="tariff-config"),
                            dbc.Tab(label="P2P Trading", tab_id="p2p-config"),
                            dbc.Tab(label="Advanced Options", tab_id="advanced-config")
                        ], id="config-subtabs", active_tab="basic-config"),
                        
                        html.Div(id="config-content", className="mt-4")
                    ])
                ])
            ], width=8),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Simulation Control"),
                    dbc.CardBody([
                        html.Div(id="status-display"),
                        dbc.Progress(id="progress-bar", value=0, className="mb-3", style={"height": "20px"}),
                        dbc.ButtonGroup([
                            dbc.Button("Start Simulation", id="start-btn", color="primary", size="lg"),
                            dbc.Button("Stop", id="stop-btn", color="danger", disabled=True)
                        ], className="w-100 mb-3"),
                        dbc.Button("View Progress", id="show-progress-btn", color="info", className="w-100", disabled=True)
                    ])
                ]),
                
                dbc.Card([
                    dbc.CardHeader("Quick Actions"),
                    dbc.CardBody([
                        dbc.Button("Load Example Config", color="secondary", className="w-100 mb-2", id="load-example"),
                        dbc.Button("Save Configuration", color="warning", className="w-100 mb-2", id="save-config"),
                        dbc.Button("Reset to Defaults", color="light", className="w-100", id="reset-config")
                    ])
                ], className="mt-3")
            ], width=4)
        ])
    ])


def render_results_content(simulation_data):
    if not simulation_data:
        return dbc.Alert([
            html.H4("No Results Available", className="alert-heading"),
            html.P("Please run a simulation from the Configuration tab to see results here."),
            dbc.Button("Go to Configuration", href="#", id="goto-config", color="primary")
        ], color="info")
    
    return create_results_overview_tab(simulation_data)


def render_analysis_content(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation data available for analysis.", color="info")
    
    return create_interactive_analysis_tab(simulation_data)


def render_details_content(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation data available for detailed view.", color="info")
    
    return create_detailed_scenario_view()


def render_export_content():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                create_export_controls()
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Export History"),
                    dbc.CardBody([
                        html.P("Recent exports will appear here"),
                        dash_table.DataTable(
                            id="export-history-table",
                            columns=[
                                {"name": "Date", "id": "date"},
                                {"name": "Format", "id": "format"},
                                {"name": "Size", "id": "size"},
                                {"name": "Download", "id": "download"}
                            ],
                            data=[]
                        )
                    ])
                ])
            ], width=6)
        ])
    ])


@app.callback(
    Output("config-content", "children"),
    Input("config-subtabs", "active_tab")
)
def render_config_subtab(active_subtab):
    if active_subtab == "basic-config":
        return create_basic_config_panel()
    elif active_subtab == "tariff-config":
        return create_tariff_config_panel()
    elif active_subtab == "p2p-config":
        return create_p2p_config_panel()
    elif active_subtab == "advanced-config":
        return create_advanced_config_panel()
    
    return html.Div("Select a configuration category")


def create_advanced_config_panel():
    return dbc.Form([
        dbc.Row([
            dbc.Col([
                dbc.Label("Battery Configuration"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Capacity Range (kWh)", size="sm"),
                        dbc.InputGroup([
                            dbc.Input(type="number", value=10, id="battery-min-capacity"),
                            dbc.InputGroupText("to"),
                            dbc.Input(type="number", value=20, id="battery-max-capacity")
                        ])
                    ])
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Efficiency (%)", size="sm"),
                        dbc.Input(type="number", value=95, min=50, max=100, id="battery-efficiency")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("Initial SOC (%)", size="sm"),
                        dbc.Input(type="number", value=50, min=0, max=100, id="initial-soc")
                    ], width=6)
                ], className="mt-2")
            ], width=6),
            
            dbc.Col([
                dbc.Label("Solver Configuration"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Solver", size="sm"),
                        dcc.Dropdown([
                            {"label": "ECOS", "value": "ECOS"},
                            {"label": "OSQP", "value": "OSQP"},
                            {"label": "CVXOPT", "value": "CVXOPT"}
                        ], value="ECOS", id="solver-choice")
                    ])
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Timeout (seconds)", size="sm"),
                        dbc.Input(type="number", value=300, id="solver-timeout")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("Tolerance", size="sm"),
                        dbc.Input(type="number", value=1e-6, step=1e-7, id="solver-tolerance")
                    ], width=6)
                ], className="mt-2")
            ], width=6)
        ])
    ])


@app.callback(
    [Output("status-display", "children"),
     Output("progress-bar", "value"),
     Output("start-btn", "disabled"),
     Output("stop-btn", "disabled"),
     Output("show-progress-btn", "disabled"),
     Output("simulation-data", "data"),
     Output("progress-modal", "is_open"),
     Output("modal-status-message", "children"),
     Output("modal-progress-bar", "value"),
     Output("modal-task-details", "children")],
    [Input("status-interval", "n_intervals"),
     Input("start-btn", "n_clicks"),
     Input("stop-btn", "n_clicks"),
     Input("show-progress-btn", "n_clicks"),
     Input("modal-close-btn", "n_clicks"),
     Input("modal-stop-btn", "n_clicks")],
    [State("num-buildings", "value"),
     State("time-horizon", "value"),
     State("num-scenarios", "value"),
     State("rapid-evaluations", "value"),
     State("analysis-options", "value"),
     State("progress-modal", "is_open")]
)
def update_simulation_control(n_intervals, start_clicks, stop_clicks, show_progress_clicks,
                            modal_close_clicks, modal_stop_clicks,
                            num_buildings, time_horizon, num_scenarios, rapid_eval, options, modal_open):
    global simulation_status, simulation_results
    
    ctx = callback_context
    
    if not ctx.triggered:
        trigger_id = None
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'start-btn' and start_clicks:
        config = {
            'num_buildings': num_buildings or 10,
            'time_horizon': time_horizon or 96,
            'num_scenarios': num_scenarios or 20,
            'rapid_eval': rapid_eval or 0,
            'include_p2p': 'p2p' in (options or []),
            'train_surrogate': 'surrogate' in (options or []),
            'sensitivity': 'sensitivity' in (options or [])
        }
        
        import requests
        try:
            requests.post('http://localhost:8050/api/start_simulation', json=config)
        except:
            pass
    
    elif trigger_id == 'stop-btn' or trigger_id == 'modal-stop-btn':
        import requests
        try:
            requests.post('http://localhost:8050/api/stop_simulation')
        except:
            pass
    
    try:
        import requests
        response = requests.get('http://localhost:8050/api/status')
        status = response.json()
    except:
        status = simulation_status
    
    status_badge_color = "primary" if status['running'] else ("success" if status['progress'] == 100 else "secondary")
    status_component = dbc.Badge(status['message'], color=status_badge_color, className="w-100 p-2")
    
    task_details = ""
    if status.get('task'):
        task_map = {
            'init': 'Initializing simulation framework...',
            'benchmark': 'Running tariff scenario benchmarks...',
            'processing': 'Processing optimization results...',
            'surrogate': 'Training machine learning surrogate model...',
            'rapid': 'Performing rapid scenario evaluations...',
            'sensitivity': 'Running sensitivity analysis...',
            'completed': 'All tasks completed successfully!',
            'error': 'An error occurred during simulation.',
            'stopped': 'Simulation was stopped by user.'
        }
        task_details = task_map.get(status['task'], status['task'])
    
    modal_should_open = (trigger_id == 'show-progress-btn' and show_progress_clicks) or (status['running'] and trigger_id == 'start-btn')
    modal_should_close = trigger_id == 'modal-close-btn' and modal_close_clicks
    
    if modal_should_close:
        modal_open = False
    elif modal_should_open:
        modal_open = True
    
    return (status_component,
            status['progress'],
            status['running'],
            not status['running'],
            status['progress'] == 0,
            simulation_results if simulation_results else {},
            modal_open,
            status['message'],
            status['progress'],
            task_details)


@app.callback(
    Output("interactive-analysis-chart", "figure"),
    [Input("analysis-type", "value"),
     Input("chart-type", "value"),
     Input("scenario-filters", "value")],
    [State("simulation-data", "data")]
)
def update_interactive_chart(analysis_type, chart_type, filters, simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return go.Figure().add_annotation(text="No data available", showarrow=False)
    
    scenario_results = simulation_data['scenario_results']
    
    filtered_scenarios = {}
    for name, result in scenario_results.items():
        if result.get('status') != 'success':
            continue
        
        include = False
        if 'p2p' in filters and result.get('with_p2p', False):
            include = True
        if 'no_p2p' in filters and not result.get('with_p2p', True):
            include = True
        
        if include:
            filtered_scenarios[name] = result
    
    if not filtered_scenarios:
        return go.Figure().add_annotation(text="No scenarios match the selected filters", showarrow=False)
    
    names = list(filtered_scenarios.keys())
    
    if analysis_type == "cost":
        values = [result['total_cost'] for result in filtered_scenarios.values()]
        title = "Total Cost Analysis"
        y_label = "Total Cost (€)"
    elif analysis_type == "fairness":
        values = [result['fairness'] for result in filtered_scenarios.values()]
        title = "Fairness Analysis"
        y_label = "Fairness (CoV)"
    elif analysis_type == "energy":
        values = [result.get('energy_metrics', {}).get('self_sufficiency_ratio', 0) 
                 for result in filtered_scenarios.values()]
        title = "Self-Sufficiency Analysis"
        y_label = "Self-Sufficiency Ratio"
    else:
        values = [result['total_cost'] for result in filtered_scenarios.values()]
        title = "Default Analysis"
        y_label = "Value"
    
    p2p_status = ['P2P' if result.get('with_p2p', False) else 'No P2P' 
                  for result in filtered_scenarios.values()]
    
    if chart_type == "bar":
        fig = px.bar(x=names, y=values, color=p2p_status, title=title)
        fig.update_xaxes(tickangle=45)
    elif chart_type == "scatter":
        costs = [result['total_cost'] for result in filtered_scenarios.values()]
        fairness = [result['fairness'] for result in filtered_scenarios.values()]
        fig = px.scatter(x=costs, y=fairness, color=p2p_status, hover_name=names,
                        title="Cost vs Fairness", labels={'x': 'Cost (€)', 'y': 'Fairness (CoV)'})
    elif chart_type == "box":
        df = pd.DataFrame({'Value': values, 'P2P': p2p_status})
        fig = px.box(df, x='P2P', y='Value', title=title)
    else:
        fig = px.bar(x=names, y=values, title=title)
    
    fig.update_layout(height=500, margin=dict(l=0, r=0, t=40, b=0))
    
    return fig


if __name__ == '__main__':
    import threading
    
    def run_flask():
        server.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    app.run_server(debug=True, host='0.0.0.0', port=8050)