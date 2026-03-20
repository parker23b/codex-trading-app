from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentDefinition:
    epic: str
    label: str
    category: str


INSTRUMENT_CATALOG: tuple[InstrumentDefinition, ...] = (
    InstrumentDefinition(epic="CS.D.EURUSD.CFD.IP", label="EUR/USD", category="FOREX"),
    InstrumentDefinition(epic="CS.D.GBPUSD.CFD.IP", label="GBP/USD", category="FOREX"),
    InstrumentDefinition(epic="CS.D.USDJPY.CFD.IP", label="USD/JPY", category="FOREX"),
    InstrumentDefinition(epic="CS.D.AUDUSD.CFD.IP", label="AUD/USD", category="FOREX"),
    InstrumentDefinition(epic="CS.D.USDCHF.CFD.IP", label="USD/CHF", category="FOREX"),
    InstrumentDefinition(epic="CS.D.USDCAD.CFD.IP", label="USD/CAD", category="FOREX"),
    InstrumentDefinition(epic="CS.D.EURGBP.CFD.IP", label="EUR/GBP", category="FOREX"),
    InstrumentDefinition(epic="IX.D.FTSE.DAILY.IP", label="FTSE 100", category="INDICES"),
    InstrumentDefinition(epic="IX.D.DAX.DAILY.IP", label="DAX 40", category="INDICES"),
    InstrumentDefinition(epic="IX.D.NASDAQ.DAILY.IP", label="Nasdaq 100", category="INDICES"),
    InstrumentDefinition(epic="IX.D.SP500.DAILY.IP", label="S&P 500", category="INDICES"),
)


def list_instruments() -> list[dict[str, str]]:
    return [{"epic": instrument.epic, "label": instrument.label, "category": instrument.category} for instrument in INSTRUMENT_CATALOG]
