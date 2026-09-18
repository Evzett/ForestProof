"""Минимальный читатель GeoTIFF под растры кейса.

Зачем свой: в наборе тайловые GeoTIFF со сжатием Deflate и PlanarConfig=2,
а ставить rasterio/GDAL ради пяти тегов не хочется — на машинах команды
это самая частая причина «у меня не собирается». Здесь только то, что
нужно кейсу: uint8/uint16/int16, Deflate и без сжатия, тайлы и полосы.

Географию берём из ModelTiepoint и ModelPixelScale: сетка в градусах,
поэтому площадь пикселя считается по широте, а не принимается за гектар
(прямое требование постановки).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

import numpy as np

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_SAMPLE_DTYPE = {(1, 8): np.uint8, (1, 16): np.uint16, (2, 16): np.int16, (3, 32): np.float32}

TAG_WIDTH = 256
TAG_LENGTH = 257
TAG_BITS = 258
TAG_COMPRESSION = 259
TAG_STRIP_OFFSETS = 273
TAG_SAMPLES = 277
TAG_ROWS_PER_STRIP = 278
TAG_STRIP_COUNTS = 279
TAG_PLANAR = 284
TAG_TILE_WIDTH = 322
TAG_TILE_LENGTH = 323
TAG_TILE_OFFSETS = 324
TAG_TILE_COUNTS = 325
TAG_SAMPLE_FORMAT = 339
TAG_PIXEL_SCALE = 33550
TAG_TIEPOINT = 33922
TAG_NODATA = 42113
TAG_GDAL_META = 42112


@dataclass(frozen=True)
class Raster:
    """Пиксели плюс минимум географии, нужный для площадного взвешивания."""

    data: np.ndarray  # (bands, rows, cols)
    lon_origin: float
    lat_origin: float
    lon_step: float
    lat_step: float  # положительный, широта убывает вниз
    nodata: float | None
    metadata: str

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape

    def band(self, index: int) -> np.ndarray:
        return self.data[index]

    def pixel_area_ha(self) -> np.ndarray:
        """Площадь каждого пикселя в гектарах — по широте его центра.

        На сетке в градусах площадь пикселя меняется с широтой, и принимать
        её равной гектару нельзя: на 56° северной широты пиксель CCI
        примерно 0,55 га, а не 1 га.
        """
        rows = self.data.shape[1]
        lat_centers = self.lat_origin - (np.arange(rows) + 0.5) * self.lat_step
        # длина градуса на эллипсоиде WGS 84, достаточная для площадей кейса
        m_per_deg_lat = 111_132.92 - 559.82 * np.cos(2 * np.radians(lat_centers))
        m_per_deg_lon = 111_412.84 * np.cos(np.radians(lat_centers)) - 93.5 * np.cos(
            3 * np.radians(lat_centers)
        )
        row_area_m2 = (self.lat_step * m_per_deg_lat) * (self.lon_step * m_per_deg_lon)
        return np.repeat((row_area_m2 / 10_000.0)[:, None], self.data.shape[2], axis=1)


def _read_entry(buf: bytes, bo: str, entry_offset: int) -> tuple[int, int, int, bytes]:
    tag, typ, count = struct.unpack(bo + "HHI", buf[entry_offset : entry_offset + 8])
    raw = buf[entry_offset + 8 : entry_offset + 12]
    total = _TYPE_SIZE.get(typ, 1) * count
    if total > 4:
        pointer = struct.unpack(bo + "I", raw)[0]
        raw = buf[pointer : pointer + total]
    else:
        raw = raw[:total]
    return tag, typ, count, raw


def _values(typ: int, count: int, raw: bytes, bo: str):
    if typ == 2:
        return raw.decode("utf-8", "replace").rstrip("\x00")
    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d"}.get(typ)
    if fmt is None:
        return raw
    return struct.unpack(bo + fmt * count, raw)


def read_geotiff(path: str) -> Raster:
    with open(path, "rb") as handle:
        buf = handle.read()

    if buf[:2] not in (b"II", b"MM"):
        raise ValueError(f"{path}: не TIFF")
    bo = "<" if buf[:2] == b"II" else ">"
    if struct.unpack(bo + "H", buf[2:4])[0] != 42:
        raise ValueError(f"{path}: поддерживается только классический TIFF")

    ifd = struct.unpack(bo + "I", buf[4:8])[0]
    count = struct.unpack(bo + "H", buf[ifd : ifd + 2])[0]
    tags: dict[int, object] = {}
    for i in range(count):
        tag, typ, cnt, raw = _read_entry(buf, bo, ifd + 2 + i * 12)
        tags[tag] = _values(typ, cnt, raw, bo)

    width = tags[TAG_WIDTH][0]
    height = tags[TAG_LENGTH][0]
    samples = tags.get(TAG_SAMPLES, (1,))[0]
    bits = tags.get(TAG_BITS, (8,) * samples)
    fmt = tags.get(TAG_SAMPLE_FORMAT, (1,) * samples)
    compression = tags.get(TAG_COMPRESSION, (1,))[0]
    planar = tags.get(TAG_PLANAR, (1,))[0]

    if compression not in (1, 8, 32946):
        raise ValueError(f"{path}: сжатие {compression} не поддерживается")

    dtype = _SAMPLE_DTYPE.get((fmt[0], bits[0]))
    if dtype is None:
        raise ValueError(f"{path}: формат образца {fmt[0]}/{bits[0]} не поддерживается")

    def blocks(offsets_tag: int, counts_tag: int) -> list[bytes]:
        offsets = tags[offsets_tag]
        counts = tags[counts_tag]
        out = []
        for off, size in zip(offsets, counts):
            chunk = buf[off : off + size]
            out.append(zlib.decompress(chunk) if compression in (8, 32946) else chunk)
        return out

    if TAG_TILE_OFFSETS in tags:
        tile_w = tags[TAG_TILE_WIDTH][0]
        tile_h = tags[TAG_TILE_LENGTH][0]
        across = (width + tile_w - 1) // tile_w
        down = (height + tile_h - 1) // tile_h
        per_plane = across * down
        planes = samples if planar == 2 else 1
        data = np.zeros((samples, height, width), dtype=dtype)
        chunks = blocks(TAG_TILE_OFFSETS, TAG_TILE_COUNTS)
        for plane in range(planes):
            for index in range(per_plane):
                raw = chunks[plane * per_plane + index]
                depth = 1 if planar == 2 else samples
                tile = np.frombuffer(raw, dtype=dtype).reshape(tile_h, tile_w, depth)
                r0 = (index // across) * tile_h
                c0 = (index % across) * tile_w
                rows = min(tile_h, height - r0)
                cols = min(tile_w, width - c0)
                if planar == 2:
                    data[plane, r0 : r0 + rows, c0 : c0 + cols] = tile[:rows, :cols, 0]
                else:
                    for band in range(samples):
                        data[band, r0 : r0 + rows, c0 : c0 + cols] = tile[:rows, :cols, band]
    else:
        rows_per_strip = tags.get(TAG_ROWS_PER_STRIP, (height,))[0]
        chunks = blocks(TAG_STRIP_OFFSETS, TAG_STRIP_COUNTS)
        data = np.zeros((samples, height, width), dtype=dtype)
        planes = samples if planar == 2 else 1
        per_plane = len(chunks) // planes
        for plane in range(planes):
            for index in range(per_plane):
                raw = chunks[plane * per_plane + index]
                r0 = index * rows_per_strip
                rows = min(rows_per_strip, height - r0)
                depth = 1 if planar == 2 else samples
                strip = np.frombuffer(raw, dtype=dtype).reshape(rows, width, depth)
                if planar == 2:
                    data[plane, r0 : r0 + rows] = strip[:, :, 0]
                else:
                    for band in range(samples):
                        data[band, r0 : r0 + rows] = strip[:, :, band]

    scale = tags.get(TAG_PIXEL_SCALE, (1.0, 1.0, 0.0))
    tie = tags.get(TAG_TIEPOINT, (0.0,) * 6)
    nodata_raw = tags.get(TAG_NODATA)
    nodata = None
    if isinstance(nodata_raw, str) and nodata_raw.strip().lower() not in ("", "none", "nan"):
        nodata = float(nodata_raw)

    return Raster(
        data=data,
        lon_origin=float(tie[3]),
        lat_origin=float(tie[4]),
        lon_step=float(scale[0]),
        lat_step=float(scale[1]),
        nodata=nodata,
        metadata=tags.get(TAG_GDAL_META, "") if isinstance(tags.get(TAG_GDAL_META), str) else "",
    )
