"""
Data analysis tool — gives Connor (DataAgent) read/analyse/chart access to
CSV, Excel, and JSON data files on the local machine.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GENERATED_DOCS_DIR

_MORGAN_DIR = os.path.join(GENERATED_DOCS_DIR, "Connor")

DEFINITIONS = [
    {
        "name":        "data_list_files",
        "description": (
            "Find CSV, Excel (.xlsx/.xls), and JSON data files in a directory. "
            "Use this first to discover what data is available before reading."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Absolute path to the directory to search (recursive).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name":        "data_read",
        "description": (
            "Read a CSV, Excel, or JSON file and return a preview of the first rows, "
            "column names, dtypes, and shape. Large files are previewed (first 50 rows). "
            "Use this to understand the structure before analysing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Absolute path to the file (CSV, .xlsx, .xls, or .json).",
                },
                "sheet": {
                    "type":        "string",
                    "description": "Sheet name for Excel files. Defaults to the first sheet.",
                },
                "rows": {
                    "type":        "integer",
                    "description": "Number of preview rows to return. Default 20.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name":        "data_describe",
        "description": (
            "Return summary statistics for a data file: count, mean, std, min, "
            "25th/50th/75th percentile, max for numeric columns. "
            "Also reports null counts and unique value counts per column."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string",  "description": "Absolute path to the CSV/Excel/JSON file."},
                "sheet": {"type": "string",  "description": "Sheet name for Excel files (optional)."},
            },
            "required": ["path"],
        },
    },
    {
        "name":        "data_query",
        "description": (
            "Run a pandas query/filter on a data file and return results. "
            "Supports: filter (pandas query string e.g. 'Amount > 1000 and Status == \"Paid\"'), "
            "groupby + aggregate (e.g. group_by='Category', agg='sum'), "
            "sort (e.g. sort_by='Amount', ascending=False), "
            "and column selection (e.g. columns=['Name', 'Amount', 'Date']). "
            "Combine them freely. Returns up to 200 rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",       "description": "Absolute path to the file."},
                "sheet":     {"type": "string",       "description": "Sheet name for Excel (optional)."},
                "filter":    {"type": "string",       "description": "Pandas query string to filter rows."},
                "columns":   {"type": "array",        "items": {"type": "string"}, "description": "Column subset to return."},
                "group_by":  {"type": "string",       "description": "Column name to group by."},
                "agg":       {"type": "string",       "description": "Aggregation: sum, mean, count, max, min (default sum)."},
                "sort_by":   {"type": "string",       "description": "Column to sort by."},
                "ascending": {"type": "boolean",      "description": "Sort order. Default True."},
                "limit":     {"type": "integer",      "description": "Max rows to return. Default 200."},
            },
            "required": ["path"],
        },
    },
    {
        "name":        "data_chart",
        "description": (
            "Generate a chart from a data file and save it as a PNG to Connor's output folder. "
            "Returns the saved file path. "
            "Chart types: bar, line, pie, scatter, hist. "
            "Specify x and y column names, or just y for histograms/bar of index."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string", "description": "Absolute path to the data file."},
                "sheet":      {"type": "string", "description": "Sheet name for Excel (optional)."},
                "chart_type": {
                    "type":        "string",
                    "enum":        ["bar", "line", "pie", "scatter", "hist"],
                    "description": "Type of chart to generate.",
                },
                "x":          {"type": "string", "description": "Column name for the x-axis (or category labels for bar/pie)."},
                "y":          {"type": "string", "description": "Column name for the y-axis (or values for bar/pie/hist)."},
                "title":      {"type": "string", "description": "Chart title."},
                "filter":     {"type": "string", "description": "Optional pandas query string to filter data before charting."},
                "filename":   {"type": "string", "description": "Output filename (without extension). Defaults to chart_{timestamp}."},
            },
            "required": ["path", "chart_type", "y"],
        },
    },
    {
        "name":        "data_write",
        "description": (
            "Write a pandas-queryable result to a CSV or Excel file. "
            "Useful for saving processed/filtered data or analysis outputs. "
            "Specify the source file, a filter/query, and the output path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path":  {"type": "string", "description": "Absolute path to the source data file."},
                "output_path":  {"type": "string", "description": "Absolute path to write the result to (CSV or .xlsx)."},
                "sheet":        {"type": "string", "description": "Sheet name for Excel source (optional)."},
                "filter":       {"type": "string", "description": "Pandas query string to filter rows before writing (optional)."},
                "columns":      {"type": "array",  "items": {"type": "string"}, "description": "Column subset to write (optional)."},
                "group_by":     {"type": "string", "description": "Group by this column before writing (optional)."},
                "agg":          {"type": "string", "description": "Aggregation to apply when grouping: sum, mean, count, max, min."},
            },
            "required": ["source_path", "output_path"],
        },
    },
]


def _load_df(path: str, sheet: str | None = None):
    """Load a CSV, Excel, or JSON file into a pandas DataFrame."""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0)
    if ext == ".json":
        return pd.read_json(path)
    return pd.read_csv(path, encoding="utf-8", errors="replace")


def _apply_query(df, inputs: dict):
    """Apply filter, column select, groupby, sort from inputs dict."""
    import pandas as pd

    # Filter
    filt = inputs.get("filter")
    if filt:
        try:
            df = df.query(filt)
        except Exception as e:
            return None, f"Filter error: {e}"

    # Column select
    cols = inputs.get("columns")
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            return None, f"Columns not found: {missing}. Available: {list(df.columns)}"
        df = df[cols]

    # Group + aggregate
    group_by = inputs.get("group_by")
    if group_by:
        if group_by not in df.columns:
            return None, f"group_by column '{group_by}' not found. Available: {list(df.columns)}"
        agg = inputs.get("agg", "sum")
        numeric_df = df.select_dtypes(include="number")
        if numeric_df.empty:
            return None, "No numeric columns to aggregate."
        df = getattr(df.groupby(group_by)[numeric_df.columns.tolist()], agg)()
        df = df.reset_index()

    # Sort
    sort_by = inputs.get("sort_by")
    if sort_by:
        if sort_by not in df.columns:
            return None, f"sort_by column '{sort_by}' not found."
        df = df.sort_values(sort_by, ascending=inputs.get("ascending", True))

    return df, None


def handle(name: str, inputs: dict) -> str:
    try:
        import pandas as pd
    except ImportError:
        return "pandas is not installed. Run: pip install pandas openpyxl"

    # ── data_list_files ───────────────────────────────────────────────────────
    if name == "data_list_files":
        path = inputs.get("path", "")
        if not os.path.isdir(path):
            return f"Directory not found: {path}"
        exts = {".csv", ".xlsx", ".xls", ".json"}
        found = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
            for f in files:
                if os.path.splitext(f)[1].lower() in exts:
                    full = os.path.join(root, f)
                    size = os.path.getsize(full)
                    rel  = os.path.relpath(full, path)
                    found.append(f"{rel}  ({size:,} bytes)")
        if not found:
            return f"No CSV/Excel/JSON files found in {path}"
        return f"Found {len(found)} data file(s) in {path}:\n\n" + "\n".join(found)

    # ── data_read ─────────────────────────────────────────────────────────────
    if name == "data_read":
        path = inputs.get("path", "")
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            df    = _load_df(path, inputs.get("sheet"))
            rows  = inputs.get("rows", 20)
            lines = [
                f"File: {path}",
                f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns",
                "",
                "Columns:",
            ]
            for col in df.columns:
                null_count = int(df[col].isnull().sum())
                lines.append(f"  {col!r:40s}  {str(df[col].dtype):12s}  {null_count} nulls")
            lines += ["", f"Preview (first {min(rows, len(df))} rows):", ""]
            lines.append(df.head(rows).to_string(index=True))
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading {path}: {e}"

    # ── data_describe ─────────────────────────────────────────────────────────
    if name == "data_describe":
        path = inputs.get("path", "")
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            df = _load_df(path, inputs.get("sheet"))
            lines = [
                f"File: {path}",
                f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns",
                "",
                "Null counts per column:",
            ]
            for col in df.columns:
                n = int(df[col].isnull().sum())
                pct = n / len(df) * 100 if len(df) else 0
                lines.append(f"  {col!r}: {n} nulls ({pct:.1f}%)")

            lines += ["", "Unique value counts (non-numeric columns):"]
            for col in df.select_dtypes(exclude="number").columns:
                u = df[col].nunique()
                lines.append(f"  {col!r}: {u} unique values")

            numeric = df.describe()
            if not numeric.empty:
                lines += ["", "Numeric summary statistics:", ""]
                lines.append(numeric.to_string())

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing {path}: {e}"

    # ── data_query ────────────────────────────────────────────────────────────
    if name == "data_query":
        path = inputs.get("path", "")
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            df = _load_df(path, inputs.get("sheet"))
            df, err = _apply_query(df, inputs)
            if err:
                return err
            limit = inputs.get("limit", 200)
            total = len(df)
            df    = df.head(limit)
            result = df.to_string(index=True)
            if total > limit:
                result += f"\n\n…showing {limit} of {total:,} rows"
            else:
                result += f"\n\n{total:,} row(s)"
            return result
        except Exception as e:
            return f"Error querying {path}: {e}"

    # ── data_chart ────────────────────────────────────────────────────────────
    if name == "data_chart":
        try:
            import matplotlib
            matplotlib.use("Agg")  # non-interactive backend — no display needed
            import matplotlib.pyplot as plt
        except ImportError:
            return "matplotlib is not installed. Run: pip install matplotlib"

        path = inputs.get("path", "")
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            df = _load_df(path, inputs.get("sheet"))

            filt = inputs.get("filter")
            if filt:
                df = df.query(filt)

            chart_type = inputs.get("chart_type", "bar")
            x          = inputs.get("x")
            y          = inputs.get("y")
            title      = inputs.get("title", f"{chart_type.title()} — {os.path.basename(path)}")

            if y not in df.columns:
                return f"Column '{y}' not found. Available: {list(df.columns)}"
            if x and x not in df.columns:
                return f"Column '{x}' not found. Available: {list(df.columns)}"

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.set_title(title)

            if chart_type == "bar":
                plot_data = df.set_index(x)[y] if x else df[y]
                plot_data.plot(kind="bar", ax=ax)
                ax.set_ylabel(y)
            elif chart_type == "line":
                plot_data = df.set_index(x)[y] if x else df[y]
                plot_data.plot(kind="line", ax=ax)
                ax.set_ylabel(y)
            elif chart_type == "pie":
                plot_data = df.set_index(x)[y] if x else df[y]
                plot_data.plot(kind="pie", ax=ax, autopct="%1.1f%%")
                ax.set_ylabel("")
            elif chart_type == "scatter":
                if not x:
                    return "scatter chart requires an 'x' column."
                ax.scatter(df[x], df[y])
                ax.set_xlabel(x)
                ax.set_ylabel(y)
            elif chart_type == "hist":
                df[y].plot(kind="hist", ax=ax, bins=20)
                ax.set_xlabel(y)

            plt.tight_layout()

            os.makedirs(_MORGAN_DIR, exist_ok=True)
            fname = inputs.get("filename") or f"chart_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
            out   = os.path.join(_MORGAN_DIR, f"{fname}.png")
            plt.savefig(out, dpi=150)
            plt.close(fig)
            return f"Chart saved: {out}"

        except Exception as e:
            return f"Error generating chart: {e}"

    # ── data_write ────────────────────────────────────────────────────────────
    if name == "data_write":
        src = inputs.get("source_path", "")
        dst = inputs.get("output_path", "")
        if not os.path.exists(src):
            return f"Source file not found: {src}"
        try:
            df = _load_df(src, inputs.get("sheet"))
            df, err = _apply_query(df, inputs)
            if err:
                return err

            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            ext = os.path.splitext(dst)[1].lower()
            if ext in (".xlsx", ".xls"):
                try:
                    df.to_excel(dst, index=False)
                except ImportError:
                    return "openpyxl is not installed. Run: pip install openpyxl"
            else:
                df.to_csv(dst, index=False)

            return f"Written: {dst} ({len(df):,} rows × {df.shape[1]} columns)"
        except Exception as e:
            return f"Error writing {dst}: {e}"

    return f"Unknown data tool: {name}"
