#!/usr/bin/env python3
"""
Protocol-Specific Mutators for FuzzUEr
Implements custom mutation strategies for different protocol categories
Addresses the limitation of generic mutations not understanding protocol semantics
"""

import os, sys, struct, random
from typing import List, Tuple
from enum import Enum

class ProtocolCategory(Enum):
    NETWORK = "network"
    USB = "usb"
    STORAGE = "storage"
    DISPLAY = "display"
    SECURITY = "security"

class ProtocolMutator:
    """Base class for protocol-specific mutations"""
    
    def __init__(self, seed=None):
        self.random = random.Random(seed)
    
    def mutate(self, data: bytes) -> bytes:
        """Override in subclasses"""
        return data
    
    def _flip_bit(self, data: bytearray, pos: int):
        """Flip a single bit"""
        byte_pos = pos // 8
        bit_pos = pos % 8
        if byte_pos < len(data):
            data[byte_pos] ^= (1 << bit_pos)
    
    def _flip_byte(self, data: bytearray, pos: int):
        """Flip entire byte"""
        if pos < len(data):
            data[pos] ^= 0xFF
    
    def _insert_interesting(self, data: bytearray, pos: int, value: int, size: int):
        """Insert interesting value"""
        if pos + size <= len(data):
            if size == 1:
                struct.pack_into('<B', data, pos, value & 0xFF)
            elif size == 2:
                struct.pack_into('<H', data, pos, value & 0xFFFF)
            elif size == 4:
                struct.pack_into('<I', data, pos, value & 0xFFFFFFFF)
            elif size == 8:
                struct.pack_into('<Q', data, pos, value & 0xFFFFFFFFFFFFFFFF)

class NetworkMutator(ProtocolMutator):
    """Mutations for Network protocols (IP4, IP6, TCP, UDP, etc.)"""
    
    # Network-specific interesting values
    INTERESTING_PORTS = [0, 21, 22, 23, 25, 53, 80, 443, 8080, 65535]
    INTERESTING_IPS = [
        0x00000000,  # 0.0.0.0
        0x7F000001,  # 127.0.0.1
        0xFFFFFFFF,  # 255.255.255.255
        0xC0A80001,  # 192.168.0.1
        0x08080808,  # 8.8.8.8
    ]
    INTERESTING_SIZES = [0, 1, 64, 512, 1024, 1500, 8192, 65535, 0xFFFFFFFF]
    INVALID_CHECKSUMS = [0x0000, 0xFFFF, 0x1234]
    
    def mutate(self, data: bytes) -> bytes:
        """Network-aware mutations"""
        data = bytearray(data)
        
        mutation = self.random.choice([
            self._mutate_ip_header,
            self._mutate_port,
            self._mutate_packet_size,
            self._mutate_checksum,
            self._mutate_flags,
            self._fragment_packet,
        ])
        
        mutation(data)
        return bytes(data)
    
    def _mutate_ip_header(self, data: bytearray):
        """Mutate IP header fields"""
        if len(data) < 20: return
        
        # Version/IHL (byte 0)
        data[0] = self.random.choice([0x45, 0x46, 0x4F, 0x00, 0xFF])
        
        # Total Length (bytes 2-3) - often triggers buffer overflows
        size = self.random.choice(self.INTERESTING_SIZES)
        struct.pack_into('>H', data, 2, size & 0xFFFF)
        
        # TTL (byte 8)
        data[8] = self.random.choice([0, 1, 64, 128, 255])
        
        # Protocol (byte 9)
        data[9] = self.random.choice([1, 6, 17, 255])  # ICMP, TCP, UDP, invalid
        
        # Source/Dest IP (bytes 12-19)
        if self.random.random() < 0.3:
            ip = self.random.choice(self.INTERESTING_IPS)
            struct.pack_into('>I', data, 12, ip)
        if self.random.random() < 0.3:
            ip = self.random.choice(self.INTERESTING_IPS)
            struct.pack_into('>I', data, 16, ip)
    
    def _mutate_port(self, data: bytearray):
        """Mutate port numbers"""
        if len(data) < 24: return
        
        # Assume ports at offset 20-24 (after IP header)
        port = self.random.choice(self.INTERESTING_PORTS)
        struct.pack_into('>H', data, 20, port)
        struct.pack_into('>H', data, 22, port)
    
    def _mutate_packet_size(self, data: bytearray):
        """Mutate packet size fields"""
        size = self.random.choice(self.INTERESTING_SIZES)
        
        # Try multiple offsets where size might be
        for offset in [2, 4, 6, 8]:
            if offset + 2 <= len(data):
                struct.pack_into('>H', data, offset, size & 0xFFFF)
                break
    
    def _mutate_checksum(self, data: bytearray):
        """Corrupt checksums to test error handling"""
        for offset in [10, 16, 24]:  # Common checksum offsets
            if offset + 2 <= len(data):
                chk = self.random.choice(self.INVALID_CHECKSUMS)
                struct.pack_into('>H', data, offset, chk)
    
    def _mutate_flags(self, data: bytearray):
        """Mutate flag fields"""
        if len(data) < 14: return
        
        # IP flags (byte 6-7)
        data[6] = self.random.choice([0x00, 0x20, 0x40, 0x60, 0xFF])
        
        # TCP flags if present (byte 33)
        if len(data) >= 34:
            data[33] = self.random.choice([0x00, 0x02, 0x10, 0x18, 0xFF])
    
    def _fragment_packet(self, data: bytearray):
        """Create fragmented packet scenarios"""
        if len(data) < 20: return
        
        # Set fragment offset
        frag_offset = self.random.randint(0, 8191)
        data[6] = (data[6] & 0xE0) | ((frag_offset >> 8) & 0x1F)
        data[7] = frag_offset & 0xFF

