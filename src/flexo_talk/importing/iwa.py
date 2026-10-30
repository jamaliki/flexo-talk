"""Keynote's file format read (and, for tests, written): IWA streams of Snappy-compressed
protobuf messages, with no library beyond Python's own.

A ``.key`` holds ``Index/*.iwa`` files. Each is a run of chunks -- a zero byte, a three-byte
length, and that many bytes of Snappy-compressed data (with no checksum, as Apple writes it).
Uncompressed, the chunks are a run of archives: a length (a varint), a ``TSP.ArchiveInfo``
naming an object's id and, for each of its messages, the message's type and length, then the
messages themselves. Each object here is its first message: its type (a number Keynote
registers each message type under) and its fields.

A message is read as protobuf's wire format says, with no schema: ``Message`` gives a field's
value by its number, as the kind the reader asks for (``int``, ``float``, ``text``, a message
in it). The numbers of the fields this importer reads are Keynote's own, as its schemas give
them (``flexo_talk.importing.keynote`` names each).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field

LARGEST = 512 * 1024 * 1024
"""More bytes than any Keynote stream holds uncompressed: one saying it holds more is damaged."""


class Damaged(ValueError):
    """A stream that is not what it says it is."""


# -- Snappy ---------------------------------------------------------------------------------------


def unsnappy(data: bytes | memoryview) -> bytes:
    """Snappy's raw format, uncompressed."""

    data = memoryview(data)
    size, at = _varint(data, 0)
    if size > LARGEST:
        raise Damaged("too large")
    out = bytearray()
    end = len(data)
    while at < end:
        tag = data[at]
        at += 1
        kind = tag & 3
        if kind == 0:
            length = tag >> 2
            if length >= 60:
                count = length - 59
                length = int.from_bytes(data[at : at + count], "little")
                at += count
            length += 1
            if at + length > end:
                raise Damaged("literal past the end")
            out += data[at : at + length]
            at += length
            continue
        if kind == 1:
            length = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | data[at]
            at += 1
        elif kind == 2:
            length = (tag >> 2) + 1
            offset = int.from_bytes(data[at : at + 2], "little")
            at += 2
        else:
            length = (tag >> 2) + 1
            offset = int.from_bytes(data[at : at + 4], "little")
            at += 4
        if offset == 0 or offset > len(out):
            raise Damaged("copy before the start")
        start = len(out) - offset
        if offset >= length:
            out += out[start : start + length]
        else:
            # (An overlapping copy repeats what it starts from.)
            pattern = bytes(out[start:])
            whole, part = divmod(length, offset)
            out += pattern * whole + pattern[:part]
    if len(out) != size:
        raise Damaged("length is not as said")
    return bytes(out)


def snappy(data: bytes) -> bytes:
    """Bytes in Snappy's raw format: literals only (as valid as compressed, if larger)."""

    out = bytearray(_encoded_varint(len(data)))
    for at in range(0, len(data), 65536):
        piece = data[at : at + 65536]
        length = len(piece) - 1
        if length < 60:
            out.append(length << 2)
        else:
            count = (length.bit_length() + 7) // 8
            out.append((59 + count) << 2)
            out += length.to_bytes(count, "little")
        out += piece
    return bytes(out)


# -- protobuf's wire format ---------------------------------------------------------------------


