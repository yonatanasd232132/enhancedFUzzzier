#!/usr/bin/env python3
"""
Enhanced FIRNESS Wrapper
Integrates all FuzzUEr enhancements
"""

import sys
import os
import subprocess
import argparse

def run_original_firness(args):
    """Run original FIRNESS"""
    cmd = ['python3', 'firness.py']
    
    if args.input:
        cmd.extend(['-i', args.input])
    if args.src:
        cmd.extend(['-s', args.src])
    if args.analyze:
        cmd.append('-a')
    if args.generate:
        cmd.append('-g')
    if args.fuzz:
        cmd.append('-f')
    if args.random:
        cmd.append('-r')
    if args.eval:
        cmd.append('-e')
    if args.timeout:
        cmd.extend(['-t', args.timeout])
    
    print("[*] Running original FIRNESS...")
    result = subprocess.run(cmd, cwd='/workspace')
    return result.returncode == 0

def apply_enhancements(args):
    """Apply all enhancements"""
    firness_json = '/workspace/firness_output/Firness/firness.json'
    
    if not os.path.exists(firness_json):
        print("[!] FIRNESS output not found. Run with -a -g first.")
        return False
    
    success = True
    
    # Enhancement 1: Concolic Execution
    if args.enable_concolic or args.all_enhancements:
        print("\n[*] Generating concolic inputs...")
        try:
            result = subprocess.run([
                'python3', '/workspace/concolic_engine.py',
                '-f', firness_json,
                '-o', '/workspace/concolic_inputs',
                '-m', str(args.concolic_paths or 100)
            ])
            if result.returncode == 0:
                print(f"[+] Generated concolic inputs in /workspace/concolic_inputs")
            else:
                print(f"[!] Concolic engine failed (non-critical)")
                success = False
        except Exception as e:
            print(f"[!] Concolic execution error: {e}")
            success = False
    
    # Enhancement 2: Callback Support
    if args.enable_callbacks or args.all_enhancements:
        print("\n[*] Enhancing harness with callback support...")
        harness_file = '/workspace/firness_output/Firness/harness.c'
        if os.path.exists(harness_file):
            try:
                result = subprocess.run([
                    'python3', '/workspace/callback_handler.py',
                    '-f', firness_json,
                    '-e', args.src or '/input/edk2',
                    '-i', harness_file,
                    '-o', '/workspace/firness_output/Firness/harness_enhanced.c'
                ])
                if result.returncode == 0:
                    print(f"[+] Enhanced harness with callbacks")
                else:
                    print(f"[!] Callback handler failed (non-critical)")
            except Exception as e:
                print(f"[!] Callback enhancement error: {e}")
        else:
            print(f"[!] Harness not found at {harness_file}")
    
    # Enhancement 3: Protocol-Specific Mutators
    if (args.enable_mutators or args.all_enhancements) and args.protocol:
        print("\n[*] Generating protocol-specific mutations...")
        seed_file = '/workspace/firness_output/seed.bin'
        
        # Create a basic seed if it doesn't exist
        if not os.path.exists(seed_file):
            print("[*] Creating initial seed file...")
            os.makedirs('/workspace/firness_output', exist_ok=True)
            with open(seed_file, 'wb') as f:
                f.write(b'\x00' * 1024)  # 1KB of zeros as seed
        
        try:
            result = subprocess.run([
                'python3', '/workspace/protocol_mutators.py',
                '-p', args.protocol,
                '-i', seed_file,
                '-o', '/workspace/protocol_mutations',
                '-n', str(args.num_mutations or 100)
            ])
            if result.returncode == 0:
                print(f"[+] Generated protocol mutations in /workspace/protocol_mutations")
            else:
                print(f"[!] Protocol mutator failed (non-critical)")
        except Exception as e:
            print(f"[!] Protocol mutation error: {e}")
    
    return success

