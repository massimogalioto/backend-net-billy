# Base image con Python
FROM python:3.10-slim

# Imposta la directory di lavoro
WORKDIR /app

# 🆕 Installa Tesseract, lingua italiana e strumenti OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-ita poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copia tutti i file nel container
COPY . .

# Installa le dipendenze Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Espone la porta su cui gira FastAPI
EXPOSE 8080

# Comando per avviare l'app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
