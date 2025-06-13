import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np


def create_advanced_config_tab():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H4("Simulation Configuration", className="mb-0")),
                    dbc.CardBody([
                        dbc.Tabs([
                            dbc.Tab(label="Basic Settings", tab_id="basic"),
                            dbc.Tab(label="Tariff Settings", tab_id="tariffs"),
                            dbc.Tab(label="P2P Settings", tab_id="p2p"),
                            dbc.Tab(label="Advanced", tab_id="advanced")
                        ], id="config-tabs", active_tab="basic"),
                        
                        html.Div(id="config-tab-content", className="mt-4")
                    ])
                ])
            ], width=8),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Simulation Status"),
                    dbc.CardBody([
                        html.Div(id="status-display"),
                        dbc.Progress(id="progress-bar", value=0, className="mb-3"),
                        dbc.ButtonGroup([
                            dbc.Button("Start", id="start-simulation", color="primary"),
                            dbc.Button("Stop", id="stop-simulation", color="danger", disabled=True),
                            dbc.Button("Reset", id="reset-simulation", color="secondary")
                        ], className="w-100")
                    ])
                ]),
                
                dbc.Card([
                    dbc.CardHeader("Quick Actions"),
                    dbc.CardBody([
                        dbc.Button("Load Example", color="info", className="w-100 mb-2"),
                        dbc.Button("Export Config", color="secondary", className="w-100 mb-2"),
                        dbc.Button("Download Results", id="download-results", color="success", className="w-100", disabled=True)
                    ])
                ], className="mt-3")
            ], width=4)
        ])
    ])


def create_basic_config_panel():
    return dbc.Form([
        dbc.Row([
            dbc.Col([
                dbc.Label("Number of Buildings"),
                dbc.InputGroup([
                    dbc.Input(id="num-buildings", type="number", value=10, min=2, max=50),
                    dbc.InputGroupText("buildings")
                ])
            ], width=6),
            dbc.Col([
                dbc.Label("Time Horizon"),
                dbc.InputGroup([
                    dbc.Input(id="time-horizon", type="number", value=96, min=24, max=672),
                    dbc.InputGroupText("intervals")
                ])
            ], width=6)
        ], className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Label("Simulation Scenarios"),
                dbc.InputGroup([
                    dbc.Input(id="num-scenarios", type="number", value=20, min=5, max=100),
                    dbc.InputGroupText("scenarios")
                ])
            ], width=6),
            dbc.Col([
                dbc.Label("Rapid Evaluations"),
                dbc.InputGroup([
                    dbc.Input(id="rapid-evaluations", type="number", value=1000, min=0, max=10000),
                    dbc.InputGroupText("evals")
                ])
            ], width=6)
        ], className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Label("Analysis Options"),
                dbc.Checklist([
                    {"label": "P2P Trading Comparison", "value": "p2p"},
                    {"label": "Train Surrogate Model", "value": "surrogate"},
                    {"label": "Sensitivity Analysis", "value": "sensitivity"},
                    {"label": "Export Detailed Results", "value": "detailed"}
                ], value=["p2p", "surrogate"], id="analysis-options")
            ])
        ])
    ])


def create_tariff_config_panel():
    return dbc.Form([
        dbc.Row([
            dbc.Col([
                dbc.Label("Tariff Types to Include"),
                dbc.Checklist([
                    {"label": "Time-of-Use (ToU)", "value": "tou"},
                    {"label": "Critical Peak Pricing (CPP)", "value": "cpp"},
                    {"label": "Real-Time Pricing (RTP)", "value": "rtp"},
                    {"label": "Emergency Demand Response (EDR)", "value": "edr"}
                ], value=["tou", "cpp", "rtp"], id="tariff-types")
            ], width=6),
            
            dbc.Col([
                dbc.Label("Price Ranges"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Off-Peak (€/kWh)", size="sm"),
                        dbc.Input(type="number", value=0.08, step=0.01, id="off-peak-price")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("On-Peak (€/kWh)", size="sm"),
                        dbc.Input(type="number", value=0.25, step=0.01, id="on-peak-price")
                    ], width=6)
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Export Ratio", size="sm"),
                        dbc.Input(type="number", value=0.4, step=0.1, min=0, max=1, id="export-ratio")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("Volatility", size="sm"),
                        dbc.Input(type="number", value=0.05, step=0.01, id="price-volatility")
                    ], width=6)
                ], className="mt-2")
            ], width=6)
        ])
    ])


def create_p2p_config_panel():
    return dbc.Form([
        dbc.Row([
            dbc.Col([
                dbc.Label("Trading Efficiency"),
                dbc.InputGroup([
                    dbc.Input(type="number", value=95, min=50, max=100, id="trading-efficiency"),
                    dbc.InputGroupText("%")
                ])
            ], width=6),
            dbc.Col([
                dbc.Label("Community Spread"),
                dbc.InputGroup([
                    dbc.Input(type="number", value=0.5, min=0, max=1, step=0.1, id="community-spread"),
                    dbc.InputGroupText("ratio")
                ])
            ], width=6)
        ], className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Label("Trading Network"),
                dbc.RadioItems([
                    {"label": "Full Network (all-to-all)", "value": "full"},
                    {"label": "Local Network (neighbors)", "value": "local"},
                    {"label": "Hub Network (central trading)", "value": "hub"}
                ], value="full", id="network-topology")
            ])
        ])
    ])


