# CSVAgent

CSVAgent is a production-ready Python CLI for inspecting CSV files and generating interactive Plotly charts.

## Features

- List CSV files in a directory with row count, column count, and file size
- Inspect columns with pandas dtypes, semantic types, and sample values
- Generate interactive charts for numeric and categorical columns
- Create correlation heatmaps for numeric data
- Persist configuration in JSON:
  - default CSV directory
  - preferred visualization defaults
  - recently opened files
  - saved chart configurations

## Project Structure

```text
.
├── csvagent
│   ├── __init__.py
│   ├── cli.py
│   ├── config_manager.py
│   ├── csv_reader.py
│   ├── data_analyzer.py
│   ├── exceptions.py
│   ├── file_manager.py
│   └── visualizer.py
├── main.py
├── README.md
└── requirements.txt
```

## Installation

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

All commands run through `main.py`:

```bash
python main.py --help
```

### List CSV Files

List CSV files in the current directory:

```bash
python main.py list-files
```

List CSV files in a specific directory recursively:

```bash
python main.py list-files ./data --recursive
```

### Inspect Columns

Show column names, dtypes, and sample values:

```bash
python main.py columns ./data/sales.csv --samples 5
```

### Generate Charts

If you provide `--column` without `--chart-type`, CSVAgent uses your saved default chart preference for that column type.

Histogram:

```bash
python main.py plot ./data/sales.csv --chart-type histogram --column revenue
```

Line plot:

```bash
python main.py plot ./data/sales.csv --chart-type line --x order_date --y revenue
```

Box plot:

```bash
python main.py plot ./data/sales.csv --chart-type box --column revenue
```

Categorical bar chart:

```bash
python main.py plot ./data/sales.csv --chart-type bar --column region
```

Pie chart:

```bash
python main.py plot ./data/sales.csv --chart-type pie --column region
```

Save a reusable chart configuration:

```bash
python main.py plot ./data/sales.csv --chart-type line --x order_date --y revenue --save-config revenue-trend
```

Reuse a saved chart configuration:

```bash
python main.py plot --use-config revenue-trend
```

### Correlation Heatmap

Use all numeric columns:

```bash
python main.py correlation ./data/sales.csv
```

Use specific numeric columns:

```bash
python main.py correlation ./data/sales.csv --columns revenue,profit,units_sold
```

Save and reuse a heatmap configuration:

```bash
python main.py correlation ./data/sales.csv --columns revenue,profit --save-config finance-heatmap
python main.py correlation --use-config finance-heatmap
```

### Configuration Commands

Set a default CSV directory:

```bash
python main.py config set-default-dir ./data
```

Update default visualization settings:

```bash
python main.py config set-visual \
  --numeric-default histogram \
  --categorical-default bar \
  --colors "#1f77b4,#ff7f0e,#2ca02c" \
  --width 1200 \
  --height 700 \
  --template plotly_white
```

Show current configuration:

```bash
python main.py config show
```

Show recent files:

```bash
python main.py config recent
```

List saved chart configurations:

```bash
python main.py config saved-charts
```

Inspect a saved chart configuration:

```bash
python main.py config show-chart revenue-trend
```

Delete a saved chart configuration:

```bash
python main.py config delete-chart revenue-trend
```

## Configuration Storage

By default, configuration is stored in:

```text
~/.csvagent/config.json
```

If that location is not writable, CSVAgent falls back to:

```text
./.csvagent/config.json
```

You can override this path per command:

```bash
python main.py --config-path ./config/local-config.json config show
```

Or via environment variable:

```bash
export CSVAGENT_CONFIG_PATH=./config/local-config.json
```

## Output

- Generated charts are saved as HTML files in `./charts/` by default
- Plotly output is interactive and can be opened in any browser
- Recently opened files and saved chart definitions are persisted automatically
