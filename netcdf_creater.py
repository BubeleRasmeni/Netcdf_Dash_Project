# Adjusting imports for completeness
import dash
from dash import dcc, html, Input, Output, dash_table, State, callback_context
import pandas as pd
import io
import base64
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import xarray as xr
import json

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],meta_tags=[{'name': 'viewport',
                            'content': 'width=device-width, initial-scale=1.0'}])
# Define a dictionary to store the netCDF data in memory
netcdf_store = {}

# Default Global Attributes
default_global_attrs = {
    "title": "Dataset Title",
    "institution": "Institution Name",
    "source": "Data Source",
    "history": "Creation Date",
    "references": "Reference Information",
    "comment": "Additional Comments",
}

# Default Local Attributes for example variables
default_local_attrs = {
    "temperature": {
        "units": "Celsius",
        "long_name": "Temperature",
        "standard_name": "air_temperature",
        "missing_value": -999.99,
        "valid_range": [0, 50]
    },
    "salinity": {
        "units": "psu",
        "long_name": "Salinity",
        "standard_name": "sea_water_salinity",
        "missing_value": -999.99,
        "valid_range": [30, 38]
    },
}

# Convert dictionaries to string representation for TextArea
global_attrs_str = str(default_global_attrs).replace("'", '"')
local_attrs_str = str(default_local_attrs).replace("'", '"')

app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H1("MIMS Flatfile to netCDF Converter"),
                width={"size": 12, "offset": 0},
                className="text-center py-3 bg-light mb-4 shadow-sm",
            )
        ),
        dbc.Row(
            [
                dbc.Col(
                    [  # Sidebar
                        html.P(
                            "This app converts flatfiles to the netCDF format. Supported file formats include CSV and xls.",
                            className="text-muted",
                        ),
                        dcc.Upload(
                            id="upload-data",
                            children=html.Div(
                                ["Drag and Drop or ", html.A("Select Files")]
                            ),
                            className="mb-3",
                            multiple=True,
                        ),
                        dcc.Dropdown(
                            id="coordinates-dropdown",
                            multi=True,
                            placeholder="Select coordinates...",
                            className="mb-3",
                        ),
                        dcc.Dropdown(
                            id="variables-dropdown",
                            multi=True,
                            placeholder="Select variables...",
                        ),
                        html.Button(
                            "Create netCDF", id="create-netcdf-button", className="mb-1"
                        ),
                        html.Div(
                            id="error-message", className="text-danger"
                        ),  # Placeholder for error messages
                    ],
                    md=3,
                    className="bg-light border-end pe-4 shadow-sm"
                ),
            dbc.Col(
                [  # Main content area for DataTable, moved to the right
                dbc.Row([html.Div(id="output-data-upload",style={'width': '100%', 'height': 200,"margin": "20px"})]),  
                dbc.Row([                
                        dbc.Col([html.H5("Global Attributes"),
                        dcc.Textarea(
                            id='global-attributes',
                            placeholder=f'{global_attrs_str}',
                            style={'width': '100%', 'height': 300},
                        ),],md=6),
                        dbc.Col([
                    html.H5("Variable Attributes"),
                        dcc.Textarea(
                            id='local-attributes',
                            #value=local_attrs_str,
                            placeholder=f'{local_attrs_str}',
                            style={'width': '100%', 'height': 300},
                        ),
                ],md=6),
                        
                        ])

            ], md=8, className="ps-12 shadow-sm",style={"margin": "20px"}
            ),
            ],
            className="g-10",style={'width': '100%', 'height': 900}
        ),
        dbc.Row([dcc.Download(id="download-netcdf")]),
    ],
    fluid=True,
    className="py-3",
    style={"margin": "20px",'width': '100%', 'height': 900}  # Adds 20px margin on all sides
)


@app.callback(
    [
        Output("coordinates-dropdown", "options"),
        Output("variables-dropdown", "options"),
        Output("output-data-upload", "children"),
        Output("error-message", "children"),  # To display error messages
    ],
    [Input("upload-data", "contents")],
    [State("upload-data", "filename")],
)
def update_output(contents, filename):
    if contents is None:
        raise PreventUpdate
    try:
        content_type, content_string = contents[0].split(",")
        decoded = base64.b64decode(content_string)
        if "csv" in filename[0]:
            df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        elif "xls" in filename[0]:
            df = pd.read_excel(io.BytesIO(decoded))
        else:
            return [], [], None, "Unsupported file type!"

        coordinate_options = [{"label": col, "value": col} for col in df.columns]
        variable_options = [{"label": col, "value": col} for col in df.columns]

        table = dash_table.DataTable(
            df.to_dict("records"),
            [{"name": i, "id": i} for i in df.columns],
            page_size=5,style_table={'overflowX': 'auto'},
        )
        return coordinate_options, variable_options, table, ""
    except Exception as e:
        return [], [], None, f"Error processing file: {str(e)}"


import json

@app.callback(
    Output("download-netcdf", "data"),
    [Input("create-netcdf-button", "n_clicks")],
    [
        State("coordinates-dropdown", "value"),
        State("variables-dropdown", "value"),
        State("upload-data", "contents"),
        State("upload-data", "filename"),
        State("global-attributes", "value"),  # Get global attributes
        State("local-attributes", "value"),   # Get local attributes
    ],
    prevent_initial_call=True,
)
def create_netcdf(n_clicks, coord_values, var_values, contents, filename, global_attrs, local_attrs):
    if n_clicks is None or contents is None:
        raise PreventUpdate

    content_type, content_string = contents[0].split(",")
    decoded = base64.b64decode(content_string)

    try:
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8"))) if "csv" in filename[0] else pd.read_excel(io.BytesIO(decoded))
        
        coordinates = {coord: df[coord].values for coord in coord_values}
        unique_counts = {key: len(set(values)) for key, values in coordinates.items()}
        shape = tuple(unique_counts.values())

        ds = xr.Dataset(
            coords={coord: list(set(values)) for coord, values in coordinates.items()},
            data_vars={
                var: (
                    list(coordinates.keys()),
                    df[var].values.reshape(shape) if len(shape) > 1 else df[var].values
                )
                for var in var_values
            },
        )

        # Parse and add global attributes
         # Handling netCDF attributes
        if global_attrs:
            try:
                global_attr_dict = json.loads(global_attrs)
                ds.attrs.update(global_attr_dict)
                print("Global attributes added:", ds.attrs)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON format in Global Attributes: {e}")
                return None, f"Invalid JSON format in Global Attributes: {e}"

        if local_attrs:
            try:
                local_attr_dict = json.loads(local_attrs)
                for var in var_values:  # Ensure we are only updating selected variables
                    if var in local_attr_dict and var in ds.data_vars:
                        ds[var].attrs.update(local_attr_dict[var])
                        print(f"Attributes for {var} updated:", ds[var].attrs)
                print("Local attributes added")
            except json.JSONDecodeError as e:
                print(f"Invalid JSON format in Local Attributes: {e}")
                return None, f"Invalid JSON format in Local Attributes: {e}"

        print(ds.attrs)
        netcdf_data = io.BytesIO()
        ds.to_netcdf(io.BytesIO)
        netcdf_data.seek(0)
        netcdf_store["my_netcdf"] = netcdf_data.read()

        return dcc.send_bytes(netcdf_store["my_netcdf"], f"{filename[0].split('.')[0]}_converted.nc")
    except Exception as e:
        return dcc.send_data(f"Failed to create netCDF file: {str(e)}")

if __name__ == "__main__":
    app.run_server(debug=True)
