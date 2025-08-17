FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install --upgrade pip && pip install uv

# Copy project files
COPY main.py .
COPY feeds.yaml .
COPY pyproject.toml .
COPY uv.lock .

# Sync/install dependencies using uv (it creates venv in .venv automatically)
RUN uv sync

# Run the MCP server using uv
CMD ["uv", "run", "main.py"]
