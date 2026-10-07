"""Opdracht 6: CSV-bestanden van alle groepsleden automatisch samenvoegen."""
import csv
from pathlib import Path

from .exporters import DECIMAAL, EXTRA_KOLOM, KOLOMNAMEN, TYPES, schrijf_csv

PATROON = "systeeminfo_*.csv"   # naamafspraak: systeeminfo_<computernaam>.csv

# Afwijkende kolomnamen (bv. de Engelse namen uit opdracht 2) -> afgesproken kolomnaam
ALIASSEN = {
    "device_name": "computernaam",
    "device_model": "computermodel",
    "serial_number": "serienummer",
    "serial": "serienummer",
    "serial_no": "serienummer",
    "physical_cpu_cores": "fysieke_cpu_cores",
    "maximum_cpu_frequency_mhz": "max_cpu_frequentie_mhz",
    "total_ram_gib": "totaal_ram_gib",
    "file_system": "bestandssysteem",
    "storage_file_system": "bestandssysteem",
    "storage_capacity_gib": "opslagcapaciteit_gib",
    "interface": "netwerkinterface",
    "primary_interface": "netwerkinterface",
    "mac_address": "mac_adres",
    "ipv4_address": "ipv4_adres",
    "ipv6_address": "ipv6_adres",
    "ipv6_link_local_address": "ipv6_link_local_adres",
}

# Tekst die "geen waarde" betekent -> wordt een leeg veld
ONTBREEKT = {"", "n/a", "na", "none", "null", "nan", "-"}


def detecteer_scheidingsteken(pad):
    """Bepaal ; , of tab aan de hand van de kopregel (vangt afwijkende bestanden op)."""
    with open(pad, encoding="utf-8-sig") as f:
        kop = f.readline()
    return max([";", ",", "\t"], key=kop.count)


def kolomnaam_normaliseren(naam):
    naam = naam.strip().lower().replace(" ", "_")
    return ALIASSEN.get(naam, naam)


def schoon_waarde(kolom, tekst, bestandsnaam):
    """Ontbrekende waarde -> leeg; getallen krijgen overal hetzelfde formaat."""
    tekst = (tekst or "").strip()
    if tekst.lower() in ONTBREEKT:
        return ""
    typ = TYPES.get(kolom)
    if typ not in (int, float):
        return tekst
    try:
        getal = float(tekst.replace(",", "."))   # werkt voor "3100.0" en "3100,0"
    except ValueError:
        print(f"  ! {bestandsnaam}: '{tekst}' in kolom {kolom} is geen getal (ongewijzigd overgenomen)")
        return tekst
    if typ is int:
        return str(int(round(getal)))
    return str(getal).replace(".", DECIMAAL)


def lees_bestand(pad):
    """Lees één CSV-bestand en geef rijen terug met precies de afgesproken kolommen."""
    rijen = []
    with open(pad, newline="", encoding="utf-8-sig") as f:
        lezer = csv.DictReader(f, delimiter=detecteer_scheidingsteken(pad))
        origineel = [k.strip() for k in (lezer.fieldnames or [])]
        kolommen = [kolomnaam_normaliseren(k) for k in origineel]
        lezer.fieldnames = kolommen

        hernoemd = [f"{o} -> {n}" for o, n in zip(origineel, kolommen) if o.lower() != n]
        ontbreekt = [k for k in KOLOMNAMEN if k not in kolommen]
        extra = [k for k in kolommen if k not in KOLOMNAMEN and k != EXTRA_KOLOM]
        if hernoemd:
            print(f"  i {pad.name}: kolommen hernoemd: {', '.join(hernoemd)}")
        if ontbreekt:
            print(f"  ! {pad.name}: ontbrekende kolommen (leeg ingevuld): {', '.join(ontbreekt)}")
        if extra:
            print(f"  ! {pad.name}: onbekende kolommen (genegeerd): {', '.join(extra)}")

        for rij in lezer:
            schoon = {k: schoon_waarde(k, rij.get(k), pad.name) for k in KOLOMNAMEN}
            if any(schoon.values()):                                    # lege regels overslaan
                schoon[EXTRA_KOLOM] = pad.name
                rijen.append(schoon)
    return rijen


def voeg_samen(map_):
    """Zoek automatisch alle bestanden die aan het patroon voldoen en voeg ze samen."""
    map_ = Path(map_)
    bestanden = sorted(map_.glob(PATROON), key=lambda p: p.stat().st_mtime)
    if not bestanden:
        raise SystemExit(f"Geen bestanden gevonden met patroon '{PATROON}' in map '{map_}'.")

    per_computer = {}
    print(f"{len(bestanden)} bestand(en) gevonden in {map_.name}/:")
    for pad in bestanden:
        print(f"- {pad.name}")
        for rij in lees_bestand(pad):
            sleutel = rij["computernaam"].lower() or pad.name
            if sleutel in per_computer:
                print(f"  ! {rij['computernaam'] or pad.name} komt meerdere keren voor: "
                      f"nieuwste bestand ({pad.name}) wordt gebruikt")
            per_computer[sleutel] = rij       # nieuwste bestand wint
    return sorted(per_computer.values(), key=lambda r: r["computernaam"].lower())


def schrijf_samengevoegd(rijen, bestand):
    schrijf_csv(rijen, bestand)
