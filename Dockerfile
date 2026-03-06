FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway sets $PORT)
EXPOSE 8501

# Run Streamlit
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
