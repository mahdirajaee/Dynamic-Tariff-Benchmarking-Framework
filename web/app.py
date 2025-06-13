import os
import sys
import json
import threading
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, send_file, session
import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
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


server = Flask(__name__)
server.secret_key = 'your-secret-key-change-in-production'

app = dash.Dash(__name__, 
                server=server,
                url_base_pathname='/dashboard/',
                external_stylesheets=[dbc.themes.BOOTSTRAP])

orchestrator = SimulationOrchestrator()
simulation_results = {}
simulation_status = {"running": False, "progress": 0, "message": "Ready"}


@server.route('/')
def index():
    return render_template('index.html')

@server.route('/api/status')
def get_status():
    return jsonify(simulation_status)

@server.route('/api/start_simulation', methods=['POST'])
def start_simulation():
    global simulation_status, simulation_results
    
    if simulation_status["running"]:
        return jsonify({"error": "Simulation already running"}), 400
    
    config = request.json
    
    def run_simulation():
        global simulation_status, simulation_results
        
        try:
            simulation_status = {"running": True, "progress": 10, "message": "Initializing..."}
            
            orchestrator.num_buildings = config.get('num_buildings', 10)
            orchestrator.time_horizon = config.get('time_horizon', 96)
            orchestrator.initialize()
            
            simulation_status["progress"] = 30
            simulation_status["message"] = "Running benchmark..."
            
            results = orchestrator.benchmark_tariff_scenarios(
                num_scenarios=config.get('num_scenarios', 20),
                include_p2p_comparison=config.get('include_p2p', True)
            )
            
            simulation_status["progress"] = 70
            simulation_status["message"] = "Processing results..."
            
            if config.get('train_surrogate', False):
                surrogate_results = orchestrator.train_surrogate_model()
                results['surrogate'] = surrogate_results
            
            if config.get('rapid_eval', 0) > 0:
                rapid_results = orchestrator.rapid_scenario_evaluation(config['rapid_eval'])
                results['rapid_evaluation'] = rapid_results
            
            simulation_results = results
            simulation_status = {"running": False, "progress": 100, "message": "Completed"}
            
        except Exception as e:
            simulation_status = {"running": False, "progress": 0, "message": f"Error: {str(e)}"}
    
    thread = threading.Thread(target=run_simulation)
    thread.start()
    
    return jsonify({"message": "Simulation started"})

@server.route('/api/results')
def get_results():
    return jsonify(simulation_results)

@server.route('/api/download_results')
def download_results():
    if not simulation_results:
        return jsonify({"error": "No results available"}), 404
    
    output = io.StringIO()
    json.dump(simulation_results, output, indent=2, default=str)
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'simulation_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )


app.layout = dbc.Container([
    dcc.Store(id='simulation-data'),
    dcc.Interval(id='interval-component', interval=2000, n_intervals=0),
    
    dbc.Row([
        dbc.Col([
            html.H1("Dynamic Tariff Benchmarking Dashboard", className="text-center mb-4"),
            html.Hr()
        ])
    ]),
    
    dbc.Tabs([
        dbc.Tab(label="Configuration", tab_id="config"),
        dbc.Tab(label="Simulation Results", tab_id="results"),
        dbc.Tab(label="Scenario Analysis", tab_id="analysis"),
        dbc.Tab(label="Fairness Metrics", tab_id="fairness"),
        dbc.Tab(label="Energy Flows", tab_id="energy"),
        dbc.Tab(label="Surrogate Model", tab_id="surrogate")
    ], id="tabs", active_tab="config"),
    
    html.Div(id="tab-content", className="mt-4")
], fluid=True)


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("simulation-data", "data")
)
def render_tab_content(active_tab, simulation_data):
    if active_tab == "config":
        return render_config_tab()
    elif active_tab == "results":
        return render_results_tab(simulation_data)
    elif active_tab == "analysis":
        return render_analysis_tab(simulation_data)
    elif active_tab == "fairness":
        return render_fairness_tab(simulation_data)
    elif active_tab == "energy":
        return render_energy_tab(simulation_data)
    elif active_tab == "surrogate":
        return render_surrogate_tab(simulation_data)
    
    return html.Div("Select a tab")


