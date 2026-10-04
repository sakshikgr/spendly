import os

# app.py refuses to import without SECRET_KEY outside `python app.py`.
os.environ.setdefault("SECRET_KEY", "test-secret")
