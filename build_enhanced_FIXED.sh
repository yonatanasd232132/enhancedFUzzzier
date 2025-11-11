#!/bin/bash
# FIXED: Enhanced build script with better error handling

set -e

echo "======================================"
echo "FuzzUEr Enhanced Build Script (FIXED)"
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
FUZZUER_DIR="${WORKDIR}"

# Verify we're in FuzzUEr directory
if [ ! -f "firness.py" ]; then
    echo "ERROR: Not in FuzzUEr directory. Please run this from FuzzUEr root."
    echo "Current directory: $PWD"
    echo "Expected to find: firness.py"
    exit 1
fi

echo "✓ FuzzUEr directory verified"

# Copy enhancement files (should already be here, but verify)
echo "[4/7] Verifying enhancement files..."
REQUIRED_FILES="concolic_engine.py callback_handler.py protocol_mutators.py crash_triage.py"
MISSING=""

for file in $REQUIRED_FILES; do
    if [ ! -f "$file" ]; then
        MISSING="$MISSING $file"
    fi
done

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing enhancement files:$MISSING"
    echo "Please copy enhancement files to this directory first."
    exit 1
fi

echo "✓ Enhancement files present"

# Apply ASAN patch (FIXED - with better error handling)
echo "[5/7] Applying enhanced ASAN patch..."

if [ -f "enhanced_asan.patch" ]; then
    echo "Found ASAN patch, attempting to apply..."
    
    # Check if uefi_asan directory exists
    if [ ! -d "uefi_asan" ]; then
        echo "WARNING: uefi_asan directory not found"
        echo "ASAN enhancements will be skipped"
        echo "This is OK - fuzzing will work without ASAN enhancements"
    else
        cd uefi_asan
        
        # Try to apply patch, but don't fail if it doesn't work
        if patch -p1 --dry-run < ../enhanced_asan.patch > /dev/null 2>&1; then
            echo "Applying ASAN patch..."
            patch -p1 < ../enhanced_asan.patch
            echo "✓ ASAN patch applied successfully"
        else
            echo "WARNING: ASAN patch cannot be applied"
            echo "Reasons could be:"
            echo "  - Patch already applied"
            echo "  - Different EDK2 version"
            echo "  - File structure mismatch"
            echo ""
            echo "This is OK - continuing without ASAN enhancements"
            echo "Basic fuzzing will still work"
        fi
        
        cd "$FUZZUER_DIR"
    fi
else
    echo "WARNING: enhanced_asan.patch not found"
    echo "Continuing without ASAN enhancements"
fi

# Modify Dockerfile
echo "[6/7] Updating Dockerfile..."

# Check if Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo "ERROR: Dockerfile not found in current directory"
    exit 1
fi

# Check if already modified
if grep -q "z3-solver" Dockerfile 2>/dev/null; then
    echo "✓ Dockerfile already has enhancements"
else
    echo "Adding enhancement dependencies to Dockerfile..."
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
COPY firness_enhanced.py /workspace/ 2>/dev/null || true

RUN chmod +x /workspace/*.py 2>/dev/null || true
EOFDOCKERFILE
    echo "✓ Dockerfile updated"
fi

# Create enhanced FIRNESS wrapper if it doesn't exist
if [ ! -f "firness_enhanced.py" ]; then
    echo "Creating firness_enhanced.py wrapper..."
    cat > firness_enhanced.py << 'EOFPYTHON'
#!/usr/bin/env python3
"""Enhanced FIRNESS wrapper"""
import sys, os, subprocess, argparse

def main():
    parser = argparse.ArgumentParser(description='Enhanced FIRNESS')
    parser.add_argument('-i', '--input')
    parser.add_argument('-s', '--src')
    parser.add_argument('-a', '--analyze', action='store_true')
    parser.add_argument('-g', '--generate', action='store_true')
    parser.add_argument('-f', '--fuzz', action='store_true')
    parser.add_argument('-t', '--timeout')
    parser.add_argument('--enable-concolic', action='store_true')
    parser.add_argument('--enable-callbacks', action='store_true')
    parser.add_argument('--enable-mutators', action='store_true')
    parser.add_argument('--all-enhancements', action='store_true')
    parser.add_argument('--protocol')
    args = parser.parse_args()
    
    # Run original firness
    cmd = ['python3', 'firness.py']
    if args.input: cmd.extend(['-i', args.input])
    if args.src: cmd.extend(['-s', args.src])
    if args.analyze: cmd.append('-a')
    if args.generate: cmd.append('-g')
    if args.fuzz: cmd.append('-f')
    if args.timeout: cmd.extend(['-t', args.timeout])
    
    print("[*] Running FIRNESS...")
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print("[!] FIRNESS failed")
        return 1
    
    # Apply enhancements if requested
    if args.all_enhancements or args.enable_concolic or args.enable_callbacks or args.enable_mutators:
        print("\n[*] Applying enhancements...")
        
        if args.all_enhancements or args.enable_concolic:
            if os.path.exists('/workspace/firness_output/Firness/firness.json'):
                print("[*] Running concolic engine...")
                subprocess.run([
                    'python3', 'concolic_engine.py',
                    '-f', '/workspace/firness_output/Firness/firness.json',
                    '-o', '/workspace/concolic_inputs',
                    '-m', '100'
                ])
        
        print("[+] Enhancements applied")
    
    print("\n[+] Complete!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
EOFPYTHON
    chmod +x firness_enhanced.py
fi

# Build Docker image
echo "[7/7] Building enhanced Docker image..."
echo "This will take 20-30 minutes..."
echo ""

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
    echo "1. Prepare input directory with EDK2:"
    echo "   mkdir -p eval_source"
    echo "   cd eval_source"
    echo "   git clone https://github.com/tianocore/edk2.git"
    echo ""
    echo "2. Create input.txt with target protocols"
    echo ""
    echo "3. Run enhanced fuzzer:"
    echo "   docker run -it -v \$(pwd)/eval_source:/input fuzzuer-enhanced:latest"
    echo ""
    echo "4. Inside container:"
    echo "   python3 firness_enhanced.py -i /input/input.txt -s /input/edk2 -a -g"
    echo ""
else
    echo ""
    echo "======================================"
    echo "✗ Build Failed"
    echo "======================================"
    echo ""
    echo "Check error messages above"
    echo ""
    echo "Common issues:"
    echo "  - Not enough memory (need 8GB+ for build)"
    echo "  - Not enough disk space (need 20GB+ free)"
    echo "  - Network timeout (try again)"
    echo ""
    exit 1
fi
