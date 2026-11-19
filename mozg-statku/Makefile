.PHONY: up down logs test e2e dev certs sat-on sat-off

up:            ## cały serwer jedną komendą
	./start.sh $(IP)

down:
	docker compose down

logs:
	docker compose logs -f api sensors shore

test:          ## testy jednostkowe rdzenia
	cd server && python3 -m pytest -q

e2e:           ## scenariusz demo przez HTTP (serwer musi działać)
	python3 scripts/e2e_test.py

dev:           ## tryb hybrydowy: API na hoście (GPU/Mac), reszta w Dockerze
	docker compose up -d mosquitto shore caddy sensors
	cd server && DATA_DIR=../data/ship SHORE_URL=http://localhost:9000 RELOAD=1 python3 -m app

certs:
	./scripts/certs.sh $(IP)

sat-on:
	curl -s -X POST localhost:8000/api/sync/link -H 'Content-Type: application/json' -d '{"up":true}'

sat-off:
	curl -s -X POST localhost:8000/api/sync/link -H 'Content-Type: application/json' -d '{"up":false}'
