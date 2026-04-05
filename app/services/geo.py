"""Geo utilities for decoding encoded polylines."""


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode a Google encoded polyline string into a list of [lat, lng] pairs."""
    coords = []
    i = 0
    lat = 0
    lng = 0

    while i < len(encoded):
        for field in range(2):
            shift = 0
            result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            value = ~(result >> 1) if (result & 1) else (result >> 1)
            if field == 0:
                lat += value
            else:
                lng += value
        coords.append([lat / 1e5, lng / 1e5])

    return coords
