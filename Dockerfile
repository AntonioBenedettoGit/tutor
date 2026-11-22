# Dockerfile per Hugging Face Spaces (SDK = Docker).
# HF espone l'app su PORT (default 7860) e fornisce SPACE_HOST.
FROM python:3.11-slim

WORKDIR /app

# le dipendenze per prime per sfruttare la cache dei layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# tutto il progetto (bot.py, tutor/, data/kb.json, app.py)
COPY . .

# HF vuole che qualcosa ascolti su questa porta
EXPOSE 7860

# entrypoint: lo Space esegue app.py (modalità webhook se c'è SPACE_HOST)
CMD ["python", "app.py"]
