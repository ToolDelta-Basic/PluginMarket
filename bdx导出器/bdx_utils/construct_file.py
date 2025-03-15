from io import BytesIO, BufferedWriter
from brotli import compress


def write_bdx_file(writer: BufferedWriter, author: str, bdx_content_reader: BytesIO):
    writer.seek(0, 2)
    writer.write(
        b"BD@"
        + compress(
            b"BDX\x00"
            + author.encode()
            + b"\x00"
            + bdx_content_reader.getvalue()
            + b"XE"
        )
    )
