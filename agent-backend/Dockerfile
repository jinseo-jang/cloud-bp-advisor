FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY . .
ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port", "8000", "--server.address", "0.0.0.0"]
