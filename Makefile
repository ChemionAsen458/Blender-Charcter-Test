# Build, verify and preview the character.
#
#   make            build the .blend (generating textures if needed)
#   make textures   regenerate the texture templates
#   make verify     run the rig checks
#   make preview    render the turnaround / expression / shadow sheets
#   make all        everything
#   make clean      remove build output

PYTHON      ?= python3
BLEND       ?= build/kaito.blend
TEXTURE_DIR ?= textures/generated
TEXTURE_SIZE?= 2048
PREVIEW_DIR ?= build/preview
SAMPLES     ?= 32

.PHONY: all build textures verify preview clean check

build:
	$(PYTHON) build.py --out $(BLEND) --textures $(TEXTURE_DIR)

textures:
	$(PYTHON) -m tools.generate_textures --size $(TEXTURE_SIZE) --out $(TEXTURE_DIR)

verify:
	$(PYTHON) -m tools.verify --blend $(BLEND)

preview:
	$(PYTHON) -m tools.showcase --blend $(BLEND) --out $(PREVIEW_DIR) --samples $(SAMPLES)

check:
	$(PYTHON) -m compileall -q character tools build.py

all: textures build verify preview

clean:
	rm -rf build $(TEXTURE_DIR)
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
