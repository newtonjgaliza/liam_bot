FROM python:3.12-slim

# Evita que o Python gere arquivos .pyc e faz o stdout sair sem buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências de sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código-fonte
COPY . .

# Cria diretórios de armazenamento
RUN mkdir -p /app/data /app/uploads

# Porta padrão para health check na Render
EXPOSE 8080

CMD ["python", "-m", "src.main"]
