# Developer Setup

## Python

The backend package requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

For BI exports:

```bash
python -m pip install -e ".[dev,bi]"
python -m build
```

The BI extra installs Parquet support through `pyarrow` and Tableau Hyper support through `tableauhyperapi`.

## Node.js

The analytics dashboard is a Next.js app in `frontend/`.

```bash
cd frontend
npm install
npm run lint
npm run build
```

The package declares Node.js `>=22.12 <25` and npm `>=10`.

## Local Development

Run the FastAPI server first:

```bash
python main.py web
```

Then run the dashboard:

```bash
cd frontend
npm run dev
```

The dashboard proxies `/backend/*` to `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.
