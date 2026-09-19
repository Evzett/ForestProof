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

import math
import mmap
import struct
import zlib
from dataclasses import dataclass

import numpy as np

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_SAMPLE_DTYPE = {
    (1, 8): np.uint8,
    (1, 16): np.uint16,
    (1, 32): np.uint32,
    (2, 16): np.int16,
    (2, 32): np.int32,
    (3, 32): np.float32,
}

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
TAG_PREDICTOR = 317
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


def _lzw_decode(data: bytes) -> bytes:
    """Распаковка LZW в варианте TIFF.

    Отличие от обычного LZW одно, но ломающее всё: ширина кода растёт
    на один код раньше, чем кажется по учебнику. Исходники CEDA сжаты
    именно так, файлы набора — Deflate, поэтому нужны оба.
    """
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    next_code = 258
    width = 9
    previous = b""
    bit = 0
    total = len(data) * 8

    while bit + width <= total:
        index = bit >> 3
        chunk = int.from_bytes(data[index : index + 3].ljust(3, b"\x00"), "big")
        code = (chunk >> (24 - (bit & 7) - width)) & ((1 << width) - 1)
        bit += width

        if code == 256:
            table = [bytes([i]) for i in range(256)] + [b"", b""]
            next_code = 258
            width = 9
            previous = b""
            continue
        if code == 257:
            break

        if not previous:
            entry = table[code]
        elif code < next_code:
            entry = table[code]
            table.append(previous + entry[:1])
            next_code += 1
        else:
            entry = previous + previous[:1]
            table.append(entry)
            next_code += 1

        out += entry
        previous = entry
        if next_code + 1 >= (1 << width) and width < 12:
            width += 1

    return bytes(out)


def _undo_predictor(
    block: bytes, predictor: int, width: int, rows: int, depth: int, dtype
) -> bytes:
    """Снимает горизонтальное дифференцирование.

    Предиктор 2 — обычная разность соседних значений. Предиктор 3 —
    плавающий: байты значений разложены по плоскостям (сначала все
    старшие байты строки, потом вторые и так далее) и продифференцированы
    побайтово. Без обратного преобразования float-растр читается как шум
    порядка 1e38, и это самая незаметная поломка из возможных.
    """
    itemsize = np.dtype(dtype).itemsize
    # Распаковщик вправе вернуть больше байтов, чем занимает полоса:
    # LZW добивает поток до границы кода, и лишние байты — padding, а не
    # данные. Обрезаем здесь, иначе reshape падает на случайных участках.
    block = block[: rows * width * depth * itemsize]

    if predictor == 1:
        return block

    if predictor == 2:
        arr = np.frombuffer(block, dtype=dtype).reshape(rows, width, depth).copy()
        np.cumsum(arr, axis=1, dtype=dtype, out=arr)
        return arr.tobytes()

    if predictor != 3:
        raise ValueError(f"предиктор {predictor} не поддерживается")

    stride = width * depth * itemsize
    raw = np.frombuffer(block, dtype=np.uint8)[: rows * stride].reshape(rows, stride)
    restored = (np.cumsum(raw.astype(np.uint32), axis=1) & 0xFF).astype(np.uint8)
    # Байтовые плоскости идут от старшего байта к младшему — значит порядок
    # байтов в собранном значении big-endian независимо от порядка файла.
    planes = restored.reshape(rows, itemsize, width * depth)
    merged = np.transpose(planes, (0, 2, 1)).reshape(rows, width * depth * itemsize)
    return merged.tobytes()


