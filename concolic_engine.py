#!/usr/bin/env python3
"""
Concolic Execution Engine for FuzzUEr
Author: Enhancement Module for NDSS FuzzUEr
Description: Adds symbolic execution to overcome path constraint limitations
"""

import os, sys, json, struct, re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

try:
    from z3 import *
except ImportError:
    print("Install Z3: pip install z3-solver --break-system-packages")
    sys.exit(1)

class ConstraintType(Enum):
    EQ="eq"; NEQ="neq"; LT="lt"; GT="gt"; LE="le"; GE="ge"
    NULL="null"; BOUNDS="bounds"; FLAG="flags"

@dataclass
class PathConstraint:
    var_name: str
    constraint_type: ConstraintType
    value: Optional[int] = None
    location: str = ""
    
    def to_z3(self, z3_vars):
        if self.var_name not in z3_vars:
            z3_vars[self.var_name] = BitVec(self.var_name, 64)
        var = z3_vars[self.var_name]
        
        if self.constraint_type == ConstraintType.EQ: return var == self.value
        elif self.constraint_type == ConstraintType.NEQ: return var != self.value
        elif self.constraint_type == ConstraintType.LT: return var < self.value
        elif self.constraint_type == ConstraintType.GT: return var > self.value
        elif self.constraint_type == ConstraintType.LE: return var <= self.value
        elif self.constraint_type == ConstraintType.GE: return var >= self.value
        elif self.constraint_type == ConstraintType.NULL: return var != 0
        elif self.constraint_type == ConstraintType.FLAG: 
            return (var & self.value) != 0
        return BoolVal(True)

@dataclass
class ExecutionPath:
    constraints: List[PathConstraint] = field(default_factory=list)
    
    def solve(self):
        solver, z3_vars = Solver(), {}
        for c in self.constraints:
            solver.add(c.to_z3(z3_vars))
        if solver.check() == sat:
            model = solver.model()
            return {v: model.eval(z, True).as_long() if hasattr(model.eval(z, True), 'as_long') else 0 
                   for v,z in z3_vars.items()}
        return None

