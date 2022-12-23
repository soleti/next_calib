#!/usr/bin/env python3

"""
Web-based display for NEXT calibration runs
"""

import sys
from io import StringIO
import fire
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import h5py
from datetime import datetime
import os
import visdcc
import time
import ciso8601
import dash_bootstrap_components as dbc
from dash import no_update
from plotly.subplots import make_subplots

from dash_extensions.enrich import Input, Output, State, DashProxy, MultiplexerTransform
from dash import dcc, html

from invisible_cities.core.configure import configure
from invisible_cities.reco.corrections import read_maps
from krcal.map_builder.map_builder_functions import map_builder

app = DashProxy(
    __name__,
    prevent_initial_callbacks=True,
    transforms=[MultiplexerTransform()],
    external_stylesheets=[dbc.themes.JOURNAL],
    external_scripts=[
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.4/MathJax.js?config=TeX-MML-AM_CHTML",
    ],
    title="NEXT calibration display",
)

folder_dst = "/Users/roberto/next/new_calib/"
dst_file = "new_calib.h5"
configuration_filename = "config_LBphys.conf"
with open(configuration_filename, "r") as f:
    config = f.read()

server = app.server
app.layout = dbc.Container(
    fluid=True,
    style={
        "padding": "1.5em",
    },
    children=[
        html.Img(
            src='https://next.ific.uv.es/next/templates/rt_quasar_j15/images/logo/stylenext/logo.png',
            style={'height': '2.3em', "float":"left", "margin": "0.65em 0.6em 0 0"}
        ),
        html.H1("calibration display", style={"float":"left", "font-weight": "normal"}),
        dbc.Row([
            dbc.Col([
                dbc.Label("Input file: ", style={'display': 'inline-block'}),
                dcc.Input(
                    id="input-filename",
                    type="text",
                    style={
                        "margin": "0.5em",
                        "display": "inline-block"
                    },
                    value="new_calib.h5",
                    placeholder="enter input file path here...",
                    size=38,
                    readOnly=True,
                    debounce=True,
                ),
                dbc.Button("Load input file", id="button-load", color="info"),
                html.Br(),
                dcc.Loading(
                    children=[
                        dbc.Label("Start time: ", style={
                                  'display': 'inline-block'}),
                        dbc.Input(id="start-date-time",
                                  type="datetime-local",
                                  style={'width': '16em', 'display': 'inline-block', 'margin': '0.5em'}),
                        dbc.Label("End time: ", style={
                                  'display': 'inline-block'}),
                        dbc.Input(id="end-date-time",
                                  type="datetime-local",
                                  style={'width': '16em', 'display': 'inline-block', 'margin': '0.5em'}),
                    ]
                ),
                html.Br(),
                dbc.Button("Calibrate", id="button-calibrate", color="info"),
                dbc.Alert(
                    children=["File not found"],
                    id="alert-file-not-found",
                    is_open=False,
                    duration=4000,
                    color="primary",
                    style={"width": "50em", "margin": "0.5em 0.5em 0.5em 0"}
                ),
                dbc.Alert(
                    children=["Error"],
                    id="alert-error",
                    is_open=False,
                    duration=60000,
                    color="primary",
                    style={"width": "50em", "margin": "0.5em 0.5em 0.5em 0"}
                ),
                dcc.Interval(
                    id='interval-component',
                    interval=1*1000,  # in milliseconds
                    n_intervals=0
                ),
                dcc.Loading(
                    type="circle",
                    children=[
                        dcc.Graph(
                            id="calibration-figure",
                            clear_on_unhover=True,
                            figure=go.Figure(layout={
                                'xaxis': {"visible": False},
                                'yaxis': {"visible": False},
                            }),
                            config={
                                "toImageButtonOptions": {
                                    "format": "png",  # one of png, svg, jpeg, webp
                                    "height": 900,
                                    "width": 1200,
                                },
                                "displaylogo": False,
                            }
                        )
                    ]
                )
            ], width=8),
            dbc.Col([
                html.Div([
                    html.H3("Configuration", style={"font-weight":"normal"}),
                    dcc.Textarea(id='config',
                                 value=config,
                                 style={
                                    "width": "100%","height":"100%","font-family": "monospace"
                                 }),
                ], style={"height":"36vh", "margin-bottom":"3em"}),
                html.Div([
                    html.Div(id='javascriptLog'),
                    # visdcc.Run_js(id='javascriptLog', run=""),
                    html.H3("Log", style={"font-weight":"normal"}),
                    dcc.Textarea(id='live-update-text', readOnly=True, style={
                                "width": "100%","height":"100%","font-family": "monospace"}),
                    dbc.Button("Clear log", id="button-clears", color="info")
                ], style={"height":"36vh"})
            ], width=4)
        ])
    ]
)


my_stdout = StringIO()
sys.stdout = my_stdout
my_stderr = StringIO()
sys.stderr = my_stderr

