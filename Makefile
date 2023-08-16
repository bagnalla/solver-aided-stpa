default: parser
	mypy --strict control.py parser.py solver.py run.py tycheck.py && python3 run.py

parser: tree-sitter-stpa/grammar.js
	cd tree-sitter-stpa && tree-sitter generate

clean:
	rm -rf __pycache__ .mypy_cache