class ConcolicEngine:
    def __init__(self, firness_json):
        with open(firness_json) as f:
            self.firness_data = json.load(f)
        self.constraint_cache = {}
    
    def extract_constraints(self, source_file, function_name):
        """Extract UEFI constraint patterns from source"""
        constraints = []
        if not os.path.exists(source_file): return constraints
        
        with open(source_file) as f: content = f.read()
        
        # Find function
        pattern = rf'{function_name}\s*\('
        match = re.search(pattern, content)
        if not match: return constraints
        
        # Extract function body
        start = content.find('{', match.end())
        if start == -1: return constraints
        
        depth, end = 1, start + 1
        while depth > 0 and end < len(content):
            if content[end] == '{': depth += 1
            elif content[end] == '}': depth -= 1
            end += 1
        
        func_body = content[start:end]
        lines = func_body.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # NULL checks
            if 'if' in line and ('== NULL' in line or '!=' in line):
                var_match = re.search(r'if\s*\(\s*(\w+)\s*[!=]=\s*NULL', line)
                if var_match:
                    constraints.append(PathConstraint(
                        var_match.group(1), ConstraintType.NULL,
                        location=f"{function_name}:{i}"
                    ))
            
            # Flag checks: if ((Flags & CONST) ...)
            if 'if' in line and '&' in line and '&&' not in line:
                flag_match = re.search(r'if\s*\(\s*\(?(\w+)\s*&\s*(0x[0-9a-fA-F]+|\w+)', line)
                if flag_match:
                    var, val = flag_match.groups()
                    try:
                        val_int = int(val, 16) if val.startswith('0x') else 0
                        constraints.append(PathConstraint(
                            var, ConstraintType.FLAG, val_int,
                            location=f"{function_name}:{i}"
                        ))
                    except: pass
            
            # Comparisons
            for op, ctype in [('<', ConstraintType.LT), ('>', ConstraintType.GT),
                            ('<=', ConstraintType.LE), ('>=', ConstraintType.GE),
                            ('==', ConstraintType.EQ), ('!=', ConstraintType.NEQ)]:
                if f'if' in line and op in line:
                    comp_match = re.search(rf'if\s*\(\s*(\w+)\s*{re.escape(op)}\s*([0-9x]+)', line)
                    if comp_match:
                        var, val = comp_match.groups()
                        try:
                            val_int = int(val, 0)
                            constraints.append(PathConstraint(
                                var, ctype, val_int,
                                location=f"{function_name}:{i}"
                            ))
                        except: pass
        
        return constraints
    
    def generate_inputs(self, output_dir, max_paths=100):
        """Generate concolic test inputs"""
        os.makedirs(output_dir, exist_ok=True)
        count = 0
        
        for func_data in self.firness_data:
            func = func_data.get('Function', '')
            if not func: continue
            
            print(f"[*] Processing {func}")
            constraints = self.constraint_cache.get(func, [])
            if not constraints: continue
            
            # Generate paths
            paths = self._gen_paths(constraints, max_paths)
            print(f"    Generated {len(paths)} paths")
            
            for idx, path in enumerate(paths):
                sol = path.solve()
                if sol:
                    data = self._sol_to_bytes(sol, func_data)
                    path_file = os.path.join(output_dir, f"{func}_p{idx}.bin")
                    with open(path_file, 'wb') as f: f.write(data)
                    count += 1
        
        print(f"\n[+] Generated {count} inputs")
        return count
    
    def _gen_paths(self, constraints, max_paths):
        """Generate path permutations"""
        paths = [ExecutionPath(constraints[:])]
        
        for i, c in enumerate(constraints):
            if len(paths) >= max_paths: break
            neg = self._negate(c)
            paths.append(ExecutionPath(constraints[:i] + [neg]))
        
        return paths
    
    def _negate(self, c):
        """Negate constraint"""
        neg_map = {
            ConstraintType.EQ: ConstraintType.NEQ,
            ConstraintType.NEQ: ConstraintType.EQ,
            ConstraintType.LT: ConstraintType.GE,
            ConstraintType.GT: ConstraintType.LE,
            ConstraintType.LE: ConstraintType.GT,
            ConstraintType.GE: ConstraintType.LT,
        }
        new_type = neg_map.get(c.constraint_type, c.constraint_type)
        return PathConstraint(c.var_name, new_type, c.value, c.location)
    
    def _sol_to_bytes(self, solution, func_data):
        """Convert solution to binary"""
        buf = bytearray(4096)
        offset = 0
        
        for arg_name, arg_info in func_data.get('Arguments', {}).items():
            if arg_info.get('arg_dir') != 'IN': continue
            
            var = arg_info.get('variable', '')
            arg_type = arg_info.get('arg_type', '')
            
            if var in solution:
                val = solution[var]
                # Pack based on type
                if '64' in arg_type:
                    struct.pack_into('<Q', buf, offset, val & 0xFFFFFFFFFFFFFFFF)
                    offset += 8
                elif '32' in arg_type:
                    struct.pack_into('<I', buf, offset, val & 0xFFFFFFFF)
                    offset += 4
                elif '16' in arg_type:
                    struct.pack_into('<H', buf, offset, val & 0xFFFF)
                    offset += 2
                elif '8' in arg_type:
                    struct.pack_into('<B', buf, offset, val & 0xFF)
                    offset += 1
                else:
                    struct.pack_into('<I', buf, offset, val & 0xFFFFFFFF)
                    offset += 4
            else:
                offset += 8
        
        return bytes(buf[:max(offset, 1024)])
    
    def add_hints(self, func_name, constraints):
        """Add manual constraint hints"""
        self.constraint_cache[func_name] = constraints

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--firness-json', required=True)
    parser.add_argument('-o', '--output-dir', default='concolic_inputs')
    parser.add_argument('-m', '--max-paths', type=int, default=100)
    args = parser.parse_args()
    
    engine = ConcolicEngine(args.firness_json)
    
    # Add hints for known problematic functions from paper
    engine.add_hints("EfiPxeBcUdpRead", [
        PathConstraint("This", ConstraintType.NULL),
        PathConstraint("OpFlags", ConstraintType.FLAG, 0x01),
        PathConstraint("DestPort", ConstraintType.NULL),
        PathConstraint("BufferSize", ConstraintType.NULL),
    ])
    
    engine.add_hints("Ip4PreProcessPacket", [
        PathConstraint("BufferSize", ConstraintType.GT, 0),
        PathConstraint("HeaderLength", ConstraintType.LE, 60),
    ])
    
    count = engine.generate_inputs(args.output_dir, args.max_paths)
    print(f"[+] Run with: ./simics -no-win -no-gui fuzz.simics")
    return 0

if __name__ == '__main__':
    sys.exit(main())