def _varint(data: memoryview | bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if at >= len(data):
            raise Damaged("varint past the end")
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > 70:
            raise Damaged("varint too long")


def _encoded_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


class Message:
    """A protobuf message read without its schema: each field's raw values, by number. Read
    when first asked."""

    __slots__ = ("_data", "_fields")

    def __init__(self, data: bytes | memoryview = b"") -> None:
        self._data = data
        self._fields: dict[int, list] | None = None

    def fields(self) -> dict[int, list]:
        if self._fields is None:
            found: dict[int, list] = {}
            data = memoryview(self._data)
            at, end = 0, len(data)
            while at < end:
                key, at = _varint(data, at)
                number, wire = key >> 3, key & 7
                if wire == 0:
                    value, at = _varint(data, at)
                elif wire == 1:
                    value = (1, data[at : at + 8])
                    at += 8
                elif wire == 2:
                    length, at = _varint(data, at)
                    if at + length > end:
                        raise Damaged("field past the end")
                    value = data[at : at + length]
                    at += length
                elif wire == 5:
                    value = (5, data[at : at + 4])
                    at += 4
                else:
                    raise Damaged(f"wire type {wire}")
                found.setdefault(number, []).append(value)
            self._fields = found
        return self._fields

    def has(self, number: int) -> bool:
        return number in self.fields()

    def _first(self, number: int):
        values = self.fields().get(number)
        return values[-1] if values else None

    def int(self, number: int, default: int | None = None) -> int | None:
        value = self._first(number)
        if value is None:
            return default
        if isinstance(value, int):
            return value - (1 << 64) if value >= 1 << 63 else value
        if isinstance(value, tuple):
            return int.from_bytes(value[1], "little")
        return default

    def bool(self, number: int, default: bool = False) -> bool:
        value = self.int(number)
        return default if value is None else bool(value)

    def float(self, number: int, default: float | None = None) -> float | None:
        value = self._first(number)
        if isinstance(value, tuple):
            kind, raw = value
            return struct.unpack("<f" if kind == 5 else "<d", raw)[0]
        if isinstance(value, int):
            return float(value)
        return default

    def text(self, number: int, default: str | None = None) -> str | None:
        value = self._first(number)
        if isinstance(value, memoryview | bytes):
            return bytes(value).decode("utf-8", "replace")
        return default

    def texts(self, number: int) -> list[str]:
        return [bytes(value).decode("utf-8", "replace") for value in self.fields().get(number, [])
                if isinstance(value, memoryview | bytes)]

    def bytes(self, number: int) -> bytes | None:
        value = self._first(number)
        return bytes(value) if isinstance(value, memoryview | bytes) else None

    def message(self, number: int) -> Message | None:
        value = self._first(number)
        return Message(value) if isinstance(value, memoryview | bytes) else None

    def messages(self, number: int) -> list[Message]:
        return [Message(value) for value in self.fields().get(number, []) if isinstance(value, memoryview | bytes)]

    def ints(self, number: int) -> list[int]:
        """A repeated whole-number field, packed or not."""

        out: list[int] = []
        for value in self.fields().get(number, []):
            if isinstance(value, int):
                out.append(value)
            elif isinstance(value, memoryview | bytes):
                at = 0
                while at < len(value):
                    item, at = _varint(value, at)
                    out.append(item)
        return out

    def floats(self, number: int) -> list[float]:
        """A repeated float field, packed or not."""

        out: list[float] = []
        for value in self.fields().get(number, []):
            if isinstance(value, tuple):
                out.append(struct.unpack("<f" if value[0] == 5 else "<d", value[1])[0])
            elif isinstance(value, memoryview | bytes):
                raw = bytes(value)
                out.extend(struct.unpack(f"<{len(raw) // 4}f", raw[: len(raw) // 4 * 4]))
        return out

    def reference(self, number: int) -> int | None:
        """A ``TSP.Reference`` field: the id of the object it names."""

        found = self.message(number)
        return found.int(1) if found is not None else None

    def references(self, number: int) -> list[int]:
        return [ident for ident in (found.int(1) for found in self.messages(number)) if ident]


# -- writing messages (for tests) -----------------------------------------------------------------


class Builder:
    """A protobuf message written field by field: ``Builder().int(1, 5).message(2, other)``."""

    def __init__(self) -> None:
        self.out = bytearray()

    def _key(self, number: int, wire: int) -> None:
        self.out += _encoded_varint(number << 3 | wire)

    def int(self, number: int, value: int) -> Builder:
        self._key(number, 0)
        self.out += _encoded_varint(int(value))
        return self

    def bool(self, number: int, value: bool) -> Builder:
        return self.int(number, 1 if value else 0)

    def float(self, number: int, value: float) -> Builder:
        self._key(number, 5)
        self.out += struct.pack("<f", float(value))
        return self

    def double(self, number: int, value: float) -> Builder:
        self._key(number, 1)
        self.out += struct.pack("<d", float(value))
        return self

    def raw(self, number: int, value: bytes) -> Builder:
        self._key(number, 2)
        self.out += _encoded_varint(len(value)) + value
        return self

    def text(self, number: int, value: str) -> Builder:
        return self.raw(number, value.encode("utf-8"))

    def message(self, number: int, value: Builder | bytes) -> Builder:
        return self.raw(number, bytes(value.out if isinstance(value, Builder) else value))

    def reference(self, number: int, ident: int) -> Builder:
        return self.message(number, Builder().int(1, ident))

    def packed(self, number: int, values: list[int]) -> Builder:
        return self.raw(number, b"".join(_encoded_varint(value) for value in values))

    def __bytes__(self) -> bytes:
        return bytes(self.out)


# -- archives -----------------------------------------------------------------------------------


@dataclass
class Archive:
    """One object of a document: its id, its message's type, and the message."""

    ident: int
    type: int
    message: Message
    references: list[int] = field(default_factory=list)


def chunks(data: bytes) -> Iterator[bytes]:
    """An IWA file's chunks, uncompressed."""

    at, end = 0, len(data)
    while at < end:
        if at + 4 > end:
            raise Damaged("chunk header past the end")
        if data[at] != 0:
            raise Damaged("not a Snappy chunk")
        length = int.from_bytes(data[at + 1 : at + 4], "little")
        at += 4
        if at + length > end:
            raise Damaged("chunk past the end")
        yield unsnappy(memoryview(data)[at : at + length])
        at += length


def archives(data: bytes) -> Iterator[Archive]:
    """The objects an IWA file holds, each its first message (the object itself)."""

    stream = b"".join(chunks(data))
    view = memoryview(stream)
    at, end = 0, len(view)
    while at < end:
        length, at = _varint(view, at)
        info = Message(view[at : at + length])
        at += length
        ident = info.int(1) or 0
        first: Archive | None = None
        for item in info.messages(2):
            size = item.int(3) or 0
            payload = view[at : at + size]
            at += size
            if first is None:
                first = Archive(ident, item.int(1) or 0, Message(payload), item.ints(5))
        if first is not None and ident:
            yield first


def write_archives(objects: list[tuple[int, int, bytes]]) -> bytes:
    """An IWA file of ``(id, type, message)``, as Keynote would read it (for tests)."""

    stream = bytearray()
    for ident, kind, payload in objects:
        info = Builder().int(1, ident).message(
            2, Builder().int(1, kind).packed(2, [1, 0, 5]).int(3, len(payload)))
        stream += _encoded_varint(len(info.out)) + bytes(info) + payload
    out = bytearray()
    for at in range(0, len(stream), 65536) or [0]:
        compressed = snappy(bytes(stream[at : at + 65536]))
        out += b"\x00" + len(compressed).to_bytes(3, "little") + compressed
    return bytes(out)