def create_results_overview_tab(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation results available. Please run a simulation first.", color="info")
    
    scenario_results = simulation_data.get('scenario_results', {})
    successful_scenarios = {k: v for k, v in scenario_results.items() if v.get('status') == 'success'}
    
    if not successful_scenarios:
        return dbc.Alert("No successful scenarios found.", color="warning")
    
    p2p_scenarios = {k: v for k, v in successful_scenarios.items() if v.get('with_p2p', False)}
    no_p2p_scenarios = {k: v for k, v in successful_scenarios.items() if not v.get('with_p2p', True)}
    
    summary_cards = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(len(successful_scenarios), className="text-primary"),
                    html.P("Successful Scenarios", className="mb-0")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(f"{len(p2p_scenarios)}", className="text-success"),
                    html.P("With P2P Trading", className="mb-0")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(f"{np.mean([v['total_cost'] for v in successful_scenarios.values()]):.2f}€", className="text-warning"),
                    html.P("Average Cost", className="mb-0")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(f"{np.mean([v['fairness'] for v in successful_scenarios.values()]):.3f}", className="text-info"),
                    html.P("Average Fairness", className="mb-0")
                ])
            ])
        ], width=3)
    ], className="mb-4")
    
    rankings = simulation_data.get('rankings', [])
    top_scenarios = rankings[:5] if rankings else []
    
    rankings_table = dash_table.DataTable(
        data=[{"Rank": i+1, "Scenario": name, "Score": f"{score:.3f}"} 
              for i, (name, score) in enumerate(top_scenarios)],
        columns=[{"name": "Rank", "id": "Rank"}, 
                {"name": "Scenario", "id": "Scenario"}, 
                {"name": "Score", "id": "Score"}],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'}
    )
    
    return html.Div([
        summary_cards,
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Top 5 Scenarios"),
                    dbc.CardBody([rankings_table])
                ])
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Performance Summary"),
                    dbc.CardBody([
                        create_performance_summary_chart(successful_scenarios)
                    ])
                ])
            ], width=6)
        ])
    ])


def create_performance_summary_chart(scenarios_data):
    costs = [result['total_cost'] for result in scenarios_data.values()]
    fairness = [result['fairness'] for result in scenarios_data.values()]
    names = list(scenarios_data.keys())
    p2p_status = ['P2P' if result.get('with_p2p', False) else 'No P2P' 
                  for result in scenarios_data.values()]
    
    fig = px.scatter(
        x=costs, y=fairness, color=p2p_status, hover_name=names,
        title="Cost vs Fairness Performance",
        labels={'x': 'Total Cost (€)', 'y': 'Fairness (CoV)'},
        color_discrete_map={'P2P': '#28a745', 'No P2P': '#dc3545'}
    )
    
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
    
    return dcc.Graph(figure=fig)


def create_interactive_analysis_tab(simulation_data):
    if not simulation_data:
        return dbc.Alert("No simulation results available.", color="info")
    
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Interactive Analysis Controls"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Analysis Type"),
                                dcc.Dropdown(
                                    options=[
                                        {"label": "Cost Comparison", "value": "cost"},
                                        {"label": "Fairness Analysis", "value": "fairness"},
                                        {"label": "Energy Flows", "value": "energy"},
                                        {"label": "P2P Benefits", "value": "p2p"}
                                    ],
                                    value="cost",
                                    id="analysis-type"
                                )
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Chart Type"),
                                dcc.Dropdown(
                                    options=[
                                        {"label": "Bar Chart", "value": "bar"},
                                        {"label": "Scatter Plot", "value": "scatter"},
                                        {"label": "Box Plot", "value": "box"},
                                        {"label": "Heatmap", "value": "heatmap"}
                                    ],
                                    value="bar",
                                    id="chart-type"
                                )
                            ], width=6)
                        ])
                    ])
                ])
            ], width=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Filters"),
                    dbc.CardBody([
                        dbc.Checklist(
                            options=[
                                {"label": "Show P2P Scenarios", "value": "p2p"},
                                {"label": "Show Non-P2P Scenarios", "value": "no_p2p"},
                                {"label": "Include ToU", "value": "tou"},
                                {"label": "Include RTP", "value": "rtp"}
                            ],
                            value=["p2p", "no_p2p"],
                            id="scenario-filters"
                        )
                    ])
                ])
            ], width=8)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="interactive-analysis-chart", style={"height": "600px"})
            ])
        ])
    ])


def create_detailed_scenario_view():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Scenario Details"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Select Scenario"),
                                dcc.Dropdown(id="detailed-scenario-selector")
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Select Building"),
                                dcc.Dropdown(id="detailed-building-selector")
                            ], width=6)
                        ]),
                        
                        dbc.Tabs([
                            dbc.Tab(label="Energy Flows", tab_id="flows"),
                            dbc.Tab(label="Cost Breakdown", tab_id="costs"),
                            dbc.Tab(label="Optimization Results", tab_id="optimization")
                        ], id="detail-tabs", active_tab="flows"),
                        
                        html.Div(id="detailed-content", className="mt-4")
                    ])
                ])
            ])
        ])
    ])


def create_export_controls():
    return dbc.Card([
        dbc.CardHeader("Export & Download"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Export Format"),
                    dbc.RadioItems([
                        {"label": "JSON", "value": "json"},
                        {"label": "CSV", "value": "csv"},
                        {"label": "Excel", "value": "xlsx"},
                        {"label": "PDF Report", "value": "pdf"}
                    ], value="json", id="export-format")
                ], width=6),
                dbc.Col([
                    dbc.Label("Include"),
                    dbc.Checklist([
                        {"label": "Raw Results", "value": "raw"},
                        {"label": "Summary Statistics", "value": "summary"},
                        {"label": "Charts", "value": "charts"},
                        {"label": "Configuration", "value": "config"}
                    ], value=["raw", "summary"], id="export-options")
                ], width=6)
            ]),
            dbc.Button("Download", id="download-button", color="success", className="w-100 mt-3")
        ])
    ])