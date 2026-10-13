"""Minimal protobuf decoder for asserting on Google Flights ``tfs`` values."""

import base64


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def decode(buf: bytes) -> list[tuple[int, int | bytes]]:
    """Return (field_number, value) pairs; length-delimited values stay as bytes."""
    fields, i = [], 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            length, i = _varint(buf, i)
            value, i = buf[i:i + length], i + length
        else:
            raise ValueError(f"unsupported wire type {wire}")
        fields.append((num, value))
    return fields


def decode_tfs(tfs: str) -> dict:
    raw = base64.urlsafe_b64decode(tfs + "=" * (-len(tfs) % 4))
    info = decode(raw)
    legs = []
    for num, value in info:
        if num != 3:
            continue
        leg = {"date": None, "from": [], "to": []}
        for f, v in decode(value):
            if f == 2:
                leg["date"] = v.decode()
            elif f in (13, 14):
                airport = dict(decode(v))
                assert airport.get(1) == 1, "airport type should be 1 (airport)"
                leg["from" if f == 13 else "to"].append(airport[2].decode())
        legs.append(leg)
    return {
        "legs": legs,
        "passengers": [v for n, v in info if n == 8],
        "seat": next((v for n, v in info if n == 9), None),
        "trip": next((v for n, v in info if n == 19), None),
    }
