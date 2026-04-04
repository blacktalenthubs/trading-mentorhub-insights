worker: cd api && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
web: streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
