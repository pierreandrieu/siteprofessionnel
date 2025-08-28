# Makefile — outils de développement pour « plandeclasse »

# --------------------------------------------------------------------
# détection de l’environnement virtuel
# - si un venv est déjà activé (VIRTUAL_ENV), on l’utilise
# - sinon on crée/emploie un dossier local .venv
# --------------------------------------------------------------------
PYTHON       ?= python3
VIRTUAL_ENV  ?= $(shell echo $$VIRTUAL_ENV)
ifeq ($(VIRTUAL_ENV),)
  VENV_DIR   := .venv
  BIN        := $(VENV_DIR)/bin
  PYTHON_BIN := $(BIN)/python
  PIP        := $(PYTHON_BIN) -m pip
else
  VENV_DIR   := $(VIRTUAL_ENV)
  BIN        := $(VIRTUAL_ENV)/bin
  PYTHON_BIN := $(BIN)/python
  PIP        := $(PYTHON_BIN) -m pip
endif

# outils appelés via "python -m ..." pour éviter les chemins cassés
PYTEST := $(PYTHON_BIN) -m pytest
RUFF   := $(PYTHON_BIN) -m ruff
MYPY   := $(PYTHON_BIN) -m mypy

DEV_PKGS := pytest ruff mypy

.PHONY: help default venv install test run-exemple lint format type clean reset

default: help

help:
	@echo "Cibles : venv | install | test | run-exemple | lint | format | type | clean | reset"

# crée un venv local seulement si aucun venv actif
venv:
ifeq ($(VIRTUAL_ENV),)
	$(PYTHON) -m venv .venv
	@echo "Environnement virtuel créé dans .venv"
else
	@echo "Un environnement est déjà actif: $(VIRTUAL_ENV)"
endif

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install $(DEV_PKGS)
	@echo "Dépendances installées : $(DEV_PKGS)"

test:
	$(PYTEST) -q

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

type:
	$(MYPY) plandeclasse

run-exemple:
	$(PYTHON_BIN) -m plandeclasse

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@rm -rf .pytest_cache .mypy_cache
	@echo "Caches nettoyés."

reset:
	@rm -rf .venv
	@$(MAKE) venv install