class USBMutator(ProtocolMutator):
    """Mutations for USB protocols"""
    
    INTERESTING_ENDPOINTS = [0, 1, 15, 16, 255]
    INTERESTING_LENGTHS = [0, 1, 8, 64, 512, 1024, 0xFFFF]
    USB_REQUESTS = [0x00, 0x05, 0x06, 0x09, 0xFF]  # GET_STATUS, SET_ADDRESS, GET_DESCRIPTOR, SET_CONFIGURATION
    
    def mutate(self, data: bytes) -> bytes:
        data = bytearray(data)
        
        mutation = self.random.choice([
            self._mutate_endpoint,
            self._mutate_transfer_length,
            self._mutate_request_type,
            self._mutate_device_address,
        ])
        
        mutation(data)
        return bytes(data)
    
    def _mutate_endpoint(self, data: bytearray):
        """Mutate endpoint numbers"""
        if len(data) < 4: return
        data[0] = self.random.choice(self.INTERESTING_ENDPOINTS)
    
    def _mutate_transfer_length(self, data: bytearray):
        """Mutate transfer lengths"""
        if len(data) < 8: return
        length = self.random.choice(self.INTERESTING_LENGTHS)
        struct.pack_into('<I', data, 4, length)
    
    def _mutate_request_type(self, data: bytearray):
        """Mutate USB request types"""
        if len(data) < 2: return
        data[1] = self.random.choice(self.USB_REQUESTS)
    
    def _mutate_device_address(self, data: bytearray):
        """Mutate device addresses"""
        if len(data) < 3: return
        data[2] = self.random.choice([0, 1, 127, 128, 255])

