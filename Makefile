# Makefile for running the virtual environment and starting uvicorn

# Path to the virtual environment
VENV = .venv

# Detect OS and set activation path
ifeq ($(OS), Windows_NT) # Windows
	ACTIVATE = source $(VENV)/Scripts/activate
else # macOS/Linux
	ACTIVATE = source $(VENV)/bin/activate
endif

# Command to run uvicorn server
RUN_UVICORN = uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log --reload

# Default target to set up environment and run the server
run:
	$(ACTIVATE) && $(RUN_UVICORN)

# Install dependencies from requirements.txt
install:
	$(ACTIVATE) && pip install -r requirements.txt

# Install a specific package and update requirements.txt
i:
	$(ACTIVATE) && pip install $(word 2, $(MAKECMDGOALS))
	$(ACTIVATE) && pip freeze > requirements.txt

# Create a new virtual environment (if .venv does not exist)
create-venv:
	python3 -m venv $(VENV)
