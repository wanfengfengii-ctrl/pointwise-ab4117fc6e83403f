import re
from fractions import Fraction
from types import MappingProxyType


MICROMETRE_FACTORS = MappingProxyType({'mm': 1000, 'um': 1, 'µm': 1, 'μm': 1})
_DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')


def to_micrometres(value: str | int, unit: str) -> Fraction:
    if not isinstance(unit, str) or unit not in MICROMETRE_FACTORS:
        raise ValueError('unsupported thickness unit')
    if type(value) not in (str, int) or not _DECIMAL.fullmatch(str(value)):
        raise ValueError('expected a finite decimal thickness')
    return Fraction(value) * MICROMETRE_FACTORS[unit]
