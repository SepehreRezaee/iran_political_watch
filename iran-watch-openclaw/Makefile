PYTHON ?= python3
PIP ?= pip3

.PHONY: setup setup-slm-airllm run-8h run-daily test docker-build docker-run lint

setup:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

setup-slm-airllm:
	$(PIP) install -r requirements-slm-airllm.txt

run-8h:
	$(PYTHON) -m iran_watch run --mode 8h

run-daily:
	$(PYTHON) -m iran_watch run --mode daily

test:
	pytest -q

lint:
	$(PYTHON) -m compileall -q iran_watch tests

docker-build:
	docker build -t iran-watch-openclaw:latest .

docker-run:
	docker compose run --rm iran-watch
