# Makefile for running the virtual environment and starting uvicorn

# Path to the virtual environment
VENV = .venv

# Activate the virtual environment
ACTIVATE = source $(VENV)/Scripts/activate

# Command to run uvicorn server
RUN_UVICORN = uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log --reload

# Default target to set up environment and run the server
run:
	$(ACTIVATE) && $(RUN_UVICORN)

# Install dependencies from requirements.txt
install:
	$(ACTIVATE) && pip install -r requirements.txt

# Create a new virtual environment (if .venv does not exist)
create-venv:
	python -m venv .venv
