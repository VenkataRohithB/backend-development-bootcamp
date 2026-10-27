# Campus Canteen API

`functions.py` already does all the database work. In class we write `main.py`,
which turns those functions into FastAPI endpoints.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run (after creating main.py)

```bash
uvicorn main:app --reload --port 8001
```

Then open http://127.0.0.1:8001/docs to see Swagger UI.

## Files

- `functions.py`: menu, cart and order functions (plain Python + sqlite3)
- `canteen.db`: the SQLite database, with 20 menu items, an empty cart and no orders
- `requirements.txt`: dependencies
