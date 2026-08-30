SHELL := /bin/bash
.DEFAULT_GOAL := help

POETRY ?= poetry
RUN := $(POETRY) run
IMAGE ?= coupon-scraper:dev

.PHONY: help
help:  ## Показать это сообщение
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# Настройка окружения

.PHONY: install
install:  ## Установить зависимости и git-хуки
	$(POETRY) install
	$(RUN) pre-commit install

.PHONY: env
env:  ## Создать .env из примера, если его ещё нет
	@if [ -f .env ]; then \
		echo ".env уже есть — не трогаю"; \
	else \
		cp .env.example .env; \
		echo "Создан .env. Заполните значения, помеченные как обязательные."; \
	fi

# Проверки

.PHONY: lint
lint:  ## Линтер без правок
	$(RUN) ruff check .
	$(RUN) ruff format --check .

.PHONY: format
format:  ## Отформатировать и починить, что чинится автоматически
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

.PHONY: types
types:  ## Строгая проверка типов
	$(RUN) mypy

.PHONY: test
test:  ## Тесты
	$(RUN) pytest

.PHONY: check
check: lint types test  ## Всё сразу — ровно то, что гоняет CI

# Локальный стенд

.PHONY: up
up: require-env  ## Поднять Postgres, Redis и MinIO и дождаться готовности
	docker compose up -d --wait

.PHONY: down
down:  ## Остановить стенд, данные сохранить
	docker compose down

.PHONY: destroy
destroy:  ## Остановить стенд и удалить данные (нужен чистый старт)
	docker compose down --volumes

.PHONY: logs
logs:  ## Смотреть логи стенда
	docker compose logs --follow --tail=50

.PHONY: ps
ps:  ## Что сейчас поднято
	docker compose ps

# Образ

.PHONY: build
build:  ## Собрать рабочий образ
	docker build --target runtime --tag $(IMAGE) .

# Уборка

.PHONY: clean
clean:  ## Удалить кэши инструментов и файлы сборки
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# Служебное

.PHONY: require-env
require-env:
	@test -f .env || { \
		echo "Нет файла .env — стенду нечего читать."; \
		echo "Выполните: make env, затем заполните обязательные значения."; \
		exit 1; \
	}
