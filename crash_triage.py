#!/usr/bin/env python3
"""
Crash Triage and Deduplication System for FuzzUEr
Automatically analyzes crashes, deduplicates, and generates reports
"""

import os, sys, re, json, hashlib
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

class CrashType(Enum):
    BUFFER_OVERFLOW = "buffer_overflow"
    NULL_DEREF = "null_pointer_deref"
    USE_AFTER_FREE = "use_after_free"
    DOUBLE_FREE = "double_free"
    STACK_OVERFLOW = "stack_overflow"
    HEAP_CORRUPTION = "heap_corruption"
    ASSERT_FAILURE = "assert_failure"
    UNKNOWN = "unknown"

@dataclass
class CrashInfo:
    """Information about a single crash"""
    crash_file: str
    crash_type: CrashType
    function_name: str = ""
    file_location: str = ""
    line_number: int = 0
    stack_trace: List[str] = field(default_factory=list)
    asan_report: str = ""
    crash_hash: str = ""
    protocol: str = ""
    reproducer_input: str = ""
    
    def generate_hash(self) -> str:
        """Generate unique hash for deduplication"""
        # Hash based on crash type, function, and top of stack
        hash_input = f"{self.crash_type.value}:{self.function_name}"
        if self.stack_trace:
            hash_input += ":" + ":".join(self.stack_trace[:3])
        
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

class CrashAnalyzer:
    """Analyzes crash logs and extracts information"""
    
    # ASAN patterns
    ASAN_PATTERNS = {
        CrashType.BUFFER_OVERFLOW: [
            r'heap-buffer-overflow',
            r'stack-buffer-overflow',
            r'global-buffer-overflow',
        ],
        CrashType.USE_AFTER_FREE: [
            r'heap-use-after-free',
        ],
        CrashType.DOUBLE_FREE: [
            r'attempting free on address which was already freed',
            r'double-free',
        ],
        CrashType.NULL_DEREF: [
            r'null-pointer-dereference',
            r'ASSERT.*NULL',
        ],
        CrashType.HEAP_CORRUPTION: [
            r'heap-corruption',
            r'corrupted heap',
        ],
    }
    
    def __init__(self):
        self.crashes: List[CrashInfo] = []
        self.crash_buckets: Dict[str, List[CrashInfo]] = defaultdict(list)
    
    def analyze_crash(self, crash_log: str, crash_file: str) -> Optional[CrashInfo]:
        """Analyze a single crash log"""
        crash = CrashInfo(crash_file=crash_file, crash_type=CrashType.UNKNOWN)
        
        # Detect crash type
        crash.crash_type = self._detect_crash_type(crash_log)
        
        # Extract ASAN report if present
        asan_match = re.search(r'=+\d+==ERROR: AddressSanitizer:.*?=+\d+==', 
                              crash_log, re.DOTALL)
        if asan_match:
            crash.asan_report = asan_match.group(0)
        
        # Extract function name
        func_match = re.search(r'in (\w+) (?:at|in) (.*?):(\d+)', crash_log)
        if func_match:
            crash.function_name = func_match.group(1)
            crash.file_location = func_match.group(2)
            crash.line_number = int(func_match.group(3))
        
        # Extract stack trace
        crash.stack_trace = self._extract_stack_trace(crash_log)
        
        # Generate hash
        crash.crash_hash = crash.generate_hash()
        
        # Try to determine protocol
        protocol_match = re.search(r'Protocol: (\w+)', crash_log)
        if protocol_match:
            crash.protocol = protocol_match.group(1)
        
        return crash
    
    def _detect_crash_type(self, log: str) -> CrashType:
        """Detect type of crash from log"""
        for crash_type, patterns in self.ASAN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, log, re.IGNORECASE):
                    return crash_type
        
        # Check for ASSERT failures
        if re.search(r'ASSERT.*FAILURE', log, re.IGNORECASE):
            return CrashType.ASSERT_FAILURE
        
        # Check for NULL dereference patterns
        if re.search(r'CR\(\).*(NULL|null)', log):
            return CrashType.NULL_DEREF
        
        return CrashType.UNKNOWN
    
    def _extract_stack_trace(self, log: str) -> List[str]:
        """Extract stack trace from log"""
        stack = []
        
        # Look for stack trace section
        trace_section = re.search(r'(?:Stack trace|Backtrace):?(.*?)(?:\n\n|$)', 
                                 log, re.DOTALL | re.IGNORECASE)
        if not trace_section:
            # Try ASAN format
            trace_section = re.search(r'#\d+.*', log, re.MULTILINE)
        
        if trace_section:
            lines = trace_section.group(0).split('\n')
            for line in lines:
                # Extract function names
                func_match = re.search(r'(?:#\d+|at|in)\s+(?:0x[0-9a-f]+\s+in\s+)?(\w+)', line)
                if func_match:
                    stack.append(func_match.group(1))
        
        return stack[:10]  # Limit to top 10 frames
    
    def deduplicate_crashes(self) -> Dict[str, List[CrashInfo]]:
        """Group crashes by hash"""
        for crash in self.crashes:
            self.crash_buckets[crash.crash_hash].append(crash)
        
        return self.crash_buckets
    
    def analyze_directory(self, crash_dir: str) -> int:
        """Analyze all crashes in directory"""
        count = 0
        
        for root, dirs, files in os.walk(crash_dir):
            for filename in files:
                if filename.endswith(('.log', '.txt', '.crash')):
                    crash_path = os.path.join(root, filename)
                    
                    try:
                        with open(crash_path, 'r', errors='ignore') as f:
                            log_content = f.read()
                        
                        crash = self.analyze_crash(log_content, crash_path)
                        if crash:
                            self.crashes.append(crash)
                            count += 1
                            print(f"[*] Analyzed: {filename} -> {crash.crash_type.value}")
                    except Exception as e:
                        print(f"[!] Error analyzing {filename}: {e}")
        
        return count