def read_geotiff(path: str, bbox: tuple[float, float, float, float] | None = None) -> Raster:
    """Читает растр целиком или только окно, накрывающее рамку.

    Окно принципиально для больших тайлов: тайл CCI 10 на 10 градусов это
    123 МБ сжатых и около 500 МБ в памяти, а участок кейса занимает в нём
    меньше тысячной доли. Распаковываем только задетые блоки.
    """
    # Адрес вместо пути — тот же растр, лежащий в облаке. Читается он
    # точно так же, срезами, только байты приезжают по HTTP Range:
    # канал Sentinel-2 весит около 150 МБ, а окно участка — доли
    # процента, и качать тайл целиком незачем.
    if path.startswith(("http://", "https://")):
        # Читатель берётся из общего кэша: за один расчёт тот же тайл
        # открывается по разу на год и канал, и заново качать заголовок
        # с таблицей смещений каждый раз — это минуты вместо секунд.
        from cog import reader_for

        handle = None
        buf = reader_for(path)
    else:
        # Файл отображается в память, а не читается целиком: тайл Hansen
        # весит 452 МБ, а окно затрагивает доли процента страниц. При чтении
        # через read() каждый вызов стоил бы полгигабайта дискового ввода,
        # и нарезка четырёхсот участков превращалась в двести гигабайт.
        handle = open(path, "rb")
        try:
            buf = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:
            # пустой файл — mmap на нём не работает
            handle.close()
            raise ValueError(f"{path}: пустой файл")

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

    predictor = tags.get(TAG_PREDICTOR, (1,))[0]
    if compression not in (1, 5, 8, 32946):
        raise ValueError(f"{path}: сжатие {compression} не поддерживается")

    dtype = _SAMPLE_DTYPE.get((fmt[0], bits[0]))
    if dtype is None:
        raise ValueError(f"{path}: формат образца {fmt[0]}/{bits[0]} не поддерживается")
    if predictor == 3:
        # После снятия предиктора байты собраны от старшего к младшему
        dtype = np.dtype(dtype).newbyteorder(">")

    def blocks(offsets_tag: int, counts_tag: int) -> list[bytes]:
        offsets = tags[offsets_tag]
        counts = tags[counts_tag]
        out = []
        for off, size in zip(offsets, counts):
            chunk = buf[off : off + size]
            if compression in (8, 32946):
                out.append(zlib.decompress(chunk))
            elif compression == 5:
                out.append(_lzw_decode(chunk))
            else:
                out.append(chunk)
        return out

    scale = tags.get(TAG_PIXEL_SCALE, (1.0, 1.0, 0.0))
    tie = tags.get(TAG_TIEPOINT, (0.0,) * 6)
    lon_origin, lat_origin = float(tie[3]), float(tie[4])
    lon_step, lat_step = float(scale[0]), float(scale[1])

    # Окно в пикселях: с запасом в один пиксель, чтобы краевой пиксель
    # целиком попал в расчёт долей пересечения.
    col0, row0 = 0, 0
    if bbox is not None:
        west, south, east, north = bbox
        col0 = max(int(math.floor((west - lon_origin) / lon_step)) - 1, 0)
        col1 = min(int(math.ceil((east - lon_origin) / lon_step)) + 1, width)
        row0 = max(int(math.floor((lat_origin - north) / lat_step)) - 1, 0)
        row1 = min(int(math.ceil((lat_origin - south) / lat_step)) + 1, height)
        if col1 <= col0 or row1 <= row0:
            raise ValueError(f"{path}: рамка не пересекается с растром")
    else:
        col1, row1 = width, height

    out_w, out_h = col1 - col0, row1 - row0

    if TAG_TILE_OFFSETS in tags:
        tile_w = tags[TAG_TILE_WIDTH][0]
        tile_h = tags[TAG_TILE_LENGTH][0]
        across = (width + tile_w - 1) // tile_w
        per_plane = across * ((height + tile_h - 1) // tile_h)
        planes = samples if planar == 2 else 1
        data = np.zeros((samples, out_h, out_w), dtype=dtype)
        offsets = tags[TAG_TILE_OFFSETS]
        counts = tags[TAG_TILE_COUNTS]

        def decode(position: int) -> bytes:
            chunk = buf[offsets[position] : offsets[position] + counts[position]]
            if compression in (8, 32946):
                return zlib.decompress(chunk)
            if compression == 5:
                return _lzw_decode(chunk)
            return chunk

        needed = [
            index
            for index in range(per_plane)
            if (index // across) * tile_h < row1
            and ((index // across) + 1) * tile_h > row0
            and (index % across) * tile_w < col1
            and ((index % across) + 1) * tile_w > col0
        ]

        for plane in range(planes):
            for index in needed:
                raw = decode(plane * per_plane + index)
                depth = 1 if planar == 2 else samples
                raw = _undo_predictor(raw, predictor, tile_w, tile_h, depth, dtype)
                tile = np.frombuffer(raw, dtype=dtype).reshape(tile_h, tile_w, depth)
                r0 = (index // across) * tile_h
                c0 = (index % across) * tile_w
                # пересечение тайла с окном, в координатах тайла и выхода
                src_r = max(row0 - r0, 0)
                src_c = max(col0 - c0, 0)
                dst_r = max(r0 - row0, 0)
                dst_c = max(c0 - col0, 0)
                rows = min(tile_h - src_r, out_h - dst_r, height - r0 - src_r)
                cols = min(tile_w - src_c, out_w - dst_c, width - c0 - src_c)
                if rows <= 0 or cols <= 0:
                    continue
                piece = tile[src_r : src_r + rows, src_c : src_c + cols]
                if planar == 2:
                    data[plane, dst_r : dst_r + rows, dst_c : dst_c + cols] = piece[:, :, 0]
                else:
                    for band in range(samples):
                        data[band, dst_r : dst_r + rows, dst_c : dst_c + cols] = piece[:, :, band]
    else:
        rows_per_strip = tags.get(TAG_ROWS_PER_STRIP, (height,))[0]
        offsets = tags[TAG_STRIP_OFFSETS]
        counts = tags[TAG_STRIP_COUNTS]
        planes = samples if planar == 2 else 1
        per_plane = len(offsets) // planes
        data = np.zeros((samples, out_h, out_w), dtype=dtype)

        def decode_strip(position: int) -> bytes:
            chunk = buf[offsets[position] : offsets[position] + counts[position]]
            if compression in (8, 32946):
                return zlib.decompress(chunk)
            if compression == 5:
                return _lzw_decode(chunk)
            return chunk

        # Разжимаем только те полосы, которые задевает окно. У тайлов
        # Hansen одна строка на полосу и сорок тысяч полос: распаковывать
        # их все ради окна в сто шестьдесят строк — это тридцать секунд
        # и полтора гигабайта там, где хватает десятой доли секунды.
        first_strip = row0 // rows_per_strip
        last_strip = min((row1 - 1) // rows_per_strip, per_plane - 1)

        for plane in range(planes):
            for index in range(first_strip, last_strip + 1):
                raw = decode_strip(plane * per_plane + index)
                r0 = index * rows_per_strip
                rows = min(rows_per_strip, height - r0)
                depth = 1 if planar == 2 else samples
                raw = _undo_predictor(raw, predictor, width, rows, depth, dtype)
                strip = np.frombuffer(raw, dtype=dtype).reshape(rows, width, depth)

                src_r = max(row0 - r0, 0)
                dst_r = max(r0 - row0, 0)
                take = min(rows - src_r, out_h - dst_r)
                if take <= 0:
                    continue
                piece = strip[src_r : src_r + take, col0:col1]
                if planar == 2:
                    data[plane, dst_r : dst_r + take] = piece[:, :, 0]
                else:
                    for band in range(samples):
                        data[band, dst_r : dst_r + take] = piece[:, :, band]

    nodata_raw = tags.get(TAG_NODATA)
    nodata = None
    if isinstance(nodata_raw, str) and nodata_raw.strip().lower() not in ("", "none", "nan"):
        nodata = float(nodata_raw)

    # Копируем результат до закрытия отображения: numpy может держать
    # ссылку на буфер, и обращение к нему после close() уронит процесс.
    data = np.array(data, copy=True)
    buf.close()
    if handle is not None:
        handle.close()

    return Raster(
        data=data,
        lon_origin=lon_origin + col0 * lon_step,
        lat_origin=lat_origin - row0 * lat_step,
        lon_step=lon_step,
        lat_step=lat_step,
        nodata=nodata,
        metadata=tags.get(TAG_GDAL_META, "") if isinstance(tags.get(TAG_GDAL_META), str) else "",
    )
