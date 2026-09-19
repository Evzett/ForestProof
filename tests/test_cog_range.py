"""Чтение растра по кускам — источник байтов для облачных файлов.

Читатель растров обращается к файлу срезами, и ровно на этом держится
возможность читать окно участка из полуторастамегабайтного канала
Sentinel-2, не скачивая его целиком. Здесь проверяется сам источник:
что он отдаёт те же байты, что лежат в файле, и что за ними он ходит
по частям, а не забирает всё сразу.

Сеть не нужна: HTTP подменяется локальным файлом.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from cog import RangeReader  # noqa: E402

DATA = bytes(range(256)) * 40  # 10 240 байт, каждый со своим значением


class _FakeResponse:
    def __init__(self, payload: bytes, total: int) -> None:
        self._payload = payload
        self.status = 206
        self.reason = "Partial Content"
        self._headers = {"Content-Range": f"bytes 0-{len(payload) - 1}/{total}"}

    def read(self) -> bytes:
        return self._payload

    def getheader(self, name: str, default: str = "") -> str:
        return self._headers.get(name, default)


class _FakeConnection:
    """Подменяет постоянное соединение читателя.

    Читатель держит одно соединение на весь растр и ходит по нему
    запросами с заголовком Range — подменять нужно именно соединение,
    а не urlopen: через urlopen он больше не ходит.
    """

    def __init__(self, host: str, timeout: float | None = None) -> None:
        self.host = host
        self._next: _FakeResponse | None = None
        self.closed = False

    def request(self, method: str, path: str, headers: dict) -> None:
        start, end = headers["Range"].removeprefix("bytes=").split("-")
        chunk = DATA[int(start) : int(end) + 1]
        self._next = _FakeResponse(chunk, len(DATA))

    def getresponse(self) -> _FakeResponse:
        return self._next

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def reader(monkeypatch) -> RangeReader:
    """Читатель поверх DATA, считающий обращения к «сети»."""
    monkeypatch.setattr("cog.http.client.HTTPSConnection", _FakeConnection)
    return RangeReader("https://example.invalid/band.tif", block=1024)


def test_slice_matches_the_file(reader: RangeReader) -> None:
    assert reader[0:16] == DATA[0:16]
    assert reader[5000:5100] == DATA[5000:5100]
    assert reader[10_000:10_240] == DATA[10_000:10_240]


def test_slice_across_block_boundary(reader: RangeReader) -> None:
    """Срез, пересекающий границу блока, склеивается без сдвига.

    Самая вероятная ошибка в таком читателе — потерянное или лишнее
    смещение на стыке: данные при этом выглядят правдоподобно, а растр
    молча разъезжается.
    """
    assert reader[1000:1100] == DATA[1000:1100]
    assert reader[2047:2049] == DATA[2047:2049]


def test_length_comes_from_the_server(reader: RangeReader) -> None:
    assert len(reader) == len(DATA)


def test_reads_only_the_blocks_it_needs(reader: RangeReader) -> None:
    """Смысл всей затеи: качается окно, а не файл."""
    reader[5000:5010]
    assert reader.requests == 1
    assert reader.bytes_read <= 1024


def test_repeat_read_does_not_go_to_network_again(reader: RangeReader) -> None:
    """Соседние тайлы растра лежат рядом, и блок переиспользуется."""
    reader[5000:5010]
    before = reader.requests
    reader[5010:5020]
    assert reader.requests == before


def test_single_index_returns_one_byte(reader: RangeReader) -> None:
    assert reader[7] == DATA[7]