class ReportGenerator:
    """Generates crash analysis reports"""
    
    def __init__(self, analyzer: CrashAnalyzer):
        self.analyzer = analyzer
    
    def generate_html_report(self, output_file: str):
        """Generate HTML report"""
        buckets = self.analyzer.deduplicate_crashes()
        
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>FuzzUEr Crash Analysis Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .summary { background: #f0f0f0; padding: 15px; margin: 20px 0; }
        .bucket { border: 1px solid #ccc; margin: 20px 0; padding: 15px; }
        .crash-type { font-weight: bold; color: #d9534f; }
        .stack-trace { background: #f9f9f9; padding: 10px; font-family: monospace; }
        .unique { color: #5cb85c; font-weight: bold; }
        .critical { background: #fff3cd; }
        .high { background: #f8d7da; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
    </style>
</head>
<body>
    <h1>FuzzUEr Crash Analysis Report</h1>
"""
        
        # Summary
        html += f"""
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total Crashes:</strong> {len(self.analyzer.crashes)}</p>
        <p><strong>Unique Bugs:</strong> <span class="unique">{len(buckets)}</span></p>
    </div>
"""
        
        # Crash type distribution
        type_counts = defaultdict(int)
        for crash in self.analyzer.crashes:
            type_counts[crash.crash_type] += 1
        
        html += """
    <h2>Crash Distribution</h2>
    <table>
        <tr><th>Crash Type</th><th>Count</th></tr>
"""
        for crash_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            html += f"        <tr><td>{crash_type.value}</td><td>{count}</td></tr>\n"
        html += "    </table>\n"
        
        # Unique bugs
        html += """
    <h2>Unique Bugs</h2>
"""
        
        for crash_hash, crash_list in sorted(buckets.items(), 
                                            key=lambda x: -len(x[1])):
            representative = crash_list[0]
            severity = "high" if len(crash_list) > 5 else "critical" if representative.crash_type in [CrashType.BUFFER_OVERFLOW, CrashType.USE_AFTER_FREE] else ""
            
            html += f"""
    <div class="bucket {severity}">
        <h3>Bug #{crash_hash}</h3>
        <p><span class="crash-type">Type:</span> {representative.crash_type.value}</p>
        <p><strong>Occurrences:</strong> {len(crash_list)}</p>
        <p><strong>Function:</strong> {representative.function_name}</p>
        <p><strong>Location:</strong> {representative.file_location}:{representative.line_number}</p>
        <p><strong>Protocol:</strong> {representative.protocol or "Unknown"}</p>
        
        <details>
            <summary>Stack Trace</summary>
            <div class="stack-trace">
                {"<br>".join(representative.stack_trace)}
            </div>
        </details>
        
        <details>
            <summary>All Instances ({len(crash_list)})</summary>
            <ul>
"""
            for crash in crash_list[:10]:  # Limit to first 10
                html += f"                <li>{os.path.basename(crash.crash_file)}</li>\n"
            if len(crash_list) > 10:
                html += f"                <li>... and {len(crash_list)-10} more</li>\n"
            html += """
            </ul>
        </details>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        with open(output_file, 'w') as f:
            f.write(html)
        
        print(f"[+] HTML report written to {output_file}")
    
    def generate_json_report(self, output_file: str):
        """Generate JSON report"""
        buckets = self.analyzer.deduplicate_crashes()
        
        report = {
            'summary': {
                'total_crashes': len(self.analyzer.crashes),
                'unique_bugs': len(buckets),
            },
            'bugs': []
        }
        
        for crash_hash, crash_list in buckets.items():
            representative = crash_list[0]
            report['bugs'].append({
                'hash': crash_hash,
                'type': representative.crash_type.value,
                'function': representative.function_name,
                'location': f"{representative.file_location}:{representative.line_number}",
                'protocol': representative.protocol,
                'occurrences': len(crash_list),
                'stack_trace': representative.stack_trace,
                'instances': [os.path.basename(c.crash_file) for c in crash_list]
            })
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[+] JSON report written to {output_file}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Crash triage for FuzzUEr')
    parser.add_argument('-d', '--crash-dir', required=True,
                       help='Directory containing crash logs')
    parser.add_argument('-o', '--output', default='crash_report.html',
                       help='Output report file')
    parser.add_argument('-j', '--json', help='Also generate JSON report')
    parser.add_argument('--deduplicate', action='store_true',
                       help='Deduplicate crashes')
    args = parser.parse_args()
    
    analyzer = CrashAnalyzer()
    
    print(f"[*] Analyzing crashes in {args.crash_dir}...")
    count = analyzer.analyze_directory(args.crash_dir)
    print(f"[+] Analyzed {count} crash logs")
    
    if args.deduplicate:
        buckets = analyzer.deduplicate_crashes()
        print(f"[+] Found {len(buckets)} unique bugs")
    
    # Generate reports
    generator = ReportGenerator(analyzer)
    generator.generate_html_report(args.output)
    
    if args.json:
        generator.generate_json_report(args.json)
    
    # Print summary
    print("\n" + "="*60)
    print("CRASH SUMMARY")
    print("="*60)
    for crash_type in CrashType:
        crashes_of_type = [c for c in analyzer.crashes if c.crash_type == crash_type]
        if crashes_of_type:
            print(f"{crash_type.value:30s}: {len(crashes_of_type):4d}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