def render_config_tab():
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Simulation Configuration"),
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Number of Buildings"),
                                dbc.Input(id="num-buildings", type="number", value=10, min=2, max=50)
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Time Horizon (15-min intervals)"),
                                dbc.Input(id="time-horizon", type="number", value=96, min=24, max=672)
                            ], width=6)
                        ], className="mb-3"),
                        
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Number of Scenarios"),
                                dbc.Input(id="num-scenarios", type="number", value=20, min=5, max=100)
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Rapid Evaluations"),
                                dbc.Input(id="rapid-eval", type="number", value=0, min=0, max=10000)
                            ], width=6)
                        ], className="mb-3"),
                        
                        dbc.Row([
                            dbc.Col([
                                dbc.Checklist(
                                    options=[
                                        {"label": "Include P2P Trading Comparison", "value": "p2p"},
                                        {"label": "Train Surrogate Model", "value": "surrogate"}
                                    ],
                                    value=["p2p"],
                                    id="simulation-options"
                                )
                            ])
                        ], className="mb-3"),
                        
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("Start Simulation", id="start-btn", color="primary", size="lg", className="w-100"),
                                html.Div(id="simulation-status", className="mt-3")
                            ])
                        ])
                    ])
                ])
            ])
        ], width=8),
        
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Quick Actions"),
                dbc.CardBody([
                    dbc.Button("Load Sample Data", color="secondary", className="w-100 mb-2"),
                    dbc.Button("Download Results", id="download-btn", color="success", className="w-100 mb-2", disabled=True),
                    dbc.Button("Reset Configuration", color="warning", className="w-100")
                ])
            ])
        ], width=4)
    ])


def render_results_tab(simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return dbc.Alert("No simulation results available. Please run a simulation first.", color="info")
    
    scenario_results = simulation_data['scenario_results']
    successful_scenarios = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    if not successful_scenarios:
        return dbc.Alert("No successful scenarios found.", color="warning")
    
    summary_data = []
    for name, result in successful_scenarios.items():
        summary_data.append({
            'Scenario': name,
            'Total Cost': f"{result.get('total_cost', 0):.2f}",
            'Fairness (CoV)': f"{result.get('fairness', 0):.3f}",
            'P2P Trading': "Yes" if result.get('with_p2p', False) else "No",
            'Self Sufficiency': f"{result.get('energy_metrics', {}).get('self_sufficiency_ratio', 0):.2f}"
        })
    
    df = pd.DataFrame(summary_data)
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Simulation Summary"),
                dbc.CardBody([
                    html.H4(f"Completed: {len(successful_scenarios)}/{len(scenario_results)} scenarios"),
                    html.P(f"Total scenarios: {simulation_data.get('total_scenarios', 0)}"),
                    html.P(f"Successful scenarios: {simulation_data.get('successful_scenarios', 0)}")
                ])
            ])
        ], width=6),
        
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Best Scenarios"),
                dbc.CardBody([
                    html.Div(id="best-scenarios-content")
                ])
            ])
        ], width=6),
        
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("All Scenarios"),
                dbc.CardBody([
                    dash_table.DataTable(
                        data=df.to_dict('records'),
                        columns=[{"name": i, "id": i} for i in df.columns],
                        style_cell={'textAlign': 'left'},
                        style_data_conditional=[
                            {
                                'if': {'filter_query': '{P2P Trading} = Yes'},
                                'backgroundColor': '#e8f5e8',
                            }
                        ],
                        sort_action="native",
                        page_size=10
                    )
                ])
            ])
        ], width=12, className="mt-3")
    ])


