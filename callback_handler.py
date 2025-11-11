#!/usr/bin/env python3
"""
Callback Support Module for FuzzUEr
Addresses limitation in Section VI-B5: lack of callback parameter support
Generates callback stubs for protocols like USB2_HC
"""

import os, sys, json, re
from typing import Dict, List, Set

class CallbackHandler:
    """Generates callback stubs for UEFI protocols"""
    
    CALLBACK_PATTERNS = [
        # Common UEFI callback signatures
        r'typedef\s+EFI_STATUS\s*\(EFIAPI\s*\*(\w+)\)\s*\((.*?)\)',
        r'typedef\s+VOID\s*\(EFIAPI\s*\*(\w+)\)\s*\((.*?)\)',
        r'EFI_\w+_CALLBACK',
    ]
    
    def __init__(self, edk2_root: str):
        self.edk2_root = edk2_root
        self.detected_callbacks = {}
        self.stub_templates = {}
        
    def detect_callbacks(self, firness_json: str) -> Dict[str, List]:
        """Detect callback parameters in FIRNESS analysis"""
        with open(firness_json) as f:
            data = json.load(f)
        
        callbacks = {}
        for func_entry in data:
            func_name = func_entry.get('Function', '')
            for arg_name, arg_info in func_entry.get('Arguments', {}).items():
                arg_type = arg_info.get('arg_type', '')
                
                # Detect callback types
                if 'CALLBACK' in arg_type or '_FUNC' in arg_type or 'EFIAPI' in arg_type:
                    if func_name not in callbacks:
                        callbacks[func_name] = []
                    callbacks[func_name].append({
                        'arg_name': arg_name,
                        'arg_type': arg_type,
                        'param_type': arg_info.get('param_type', '')
                    })
        
        self.detected_callbacks = callbacks
        return callbacks
    
    def generate_stub(self, callback_type: str) -> str:
        """Generate C callback stub"""
        # Parse callback signature
        if 'EFI_STATUS' in callback_type:
            return_type = 'EFI_STATUS'
            default_return = 'return EFI_SUCCESS;'
        elif 'VOID' in callback_type:
            return_type = 'VOID'
            default_return = 'return;'
        else:
            return_type = 'VOID'
            default_return = 'return;'
        
        stub_code = f"""
// Auto-generated callback stub for {callback_type}
{return_type}
EFIAPI
FuzzCallbackStub_{callback_type.replace('*', '_PTR')}(
    IN VOID *Context
)
{{
    // Log callback invocation for coverage
    DEBUG((DEBUG_INFO, "Callback invoked: {callback_type}\\n"));
    
    // Record callback was called (for state tracking)
    if (Context != NULL) {{
        CALLBACK_CONTEXT *Ctx = (CALLBACK_CONTEXT *)Context;
        Ctx->CallbackInvoked = TRUE;
        Ctx->InvocationCount++;
    }}
    
    {default_return}
}}
"""
        return stub_code
    
    def generate_callback_context(self) -> str:
        """Generate context structure for callback tracking"""
        return """
// Callback tracking context
typedef struct {
    BOOLEAN     CallbackInvoked;
    UINTN       InvocationCount;
    VOID        *UserData;
    EFI_STATUS  LastStatus;
} CALLBACK_CONTEXT;

static CALLBACK_CONTEXT gCallbackContexts[32];
static UINTN gCallbackContextCount = 0;

CALLBACK_CONTEXT*
AllocateCallbackContext(VOID)
{
    if (gCallbackContextCount >= 32) {
        return NULL;
    }
    
    CALLBACK_CONTEXT *Ctx = &gCallbackContexts[gCallbackContextCount++];
    Ctx->CallbackInvoked = FALSE;
    Ctx->InvocationCount = 0;
    Ctx->UserData = NULL;
    Ctx->LastStatus = EFI_SUCCESS;
    
    return Ctx;
}
"""
    
    def enhance_harness(self, harness_file: str, output_file: str):
        """Enhance existing harness with callback support"""
        with open(harness_file) as f:
            harness_content = f.read()
        
        # Add callback context definition
        enhanced = "// Enhanced with callback support\n"
        enhanced += "#include <Library/DebugLib.h>\n\n"
        enhanced += self.generate_callback_context()
        enhanced += "\n"
        
        # Generate stubs for all detected callbacks
        for func_name, callbacks in self.detected_callbacks.items():
            for cb_info in callbacks:
                stub = self.generate_stub(cb_info['arg_type'])
                enhanced += stub + "\n"
        
        # Modify original harness to use callback stubs
        enhanced += "\n// Original harness code with callback modifications:\n"
        enhanced += self._inject_callback_usage(harness_content)
        
        with open(output_file, 'w') as f:
            f.write(enhanced)
        
        print(f"[+] Enhanced harness written to {output_file}")
        return output_file
    
    def _inject_callback_usage(self, harness_content: str) -> str:
        """Inject callback stub usage into harness"""
        # Find NULL callback assignments and replace with stubs
        modified = harness_content
        
        for func_name, callbacks in self.detected_callbacks.items():
            for cb_info in callbacks:
                arg_name = cb_info['arg_name']
                arg_type = cb_info['arg_type']
                
                # Pattern: SomeCallback = NULL;
                null_pattern = rf'({arg_name}\s*=\s*)NULL;'
                stub_name = f"FuzzCallbackStub_{arg_type.replace('*', '_PTR')}"
                replacement = rf'\1{stub_name};'
                
                modified = re.sub(null_pattern, replacement, modified)
                
                # Also allocate context
                # Find function call and insert context allocation before it
                func_call_pattern = rf'(Status\s*=\s*ProtocolVariable->{func_name}\s*\()'
                context_alloc = r"""
    // Allocate callback context
    CALLBACK_CONTEXT *CallbackCtx = AllocateCallbackContext();
    
\1"""
                modified = re.sub(func_call_pattern, context_alloc, modified, count=1)
        
        return modified
    
    def generate_callback_fuzzer(self, output_file: str):
        """Generate standalone callback fuzzer for testing"""
        code = """
// Callback Fuzzing Helper
// Tests callback behavior under various conditions

#include <Uefi.h>
#include <Library/UefiLib.h>
#include <Library/MemoryAllocationLib.h>

// Include callback stubs
""" + self.generate_callback_context()
        
        for func_name, callbacks in self.detected_callbacks.items():
            for cb_info in callbacks:
                code += self.generate_stub(cb_info['arg_type'])
        
        code += """
// Test callback invocation
EFI_STATUS
EFIAPI
TestCallbacks(VOID)
{
    EFI_STATUS Status;
    CALLBACK_CONTEXT *Ctx;
    
    // Test each callback
    Print(L"Testing callbacks...\\n");
    
"""
        
        for func_name, callbacks in self.detected_callbacks.items():
            for cb_info in callbacks:
                stub_name = f"FuzzCallbackStub_{cb_info['arg_type'].replace('*', '_PTR')}"
                code += f"""
    Ctx = AllocateCallbackContext();
    {stub_name}(Ctx);
    Print(L"  {stub_name}: Invoked=%d\\n", Ctx->CallbackInvoked);
"""
        
        code += """
    return EFI_SUCCESS;
}
"""
        
        with open(output_file, 'w') as f:
            f.write(code)
        
        print(f"[+] Callback fuzzer written to {output_file}")
        return output_file

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Callback handler for FuzzUEr')
    parser.add_argument('-f', '--firness-json', required=True)
    parser.add_argument('-e', '--edk2-root', default='/input/edk2')
    parser.add_argument('-i', '--input-harness', required=True)
    parser.add_argument('-o', '--output-harness', required=True)
    parser.add_argument('--gen-fuzzer', help='Generate standalone callback fuzzer')
    args = parser.parse_args()
    
    handler = CallbackHandler(args.edk2_root)
    
    # Detect callbacks
    callbacks = handler.detect_callbacks(args.firness_json)
    print(f"[*] Detected {len(callbacks)} functions with callbacks")
    for func, cbs in callbacks.items():
        print(f"    {func}: {len(cbs)} callback(s)")
    
    # Enhance harness
    handler.enhance_harness(args.input_harness, args.output_harness)
    
    # Generate standalone fuzzer if requested
    if args.gen_fuzzer:
        handler.generate_callback_fuzzer(args.gen_fuzzer)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
