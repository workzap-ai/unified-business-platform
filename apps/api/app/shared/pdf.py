"""A tiny PDF writer for business documents (receipts, statements): A4 pages of real,
selectable text in the PDF standard Helvetica fonts, plus lines and filled boxes.

No dependency and no native code: the document is a few text objects. Text is
WinAnsi (Latin-1); characters outside it are replaced, so keep documents in English or
Roman Urdu. Coordinates are points from the top-left (converted to PDF's bottom-left).
"""

from dataclasses import dataclass, field

WIDTH, HEIGHT = 595.28, 841.89  # A4 in points
MARGIN = 48.0

# Helvetica advance widths (per 1000 units) for the printable ASCII range 32..126.
_WIDTHS = [
    278,
    278,
    355,
    556,
    556,
    889,
    667,
    191,
    333,
    333,
    389,
    584,
    278,
    333,
    278,
    278,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    278,
    278,
    584,
    584,
    584,
    556,
    1015,
    667,
    667,
    722,
    722,
    667,
    611,
    778,
    722,
    278,
    500,
    667,
    556,
    833,
    722,
    778,
    667,
    778,
    722,
    667,
    611,
    722,
    667,
    944,
    667,
    667,
    611,
    278,
    278,
    278,
    469,
    556,
    333,
    556,
    556,
    500,
    556,
    556,
    278,
    556,
    556,
    222,
    222,
    500,
    222,
    833,
    556,
    556,
    556,
    556,
    333,
    500,
    278,
    556,
    500,
    722,
    500,
    500,
    500,
    334,
    260,
    334,
    584,
]


def text_width(text: str, size: float, bold: bool = False) -> float:
    total = 0
    for ch in text:
        code = ord(ch)
        total += _WIDTHS[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000 * (1.05 if bold else 1.0)


def _clean(text: str) -> str:
    out = []
    for ch in text:
        if ch in "\r\n\t":
            out.append(" ")
            continue
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    """Split text into lines that fit ``width`` (breaks at spaces; long words are cut)."""
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip() if line else word
            if text_width(candidate, size, bold) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            while text_width(word, size, bold) > width and len(word) > 1:
                cut = max(1, int(len(word) * width / max(text_width(word, size, bold), 1)))
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


@dataclass
class Page:
    ops: list[str] = field(default_factory=list)


@dataclass
class Document:
    """Build pages with text(), line() and box(); render() returns the PDF bytes."""

    title: str = ""
    pages: list[Page] = field(default_factory=lambda: [Page()])

    @property
    def page(self) -> Page:
        return self.pages[-1]

    def new_page(self) -> None:
        self.pages.append(Page())

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 10,
        bold: bool = False,
        color: tuple[float, float, float] = (0.1, 0.1, 0.12),
        align: str = "left",
    ) -> None:
        value = _clean(value)
        if align == "right":
            x -= text_width(value, size, bold)
        elif align == "center":
            x -= text_width(value, size, bold) / 2
        font = "F2" if bold else "F1"
        r, g, b = color
        self.page.ops.append(
            f"BT {r:.3f} {g:.3f} {b:.3f} rg /{font} {size:.1f} Tf "
            f"{x:.2f} {HEIGHT - y:.2f} Td ({_escape(value)}) Tj ET"
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        width: float = 0.6,
        color: tuple[float, float, float] = (0.85, 0.86, 0.88),
    ) -> None:
        r, g, b = color
        self.page.ops.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w "
            f"{x1:.2f} {HEIGHT - y1:.2f} m {x2:.2f} {HEIGHT - y2:.2f} l S"
        )

    def box(
        self, x: float, y: float, w: float, h: float, color: tuple[float, float, float]
    ) -> None:
        r, g, b = color
        self.page.ops.append(
            f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {HEIGHT - y - h:.2f} {w:.2f} {h:.2f} re f"
        )

    def render(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        catalog = add(b"")  # filled below
        pages_id = add(b"")
        regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )
        kids = []
        for page in self.pages:
            stream = "\n".join(page.ops).encode("cp1252", errors="replace")
            content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            kids.append(
                add(
                    b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                    b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                    % (pages_id, WIDTH, HEIGHT, regular, bold, content)
                )
            )
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % k for k in kids),
            len(kids),
        )
        title = _escape(_clean(self.title)).encode("cp1252", errors="replace")
        info = add(b"<< /Title (%s) /Producer (Owner OS) >>" % title)
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for offset in offsets:
            out += b"%010d 00000 n \n" % offset
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1,
            catalog,
            info,
            xref,
        )
        return bytes(out)
