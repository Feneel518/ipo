from pathlib import Path

import pikepdf


class PdfOptimizationError(Exception):
    pass


def optimize_pdf(source: Path, destination: Path) -> Path:
    """Perform structural compression without dropping document content."""
    try:
        with pikepdf.open(source) as pdf:
            pdf.save(
                destination,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                linearize=False,
            )
        return destination
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise PdfOptimizationError(f"PDF optimization failed: {exc}") from exc
