# End-to-end pipeline. Run `make all` after `make setup` and starting PostgreSQL.
PY ?= .venv/bin/python
DB ?= ecommerce

.PHONY: setup db data load train export charts notebooks sql app all clean

setup:            ## create virtualenv and install dependencies
	python3 -m venv .venv && $(PY) -m pip install -r requirements.txt

db:               ## create the PostgreSQL database (once)
	createdb $(DB) || true

data:             ## generate synthetic raw CSVs
	$(PY) -m src.generate_data

load:             ## load + clean into PostgreSQL, build views, print data-quality report
	$(PY) -m src.load_to_postgres

train:            ## train / evaluate / explain model and score customers
	$(PY) -m src.train_model

export:           ## export Tableau + app extracts
	$(PY) -m src.export_for_tableau

charts:           ## render README charts
	$(PY) -m src.make_charts

notebooks:        ## execute notebooks in place
	cd notebooks && ../$(PY) -m nbconvert --to notebook --execute --inplace 01_eda.ipynb 02_modeling.ipynb

sql:              ## run the business-question queries
	psql -d $(DB) -f sql/06_business_questions.sql

app:              ## launch the Streamlit dashboard
	$(PY) -m streamlit run app/streamlit_app.py

all: data load train export charts notebooks

clean:
	rm -rf data/raw/*.csv data/exports/*.csv models/*.pkl models/*.csv models/*.json images/*.png
