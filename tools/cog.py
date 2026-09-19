"""Чтение облачного GeoTIFF по кускам — без скачивания целиком.

Зачем. Канал Sentinel-2 в родном разрешении весит около 150 МБ, а
участок занимает в нём доли процента. Скачивать тайл целиком ради
окна 2 на 3 километра — это два гигабайта трафика на дюжину участков
и минуты ожидания там, где хватает нескольких сотен килобайт.

Как. Читатель растров обращается к файлу срезами `buf[a:b]`, а не
читает его подряд. Значит вместо отображённого в память файла ему
можно подсунуть объект, который те же срезы берёт по HTTP Range и
запоминает прочитанное. Ни одной строчки в самом читателе менять не
пришлось — он и не знает, что файл лежит в облаке.

Блок в 256 КБ выбран как компромисс: заголовок TIFF с таблицей
смещений тайлов читается одним запросом, а лишнего тянется немного.
"""

from __future__ import annotations

import urllib.request

BLOCK = 256 * 1024
TIMEOUT = 120


class RangeReader:
    """Файлоподобный источник байтов, который тянет их по HTTP Range.

    Поддерживает ровно то, что нужно читателю растров: срезы и длину.
    Прочитанные блоки остаются в памяти — соседние тайлы растра лежат
    рядом, и повторный запрос за теми же байтами обычно не нужен.
    """

    def __init__(self, url: str, *, block: int = BLOCK, timeout: float = TIMEOUT) -> None:
        self.url = url
        self.block = block
        self.timeout = timeout
        self._blocks: dict[int, bytes] = {}
        self._size: int | None = None
        self.requests = 0
        self.bytes_read = 0

    def __len__(self) -> int:
        if self._size is None:
            self._fetch(0)
        return self._size or 0

    def _fetch(self, index: int) -> bytes:
        cached = self._blocks.get(index)
        if cached is not None:
            return cached

        start = index * self.block
        end = start + self.block - 1
        request = urllib.request.Request(
            self.url,
            headers={"Range": f"bytes={start}-{end}", "User-Agent": "ForestProof/1.0"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read()
            # Общий размер приходит в заголовке диапазона: «bytes 0-1023/148132472».
            if self._size is None:
                header = response.headers.get("Content-Range", "")
                if "/" in header:
                    self._size = int(header.rsplit("/", 1)[1])

        self.requests += 1
        self.bytes_read += len(data)
        self._blocks[index] = data
        return data

    def __getitem__(self, key):
        if isinstance(key, int):
            return self[key : key + 1][0]

        if key.step not in (None, 1):
            raise ValueError("шаг среза не поддерживается")

        # Длина спрашивается только тогда, когда без неё не обойтись:
        # у среза с отрицательной или открытой границей. Обычный срез
        # с явными границами её не требует, а узнать её можно лишь
        # сходив в сеть — и это был бы лишний запрос на каждое чтение.
        start, stop = key.start, key.stop
        if start is None or stop is None or start < 0 or stop < 0:
            start, stop, _ = key.indices(len(self))
        if stop <= start:
            return b""

        first, last = start // self.block, (stop - 1) // self.block
        chunks = [self._fetch(i) for i in range(first, last + 1)]
        joined = b"".join(chunks)
        offset = start - first * self.block
        return joined[offset : offset + (stop - start)]

    def close(self) -> None:
        # Блоки намеренно не выбрасываются: читатель живёт в общем кэше
        # (см. reader_for), и один и тот же тайл открывается за расчёт
        # два десятка раз — по разу на год и канал.
        pass


# Общий кэш читателей по адресу.
#
# Расчёт по контуру открывает один и тот же тайл около двадцати раз:
# десять лет на два канала. Заголовок TIFF с таблицей смещений у него
# общий, окна соседних лет попадают в те же блоки, и без кэша всё это
# качалось заново — полторы минуты вместо нескольких секунд.
#
# Кэш ограничен по числу тайлов: каждый держит прочитанные блоки в
# памяти, и расти без предела ему нельзя.
_READERS: dict[str, RangeReader] = {}
MAX_READERS = 8


def reader_for(url: str) -> RangeReader:
    reader = _READERS.get(url)
    if reader is None:
        if len(_READERS) >= MAX_READERS:
            # Вытесняется самый старый: словарь помнит порядок вставки.
            _READERS.pop(next(iter(_READERS)))
        reader = RangeReader(url)
        _READERS[url] = reader
    return reader
