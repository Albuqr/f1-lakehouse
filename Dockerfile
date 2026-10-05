FROM python:3.12-slim
WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY analysis.py dashboard.py ./
COPY data/ ./data/
COPY .streamlit/ ./.streamlit/
EXPOSE 8501
CMD ["streamlit", "run", "dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]