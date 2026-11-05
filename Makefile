.PHONY: test demo lint serve
test:
	python -m pytest -q
demo:
	python -m dcop.demo
lint:
	python -m compileall dcop
serve:
	uvicorn dcop.api:app --host 127.0.0.1 --port 8000
