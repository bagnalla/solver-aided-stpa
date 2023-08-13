default:
	mypy control.py run.py && python3 run.py

clean:
	rm -rf __pycache__ .mypy_cache
