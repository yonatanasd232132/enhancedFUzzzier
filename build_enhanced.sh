#!/bin/bash
# Automated build script for Enhanced FuzzUEr

set -e

echo "======================================"
echo "FuzzUEr Enhanced Build Script"
echo "======================================"
echo ""

# Check prerequisites
echo "[1/7] Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Please install Docker first."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found."
    exit 1
fi

# Check Python packages
echo "[2/7] Checking Python dependencies..."
python3 -c "import z3" 2>/dev/null || {
    echo "Installing z3-solver..."
    pip3 install z3-solver --break-system-packages
}

python3 -c "import pycparser" 2>/dev/null || {
    echo "Installing pycparser..."
    pip3 install pycparser --break-system-packages
}

python3 -c "import networkx" 2>/dev/null || {
    echo "Installing networkx..."
    pip3 install networkx --break-system-packages
}

echo "✓ All dependencies installed"

# Setup directories
echo "[3/7] Setting up directories..."
WORKDIR="$PWD"
FUZZUER_DIR="${WORKDIR}/FuzzUEr"

# Clone or update FuzzUEr
if [ ! -d "$FUZZUER_DIR" ]; then
    echo "Cloning FuzzUEr repository..."
    git clone https://github.com/BreakingBoot/FuzzUEr.git
    cd "$FUZZUER_DIR"
    git submodule update --init --recursive
else
    echo "FuzzUEr directory exists, updating..."
    cd "$FUZZUER_DIR"
    git pull
    git submodule update --init --recursive
fi

echo "✓ FuzzUEr repository ready"

# Copy enhancement files
echo "[4/7] Copying enhancement files..."
ENHANCE_DIR="${WORKDIR}/fuzzuer_enhancements"

if [ ! -d "$ENHANCE_DIR" ]; then
    echo "ERROR: Enhancement directory not found at $ENHANCE_DIR"
    echo "Please ensure fuzzuer_enhancements directory is in current directory"
    exit 1
fi

cp -v "$ENHANCE_DIR"/*.py "$FUZZUER_DIR/"
cp -v "$ENHANCE_DIR"/*.md "$FUZZUER_DIR/"
cp -v "$ENHANCE_DIR"/*.patch "$FUZZUER_DIR/" 2>/dev/null || true

echo "✓ Enhancement files copied"

# Apply ASAN patch
echo "[5/7] Applying enhanced ASAN patch..."
cd "$FUZZUER_DIR/uefi_asan"

if [ -f "${FUZZUER_DIR}/enhanced_asan.patch" ]; then
    patch -p1 < "${FUZZUER_DIR}/enhanced_asan.patch" || {
        echo "WARNING: Patch may have already been applied or conflicts exist"
    }
    echo "✓ ASAN patch applied"
else
    echo "WARNING: ASAN patch not found, skipping"
fi

cd "$FUZZUER_DIR"

# Modify Dockerfile
echo "[6/7] Updating Dockerfile..."
if ! grep -q "z3-solver" Dockerfile 2>/dev/null; then
    cat >> Dockerfile << 'EOFDOCKERFILE'

# Enhanced FuzzUEr dependencies
RUN pip3 install --break-system-packages \
    z3-solver \
    pycparser \
    networkx \
    jinja2

# Copy enhancement scripts
COPY concolic_engine.py /workspace/
COPY callback_handler.py /workspace/
COPY protocol_mutators.py /workspace/
COPY crash_triage.py /workspace/
COPY firness_enhanced.py /workspace/

RUN chmod +x /workspace/*.py
EOFDOCKERFILE
    echo "✓ Dockerfile updated"
else
    echo "✓ Dockerfile already has enhancements"
fi

# Build Docker image
echo "[7/7] Building enhanced Docker image..."
echo "This will take 20-30 minutes..."
docker build -t fuzzuer-enhanced:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "✓ Build Complete!"
    echo "======================================"
    echo ""
    echo "Docker image: fuzzuer-enhanced:latest"
    echo ""
    echo "Next steps:"
    echo "1. Prepare your input directory:"
    echo "   mkdir -p eval_source && cd eval_source"
    echo "   git clone https://github.com/tianocore/edk2.git"
    echo "   # Create input.txt with target protocols"
    echo ""
    echo "2. Run enhanced fuzzer:"
    echo "   docker run -it -v \$(pwd)/eval_source:/input fuzzuer-enhanced:latest"
    echo ""
    echo "3. Inside container:"
    echo "   python3 firness_enhanced.py -i /input/input.txt -s /input/edk2 --all-enhancements"
    echo ""
    echo "For detailed instructions, see:"
    echo "- QUICK_START.md for quick guide"
    echo "- INTEGRATION_GUIDE.md for complete documentation"
    echo ""
else
    echo ""
    echo "======================================"
    echo "✗ Build Failed"
    echo "======================================"
    echo ""
    echo "Please check the error messages above and ensure:"
    echo "1. Docker has sufficient resources (32GB+ RAM recommended)"
    echo "2. You have enough disk space (100GB+ free)"
    echo "3. Network connection is stable"
    echo ""
    exit 1
fi
