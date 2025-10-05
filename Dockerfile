FROM python:3.12-alpine

# Устанавливаем Poetry
RUN pip install poetry

# Настраиваем рабочую директорию
WORKDIR /app

# Копируем pyproject.toml и poetry.lock
COPY pyproject.toml poetry.lock* /app/

# Устанавливаем зависимости без виртуального окружения (в системный Python)
RUN poetry config virtualenvs.create false \
  && poetry install --no-root --no-interaction --no-ansi

# Копируем остальной код
COPY . .

# Команда по умолчанию
CMD ["poetry", "run", "python", "-m", "bot.main"]
