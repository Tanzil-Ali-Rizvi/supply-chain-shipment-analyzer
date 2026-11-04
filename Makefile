test:
	pytest -q && python evals/run_evals.py
app:
	streamlit run app/streamlit_app.py
tableau:
	python scripts/export_tableau.py