class StorageMutator(ProtocolMutator):
    """Mutations for Storage protocols (DISK_IO, IDE, SD_MMC, etc.)"""
    
    INTERESTING_LBAS = [0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
    INTERESTING_BLOCK_SIZES = [0, 1, 512, 1024, 2048, 4096, 8192, 0xFFFFFFFF]
    
    def mutate(self, data: bytes) -> bytes:
        data = bytearray(data)
        
        mutation = self.random.choice([
            self._mutate_lba,
            self._mutate_block_size,
            self._mutate_block_count,
            self._mutate_media_id,
        ])
        
        mutation(data)
        return bytes(data)
    
    def _mutate_lba(self, data: bytearray):
        """Mutate Logical Block Address"""
        if len(data) < 8: return
        lba = self.random.choice(self.INTERESTING_LBAS)
        struct.pack_into('<Q', data, 0, lba)
    
    def _mutate_block_size(self, data: bytearray):
        """Mutate block size"""
        if len(data) < 12: return
        size = self.random.choice(self.INTERESTING_BLOCK_SIZES)
        struct.pack_into('<I', data, 8, size)
    
    def _mutate_block_count(self, data: bytearray):
        """Mutate block count"""
        if len(data) < 16: return
        count = self.random.choice([0, 1, 256, 1024, 0xFFFFFFFF])
        struct.pack_into('<I', data, 12, count)
    
    def _mutate_media_id(self, data: bytearray):
        """Mutate media ID"""
        if len(data) < 20: return
        media_id = self.random.choice([0, 1, 0xDEADBEEF, 0xFFFFFFFF])
        struct.pack_into('<I', data, 16, media_id)

class DisplayMutator(ProtocolMutator):
    """Mutations for Graphics/Display protocols"""
    
    INTERESTING_COORDS = [0, 1, 640, 1024, 1920, 0x7FFF, 0xFFFF, 0xFFFFFFFF]
    INTERESTING_COLORS = [0x00000000, 0xFFFFFFFF, 0xFF0000, 0x00FF00, 0x0000FF]
    
    def mutate(self, data: bytes) -> bytes:
        data = bytearray(data)
        
        mutation = self.random.choice([
            self._mutate_coordinates,
            self._mutate_dimensions,
            self._mutate_color,
            self._mutate_pixel_format,
        ])
        
        mutation(data)
        return bytes(data)
    
    def _mutate_coordinates(self, data: bytearray):
        """Mutate X/Y coordinates - triggers bounds checks"""
        if len(data) < 8: return
        x = self.random.choice(self.INTERESTING_COORDS)
        y = self.random.choice(self.INTERESTING_COORDS)
        struct.pack_into('<I', data, 0, x)
        struct.pack_into('<I', data, 4, y)
    
    def _mutate_dimensions(self, data: bytearray):
        """Mutate width/height"""
        if len(data) < 16: return
        w = self.random.choice(self.INTERESTING_COORDS)
        h = self.random.choice(self.INTERESTING_COORDS)
        struct.pack_into('<I', data, 8, w)
        struct.pack_into('<I', data, 12, h)
    
    def _mutate_color(self, data: bytearray):
        """Mutate color values"""
        if len(data) < 20: return
        color = self.random.choice(self.INTERESTING_COLORS)
        struct.pack_into('<I', data, 16, color)
    
    def _mutate_pixel_format(self, data: bytearray):
        """Mutate pixel format enum"""
        if len(data) < 24: return
        fmt = self.random.choice([0, 1, 2, 3, 255])
        struct.pack_into('<I', data, 20, fmt)

class MutatorFactory:
    """Factory for creating protocol-specific mutators"""
    
    PROTOCOL_MAP = {
        # Network protocols
        'gEfiIp4ProtocolGuid': NetworkMutator,
        'gEfiIp6ProtocolGuid': NetworkMutator,
        'gEfiTcp4ProtocolGuid': NetworkMutator,
        'gEfiUdp4ProtocolGuid': NetworkMutator,
        'gEfiSimpleNetworkProtocolGuid': NetworkMutator,
        'gEfiManagedNetworkProtocolGuid': NetworkMutator,
        
        # USB protocols
        'gEfiUsbIoProtocolGuid': USBMutator,
        'gEfiUsb2HcProtocolGuid': USBMutator,
        
        # Storage protocols
        'gEfiDiskIoProtocolGuid': StorageMutator,
        'gEfiBlockIoProtocolGuid': StorageMutator,
        'gEfiIdeControllerInitProtocolGuid': StorageMutator,
        'gEfiSdMmcPassThruProtocolGuid': StorageMutator,
        
        # Display protocols
        'gEfiGraphicsOutputProtocolGuid': DisplayMutator,
        'gEfiHiiFontProtocolGuid': DisplayMutator,
    }
    
    @staticmethod
    def create_mutator(protocol_guid: str, seed=None) -> ProtocolMutator:
        """Create mutator for protocol"""
        mutator_class = MutatorFactory.PROTOCOL_MAP.get(
            protocol_guid, ProtocolMutator
        )
        return mutator_class(seed)
    
    @staticmethod
    def mutate_input(protocol_guid: str, data: bytes, iterations: int = 1) -> List[bytes]:
        """Generate mutated inputs"""
        mutator = MutatorFactory.create_mutator(protocol_guid)
        mutations = []
        
        for i in range(iterations):
            mutated = mutator.mutate(data)
            mutations.append(mutated)
            data = mutated  # Chain mutations
        
        return mutations

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Protocol-specific mutator')
    parser.add_argument('-p', '--protocol', required=True, help='Protocol GUID')
    parser.add_argument('-i', '--input', required=True, help='Input file')
    parser.add_argument('-o', '--output-dir', default='mutated_inputs')
    parser.add_argument('-n', '--num-mutations', type=int, default=100)
    args = parser.parse_args()
    
    # Read input
    with open(args.input, 'rb') as f:
        data = f.read()
    
    # Generate mutations
    os.makedirs(args.output_dir, exist_ok=True)
    mutations = MutatorFactory.mutate_input(
        args.protocol, data, args.num_mutations
    )
    
    # Write mutations
    for i, mutated in enumerate(mutations):
        out_file = os.path.join(args.output_dir, f"mutation_{i:04d}.bin")
        with open(out_file, 'wb') as f:
            f.write(mutated)
    
    print(f"[+] Generated {len(mutations)} protocol-specific mutations")
    return 0

if __name__ == '__main__':
    sys.exit(main())