@app.callback(
    [
        Output('live-update-text', 'value'),
        Output('javascriptLog', 'run')
    ],
    State('live-update-text', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_metrics(log, n):
    js_cmd = """
        var textarea = document.getElementById('live-update-text');
        textarea.scrollTop = textarea.scrollHeight;
    """
    if log:
        if log != my_stdout.getvalue()+my_stderr.getvalue():
            return log+my_stdout.getvalue()+my_stderr.getvalue(), js_cmd
    return my_stdout.getvalue()+my_stderr.getvalue(), js_cmd


@app.callback(
    [
        Output("alert-file-not-found", "is_open"),
        Output("alert-file-not-found", "children"),
        Output("start-date-time", "value"),
        Output("end-date-time", "value"),
    ],
    Input("button-load", "n_clicks"),
    State("input-filename", "value"),
)
def load_times(button_click, input_filename):
    if not input_filename:
        return (
            True,
            "You need to specify an input file"
        )

    try:
        data = h5py.File(input_filename, "r")
        times = data['DST']['Events']['time']
        start_time = datetime.fromtimestamp(
            min(times)).strftime('%Y-%m-%dT%H:%M:%S')
        end_time = datetime.fromtimestamp(
            max(times)).strftime('%Y-%m-%dT%H:%M:%S')
    except FileNotFoundError:
        print(input_filename, "not found")
        return (
            True,
            f"File {input_filename} not found",
            no_update, no_update
        )
    except IsADirectoryError:
        return no_update, False, no_update, no_update
    except OSError as err:
        return (
            True,
            f"File {input_filename} is not a valid file",
            no_update,
            no_update
        )

    return False, no_update, start_time, end_time


@app.callback(
    [
        Output("alert-file-not-found", "is_open"),
        Output("alert-file-not-found", "children"),
        Output("alert-error", "is_open"),
        Output("alert-error", "children"),
        Output("calibration-figure", "figure"),
    ],
    Input("button-calibrate", "n_clicks"),
    [
        State("config", "value"),
        State("input-filename", "value"),
        State("start-date-time", "value"),
        State("end-date-time", "value"),
    ]
)
def calibrate(button_click, config, input_filename, start_time, end_time):

    if not input_filename:
        return (
            True,
            "You need to specify an input file",
            no_update,
            no_update,
            no_update,
            no_update,
        )

    file_bootstrap = f"/Users/roberto/next/IC/invisible_cities/database/test_data/kr_emap_xy_100_100_r_6573_time.h5"
    ref_histo_file = f"{os.environ['ICARO']}/krcal/map_builder/reference_files/z_dst_LB_mean_ref.h5"

    output_maps_file = './'

    map_file_out = os.path.join(output_maps_file, 'map.h5')
    histo_file_out = os.path.join(output_maps_file, 'histos.h5')

    print('Input dst: ', input_filename)
    print('Output map file: ', map_file_out)
    print('Output histograms file: ', histo_file_out)

    ref_Z_histogram = dict(
        ref_histo_file=ref_histo_file,
        key_Z_histo='histo_Z_dst')

    print("START TIME", start_time)
    with open("config.conf","w") as f:
        f.write(config)

    config = configure('maps config.conf'.split())
    start_timestamp = time.mktime(
        ciso8601.parse_datetime(start_time).timetuple())
    end_timestamp = time.mktime(ciso8601.parse_datetime(end_time).timetuple())

    config.update(
        dict(
            time_start=start_timestamp,
            time_end=end_timestamp,
            nS1_eff_min=0.7,
            nS2_eff_min=0.7,
        )
    )
    print(os.getcwd())
    config.update(dict(folder=f"{os.getcwd()}/",
                       file_in=input_filename,
                       file_out_map=map_file_out,
                       file_out_hists=histo_file_out,
                       ref_Z_histogram=ref_Z_histogram,
                       run_number=1,
                       file_bootstrap_map=file_bootstrap))

    try:
        map_builder(config.as_namespace)
        final_map = read_maps(map_file_out)
    except ValueError as err:
        print(err, input_filename)
        return True, f"Impossible to open {input_filename} ", False, no_update, no_update, no_update
    except Exception as err:
        return False, no_update, True, str(err), no_update, no_update

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("E0", "E0 uncertainty", "Lifetime", "Lifetime uncertainty"),
        horizontal_spacing=0.175,
        vertical_spacing=0.1,
        shared_yaxes=True,
        shared_xaxes=True,
    )

    fig.update_layout(
        width=800,
        height=700,
        margin=dict(t=10),
        plot_bgcolor='rgb(255,255,255)'
    )

    for r in range(2):
        for c in range(2):
            if r == 1:
                fig.update_xaxes(title_text="x [bin number]", row=r+1, col=c+1)
            if c == 0:
                fig.update_yaxes(title_text="y [bin number]", row=r+1, col=c+1)

    fig.add_trace(
        go.Heatmap(
            z=final_map.e0,
            colorscale='viridis', colorbar=dict(x=0.42, len=0.48, y=0.775),
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Heatmap(
            z=final_map.e0u,
            colorbar=dict(len=0.47, y=0.775),
        ),
        row=1, col=2
    )
    fig.add_trace(
        go.Heatmap(
            z=final_map.lt,
            colorscale='viridis', colorbar=dict(x=0.42, len=0.48, y=0.22),
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Heatmap(
            z=final_map.ltu,
            colorbar=dict(len=0.48, y=0.22),
        ),
        row=2, col=2
    )


    return False, no_update, no_update, no_update, fig


if __name__ == "__main__":
    fire.Fire(app.run_server)
