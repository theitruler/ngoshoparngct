FROM python:3.11-slim

# Prevent Python from buffering logs (important for Coolify)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Coolify injects PORT automatically, but we set a default
ENV HOST=0.0.0.0
ENV PORT=3000

EXPOSE 3000

# Run Flask app via Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "app:app"]