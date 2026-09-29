"""Turn Vivado's report_io output into pin constraints (design.xdc).

Reads a ``report_io`` table on stdin and writes one ``set_property`` line per
placed port on stdout, fixing the port to the package pin that ``place_ports``
chose during synthesis and giving every port ``IOSTANDARD LVCMOS33``.

The I/O standard is deliberately hard-coded rather than copied from the report.
This is the exact script the 10,000-design suite was built with, and the I/O
standard determines the I/O buffer delays that placement and routing see; using
the report's default (LVCMOS18) instead produces slightly different placement,
routing, slack, and even LUT counts, so the shipped ``dataset_stats.csv`` and
``dataset_ip_sizes.csv`` would not be reproduced. Keep this file as is when
rebuilding designs from this suite.
"""

import re
import sys


def parse_pin(line):
    match = re.match(
        r"\|\s+([A-Z]+[0-9]+)\s+\|\s+([^\s\|]+)\s+\|[^\|]+\|[^\|]+\|\s+([A-Z]+)\s+\|",
        line,
    )
    return (match.group(1), match.group(2), match.group(3)) if match else None


def lines_of(stream):
    yield from stream


# Note that filter with None works like (x for x in gen if x)
def map_pins(io_stream):
    return filter(None, (parse_pin(line) for line in lines_of(io_stream)))


def xdc_line(pin):
    return (
        "set_property -dict "
        f"{{ PACKAGE_PIN {pin[0]}   IOSTANDARD LVCMOS33 }} "
        f"[get_ports {{ {pin[1]} }}];\n"
    )


def write_xdc(pinmap, stream):
    for pin in pinmap:
        stream.write(xdc_line(pin))


def main():
    write_xdc(tuple(map_pins(sys.stdin)), sys.stdout)


if __name__ == "__main__":
    main()