def main():
    parser = argparse.ArgumentParser(
        description='Enhanced FIRNESS with all improvements'
    )
    
    # Original FIRNESS arguments
    parser.add_argument('-i', '--input', help='Path to input file')
    parser.add_argument('-s', '--src', help='Path to EDK2 source')
    parser.add_argument('-a', '--analyze', action='store_true',
                       help='Run static analysis')
    parser.add_argument('-g', '--generate', action='store_true',
                       help='Generate harness')
    parser.add_argument('-f', '--fuzz', action='store_true',
                       help='Run fuzzer')
    parser.add_argument('-r', '--random', action='store_true',
                       help='Randomize input')
    parser.add_argument('-e', '--eval', action='store_true',
                       help='Evaluate results')
    parser.add_argument('-t', '--timeout', help='Timeout for fuzzer')
    
    # Enhancement flags
    parser.add_argument('--enable-concolic', action='store_true',
                       help='Enable concolic execution')
    parser.add_argument('--concolic-paths', type=int, default=100,
                       help='Number of paths for concolic execution')
    
    parser.add_argument('--enable-callbacks', action='store_true',
                       help='Enable callback support')
    
    parser.add_argument('--enable-mutators', action='store_true',
                       help='Enable protocol-specific mutators')
    parser.add_argument('--num-mutations', type=int, default=100,
                       help='Number of mutations to generate')
    
    parser.add_argument('--protocol', 
                       help='Protocol GUID for mutators')
    
    parser.add_argument('--all-enhancements', action='store_true',
                       help='Enable all enhancements')
    
    args = parser.parse_args()
    
    # Enable all if requested
    if args.all_enhancements:
        args.enable_concolic = True
        args.enable_callbacks = True
        args.enable_mutators = True
    
    # Run original FIRNESS first
    if not run_original_firness(args):
        print("[!] FIRNESS failed")
        return 1
    
    # Apply enhancements if any are enabled
    if any([args.enable_concolic, args.enable_callbacks, args.enable_mutators]):
        print("\n" + "="*60)
        print("APPLYING ENHANCEMENTS")
        print("="*60)
        
        if not apply_enhancements(args):
            print("\n[!] Some enhancements failed, but continuing...")
        
        print("\n" + "="*60)
        print("ENHANCEMENT SUMMARY")
        print("="*60)
        
        if args.enable_concolic:
            if os.path.exists('/workspace/concolic_inputs'):
                count = len(os.listdir('/workspace/concolic_inputs'))
                print(f"✓ Concolic inputs: {count} files in /workspace/concolic_inputs")
            else:
                print("✗ Concolic inputs: Failed to generate")
        
        if args.enable_callbacks:
            if os.path.exists('/workspace/firness_output/Firness/harness_enhanced.c'):
                print(f"✓ Callback support: Enhanced harness created")
            else:
                print("✗ Callback support: Enhancement failed")
        
        if args.enable_mutators:
            if os.path.exists('/workspace/protocol_mutations'):
                count = len(os.listdir('/workspace/protocol_mutations'))
                print(f"✓ Protocol mutators: {count} mutations in /workspace/protocol_mutations")
            else:
                print("✗ Protocol mutators: Failed to generate")
    
    print("\n[+] Enhanced FIRNESS completed successfully")
    
    if args.fuzz:
        print("\n" + "="*60)
        print("FUZZING READY")
        print("="*60)
        print("Next steps:")
        print("  1. Review harness: /workspace/firness_output/Firness/")
        
        if args.enable_concolic and os.path.exists('/workspace/concolic_inputs'):
            print("  2. Use concolic seeds: ./simics -seed-dir /workspace/concolic_inputs")
        else:
            print("  2. Run fuzzer: cd /workspace/firness_output/Firness && ./simics -no-win -no-gui fuzz.simics")
        
        print("  3. After fuzzing, analyze crashes:")
        print("     python3 /workspace/crash_triage.py -d crashes/ -o report.html --deduplicate")
    else:
        print("\nTo start fuzzing:")
        print("  cd /workspace/firness_output/Firness")
        print("  ./simics -no-win -no-gui fuzz.simics")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
