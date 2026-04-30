"""Thai large-cap universe — SET100 blue chips, benchmark ^SET.BK."""

from src.backtesting.interfaces import Universe

_SECTORS = {
    "ENERGY":        {"etf": "PTT.BK",   "members": ["BANPU.BK", "BCP.BK", "IRPC.BK", "OR.BK", "PTG.BK", "PTT.BK", "PTTEP.BK", "SPRC.BK", "TOP.BK"]},
    "FINANCIALS":    {"etf": "KBANK.BK", "members": ["AEONTS.BK", "BAM.BK", "BBL.BK", "BLA.BK", "JMT.BK", "KBANK.BK", "KKP.BK", "KTB.BK", "KTC.BK", "MTC.BK", "SAWAD.BK", "SCB.BK", "TCAP.BK", "TIDLOR.BK", "TISCO.BK", "TLI.BK", "TTB.BK"]},
    "TECH":          {"etf": "DELTA.BK", "members": ["ADVANC.BK", "CCET.BK", "COM7.BK", "DELTA.BK", "HANA.BK", "JAS.BK", "JMART.BK", "JTS.BK", "KCE.BK", "TRUE.BK"]},
    "CONSUMER_DISC": {"etf": "CPALL.BK", "members": ["AURA.BK", "BJC.BK", "CBG.BK", "CENTEL.BK", "CPALL.BK", "CRC.BK", "DOHOME.BK", "ERW.BK", "GLOBAL.BK", "HMPRO.BK", "ICHI.BK", "M.BK", "MINT.BK", "MOSHI.BK", "OSP.BK", "PLANB.BK", "SISB.BK", "VGI.BK"]},
    "CONSUMER_STAP": {"etf": "CPF.BK",   "members": ["BTG.BK", "CPF.BK", "GFPT.BK", "MEGA.BK", "STA.BK", "STGT.BK", "TFG.BK", "TU.BK"]},
    "HEALTH":        {"etf": "BDMS.BK",  "members": ["BCH.BK", "BDMS.BK", "BH.BK", "CHG.BK", "PR9.BK"]},
    "MATERIALS":     {"etf": "SCC.BK",   "members": ["IVL.BK", "PTTGC.BK", "SCC.BK", "SCGP.BK", "TASCO.BK", "TOA.BK"]},
    "INDUSTRIALS":   {"etf": "BEM.BK",   "members": ["AMATA.BK", "CK.BK", "STECON.BK"]},
    "UTILITIES":     {"etf": "BGRIM.BK", "members": ["BCPG.BK", "BGRIM.BK", "EA.BK", "EGCO.BK", "GPSC.BK", "GULF.BK", "GUNKUL.BK", "RATCH.BK"]},
    "REIT":          {"etf": "WHA.BK",   "members": ["AP.BK", "AWC.BK", "CPN.BK", "LH.BK", "QH.BK", "SIRI.BK", "SPALI.BK", "WHA.BK"]},
    "TRANSPORT":     {"etf": "BANPU.BK", "members": ["AAV.BK", "AOT.BK", "BA.BK", "BEM.BK", "BTS.BK", "PRM.BK", "RCL.BK", "SJWD.BK"]},
}

SET100 = Universe(
    name="SET100",
    display_name="SET100 Thailand",
    tickers=list(dict.fromkeys(t for s in _SECTORS.values() for t in s["members"])),
    benchmark_ticker="^SET.BK",
    fallback_benchmark="EWY",
    sectors=_SECTORS,
)
