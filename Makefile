default:
	mypy control.py && python3 run.py

clean:
	rm -rf __pycache__
