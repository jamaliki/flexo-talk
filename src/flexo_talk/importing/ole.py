# Adapted from DeckWerk's importers/pptx/import_pptx.py (compound_file_streams, embedded_pdf),
# by Vincent Sitzmann, under the MIT License: Copyright (c) 2026 Vincent Sitzmann. Its full text
# is in LICENSE-DeckWerk beside this file. Flexo's changes are under the Apache License 2.0, as
# the rest of it.
"""An object embedded in a PowerPoint deck (OLE): the PDF it holds, read as Flexo reads PDFs.

An embedded object is an OLE compound file (MS-CFB). Acrobat keeps the whole document in a
stream named CONTENTS; the generic packager (``\\x01Ole10Native``) keeps a short header and
then the file. Either way the PDF is the stream from its ``%PDF-`` on. Only reading is needed:
the FAT, the mini FAT and the directory, and nothing else; a damaged file is no PDF.
"""

from __future__ import annotations

SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
END_OF_CHAIN = 0xFFFFFFFE
MOST_SECTORS = 1 << 22
"""More sectors than any embedded object has: a chain past it is a damaged file."""


def streams(raw: bytes) -> list[tuple[str, bytes]]:
    """Every stream in a compound file, as (name, data); ``ValueError`` for a damaged one."""

    def u16(offset: int) -> int:
        return int.from_bytes(raw[offset : offset + 2], "little")

    def u32(offset: int) -> int:
        return int.from_bytes(raw[offset : offset + 4], "little")

    if not raw.startswith(SIGNATURE) or len(raw) < 512:
        raise ValueError("not a compound file")
    shift, mini_shift = u16(0x1E), u16(0x20)
    if not 7 <= shift <= 16 or not 2 <= mini_shift <= shift:
        raise ValueError("odd sector sizes")
    sector, mini_sector = 1 << shift, 1 << mini_shift
    mini_cutoff = u32(0x38)

    def sector_data(index: int) -> bytes:
        start = (index + 1) * sector
        if start + sector > len(raw):
            raise ValueError("sector out of range")
        return raw[start : start + sector]

    def table(data: bytes) -> list[int]:
        return [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data), 4)]

    def chain(start: int, fat: list[int]) -> list[int]:
        out: list[int] = []
        while start != END_OF_CHAIN:
            if start >= len(fat) or len(out) > min(len(fat), MOST_SECTORS):
                raise ValueError("broken sector chain")
            out.append(start)
            start = fat[start]
        return out

    fat_sectors = [s for s in table(raw[0x4C:0x200]) if s < END_OF_CHAIN]
    difat, seen = u32(0x44), set()
    while difat < END_OF_CHAIN and difat not in seen:
        seen.add(difat)
        entries = table(sector_data(difat))
        fat_sectors.extend(s for s in entries[:-1] if s < END_OF_CHAIN)
        difat = entries[-1]
    fat = [entry for s in fat_sectors for entry in table(sector_data(s))]

    def read_chain(start: int) -> bytes:
        return b"".join(sector_data(s) for s in chain(start, fat))

    directory = read_chain(u32(0x30))
    entries = [directory[i : i + 128] for i in range(0, len(directory) - 127, 128)]
    if not entries:
        raise ValueError("empty directory")
    mini_stream = read_chain(int.from_bytes(entries[0][0x74:0x78], "little"))
    first_mini_fat = u32(0x3C)
    mini_fat = table(read_chain(first_mini_fat)) if first_mini_fat < END_OF_CHAIN else []
    found: list[tuple[str, bytes]] = []
    for entry in entries:
        if entry[0x42] != 2:  # a stream, not a storage or the root
            continue
        length = int.from_bytes(entry[0x40:0x42], "little")
        name = entry[: max(0, min(length, 64) - 2)].decode("utf-16-le", "replace")
        start = int.from_bytes(entry[0x74:0x78], "little")
        size = int.from_bytes(entry[0x78:0x80], "little")
        if sector == 512:
            size &= 0xFFFFFFFF  # version 3 files leave the high half undefined
        if size < mini_cutoff:
            data = b"".join(mini_stream[s * mini_sector : (s + 1) * mini_sector] for s in chain(start, mini_fat))
        else:
            data = read_chain(start)
        found.append((name, data[:size]))
    return found


def embedded_pdf(raw: bytes) -> bytes | None:
    """The PDF inside an embedded object's data, if it holds one."""

    if raw.startswith(b"%PDF-"):
        return raw
    if not raw.startswith(SIGNATURE):
        return None
    try:
        for _name, data in streams(raw):
            at = data.find(b"%PDF-", 0, 1024)
            if at >= 0:
                return data[at:]
    except (ValueError, IndexError):
        return None
    return None
