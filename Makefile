UV ?= uv
DEVICE ?= admin@gamebox.local
TARGET_PYTHON ?= 3.13

# Windows: npm обычно установлен как npm.cmd; GNU Make может не находить его
# через CreateProcess без оболочки. cmd /c решает это и для PowerShell, и для make.
ifeq ($(OS),Windows_NT)
NPM ?= cmd /c npm
else
NPM ?= npm
endif

.PHONY: setup check lint typecheck test schemas schemas-check ui wheelhouse device-package device-deploy clean

setup:
	$(UV) sync --frozen --extra dev
	$(NPM) ci --prefix ui

check: setup schemas-check lint typecheck ui test

lint:
	$(UV) run ruff check gamebox tests deploy --exclude deploy/hwcheck
	$(UV) run ruff format --check gamebox tests deploy --exclude deploy/hwcheck

typecheck:
	$(UV) run mypy gamebox
	$(NPM) run --prefix ui typecheck

test:
	$(UV) run pytest

schemas:
	$(UV) run python -m gamebox.devtools.schemas

schemas-check:
	$(UV) run python -m gamebox.devtools.schemas --check

ui:
	$(NPM) run --prefix ui build

wheelhouse: setup
	$(UV) export --frozen --no-dev --extra device --no-emit-project --output-file .build/device-requirements.txt
	$(UV) build --wheel --out-dir .build/dist
	$(UV) run python deploy/build_wheelhouse.py --requirements .build/device-requirements.txt --project-wheel .build/dist --output wheelhouse --python-version $(TARGET_PYTHON)

device-package: check wheelhouse
	$(UV) run python deploy/package_release.py --output .build

device-deploy: device-package
	$(UV) run python deploy/device_deploy.py --device "$(DEVICE)"

clean:
	rm -rf .build wheelhouse ui/dist