def render_analysis_tab(simulation_data):
    if not simulation_data or 'scenario_results' not in simulation_data:
        return dbc.Alert("No simulation results available.", color="info")
    
    scenario_results = simulation_data['scenario_results']
    successful_scenarios = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    costs = [result['total_cost'] for result in successful_scenarios.values()]
    fairness = [result['fairness'] for result in successful_scenarios.values()]
    names = list(successful_scenarios.keys())
    p2p_status = ['With P2P' if result.get('with_p2p', False) else 'Without P2P' 
                  for result in successful_scenarios.values()]
    
    cost_comparison_fig = px.bar(
        x=names, y=costs, color=p2p_status,
        title="Total Cost Comparison by Scenario",
        labels={'x': 'Scenario', 'y': 'Total Cost (€)'}
    )
    cost_comparison_fig.update_xaxes(tickangle=45)
    
    fairness_cost_fig = px.scatter(
        x=costs, y=fairness, color=p2p_status, hover_name=names,
        title="Cost vs Fairness Trade-off",
        labels={'x': 'Total Cost (€)', 'y': 'Fairness (CoV)'}
    )
    
    fairness_dist_fig = px.histogram(
        x=fairness, nbins=10,
        title="Fairness Distribution",
        labels={'x': 'Fairness (CoV)', 'y': 'Count'}
    )
    
    return dbc.Row([
        dbc.Col([
            dcc.Graph(figure=cost_comparison_fig)
        ], width=12),
        
        dbc.Col([
            dcc.Graph(figure=fairness_cost_fig)
        ], width=6),
        
        dbc.Col([
            dcc.Graph(figure=fairness_dist_fig)
        ], width=6)
    ])


def render_fairness_tab(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation results available.", color="info")
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Fairness Metrics Analysis"),
                dbc.CardBody([
                    html.P("Detailed fairness analysis will be displayed here"),
                    dcc.Graph(id="fairness-metrics-chart")
                ])
            ])
        ])
    ])


def render_energy_tab(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation results available.", color="info")
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Energy Flow Analysis"),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Select Scenario"),
                            dcc.Dropdown(id="scenario-selector")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Select Building"),
                            dcc.Dropdown(id="building-selector")
                        ], width=6)
                    ]),
                    dcc.Graph(id="energy-flow-chart")
                ])
            ])
        ])
    ])


def render_surrogate_tab(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation results available.", color="info")
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Surrogate Model Analysis"),
                dbc.CardBody([
                    html.P("Surrogate model performance and feature importance"),
                    dcc.Graph(id="surrogate-performance-chart")
                ])
            ])
        ])
    ])


@app.callback(
    [Output("simulation-status", "children"),
     Output("start-btn", "disabled"),
     Output("download-btn", "disabled"),
     Output("simulation-data", "data")],
    [Input("interval-component", "n_intervals"),
     Input("start-btn", "n_clicks")],
    [State("num-buildings", "value"),
     State("time-horizon", "value"),
     State("num-scenarios", "value"),
     State("rapid-eval", "value"),
     State("simulation-options", "value")]
)
def update_simulation_status(n_intervals, n_clicks, num_buildings, time_horizon, 
                           num_scenarios, rapid_eval, options):
    global simulation_status, simulation_results
    
    ctx = callback_context
    
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'start-btn.n_clicks' and n_clicks:
        config = {
            'num_buildings': num_buildings,
            'time_horizon': time_horizon,
            'num_scenarios': num_scenarios,
            'rapid_eval': rapid_eval,
            'include_p2p': 'p2p' in (options or []),
            'train_surrogate': 'surrogate' in (options or [])
        }
        
        import requests
        try:
            requests.post('http://localhost:5000/api/start_simulation', json=config)
        except:
            pass
    
    try:
        import requests
        response = requests.get('http://localhost:5000/api/status')
        status = response.json()
    except:
        status = simulation_status
    
    status_component = dbc.Alert(
        [
            html.H6(status['message']),
            dbc.Progress(value=status['progress'], className="mb-2") if status['running'] else None
        ],
        color="info" if status['running'] else ("success" if status['progress'] == 100 else "light")
    )
    
    return (status_component, 
            status['running'], 
            len(simulation_results) == 0,
            simulation_results if simulation_results else {})


if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8050)