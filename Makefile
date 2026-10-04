.PHONY: check test run demo serve deadcode

check:
	python -m compileall -q batterystore
	python tools/deadcode.py batterystore

test:
	PYTHONPATH=. python -m pytest -q

run:
	PYTHONPATH=. python -m batterystore --config config/batterystore.json serve --host 127.0.0.1 --port 8080

demo:
	PYTHONPATH=. python -m batterystore --config config/batterystore.json demo --fast --racks 2

deadcode:
	PYTHONPATH=. python tools/deadcode.py batterystore
