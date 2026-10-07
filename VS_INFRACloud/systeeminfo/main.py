"""Voert alle opdrachten in één keer uit:

1. systeeminformatie verzamelen en filteren     (opdracht 1 en 2)
2. opslaan als JSON, CSV en XLSX + controle      (opdracht 3, 4 en 5)
3. bestanden van de groepsleden samenvoegen      (opdracht 6)
4. de gegevens valideren                         (opdracht 7)
   (het serienummer van de computer zit overal bij: opdracht 8)
5. de Excel-bestanden openen

Uitvoeren:  python main.py            (of: python main.py --no-open om niets te openen)
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sysinfo.collect import collect_selected_system_info
from sysinfo.exporters import (
    KOLOMMEN, TYPES, dict_naar_rij, haal_op, lees_csv, lees_json, lees_xlsx,
    schrijf_csv, schrijf_json, schrijf_xlsx, tekst_naar_waarde, veilige_naam,
)
from sysinfo.merge import schrijf_samengevoegd, voeg_samen
from sysinfo.validate import schrijf_rapport, valideer_dataset, valideer_eigen_computer

# Alle paden zijn relatief aan deze map, zodat het script overal vandaan werkt.
BASIS = Path(__file__).resolve().parent
OUTPUT = BASIS / "output"
GROEPSDATA = BASIS / "groepsdata"


def titel(tekst):
    print(f"\n=== {tekst} ===")


def open_bestand(pad):
    """Open een bestand met het standaardprogramma (Excel) van het besturingssysteem."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(pad)  # noqa: S606  (alleen beschikbaar op Windows)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(pad)], check=False)
        else:
            subprocess.run(["xdg-open", str(pad)], check=False)
        print(f"Geopend: {pad.name}")
    except Exception as exc:  # het openen mag het programma nooit laten crashen
        print(f"Kon {pad.name} niet automatisch openen ({exc}). Open het zelf.")


def controleer_roundtrips(info, json_pad, csv_pad, xlsx_pad):
    """Lees de bestanden terug in en vergelijk ze met de oorspronkelijke dict."""
    resultaten = {"JSON": lees_json(json_pad) == info}

    verwacht = {naam: tekst_naar_waarde(dict_naar_rij(info)[naam], typ)
                for naam, _, typ in KOLOMMEN}
    csv_rij = lees_csv(csv_pad)[0]
    xlsx_rij = lees_xlsx(xlsx_pad)[0]
    resultaten["CSV"] = csv_rij == verwacht
    resultaten["XLSX"] = xlsx_rij == verwacht
    resultaten["XLSX == CSV"] = xlsx_rij == csv_rij
    for naam, ok in resultaten.items():
        print(f"  {naam:12} {'OK' if ok else 'VERSCHIL'}")
    return all(resultaten.values())


def main():
    parser = argparse.ArgumentParser(description="Verzamel en verwerk systeeminformatie.")
    parser.add_argument("--no-open", action="store_true",
                        help="open de Excel-bestanden niet automatisch")
    args = parser.parse_args()

    OUTPUT.mkdir(exist_ok=True)
    GROEPSDATA.mkdir(exist_ok=True)

    # 1. Verzamelen (opdracht 1 en 2)
    titel("1. Systeeminformatie verzamelen")
    info = collect_selected_system_info()
    naam = veilige_naam(info["device_name"])
    print(f"Computer: {info['device_name']} ({info['device_model']})")

    # 2. Opslaan (opdracht 3, 4 en 5)
    titel("2. Opslaan als JSON, CSV en XLSX")
    json_pad = OUTPUT / f"systeeminfo_{naam}.json"
    csv_pad = OUTPUT / f"systeeminfo_{naam}.csv"
    xlsx_pad = OUTPUT / f"systeeminfo_{naam}.xlsx"
    schrijf_json(info, json_pad)
    schrijf_csv([dict_naar_rij(info)], csv_pad)
    schrijf_xlsx([dict_naar_rij(info)], xlsx_pad)
    print(f"Opgeslagen in {OUTPUT.name}/: {json_pad.name}, {csv_pad.name}, {xlsx_pad.name}")
    print("Terug ingelezen en vergeleken met de oorspronkelijke gegevens:")
    if not controleer_roundtrips(info, json_pad, csv_pad, xlsx_pad):
        print("WAARSCHUWING: de teruggelezen gegevens komen niet overeen!")

    # 3. Samenvoegen (opdracht 6)
    titel("3. Gegevens van de groep samenvoegen")
    shutil.copy2(csv_pad, GROEPSDATA / csv_pad.name)      # eigen bestand bij de groepsbestanden
    rijen = voeg_samen(GROEPSDATA)
    samengevoegd_csv = GROEPSDATA / "groep_samengevoegd.csv"
    samengevoegd_xlsx = GROEPSDATA / "groep_samengevoegd.xlsx"
    schrijf_samengevoegd(rijen, samengevoegd_csv)
    schrijf_xlsx(rijen, samengevoegd_xlsx)
    print(f"{len(rijen)} computer(s) samengevoegd in {samengevoegd_csv.name} en {samengevoegd_xlsx.name}")

    # 4. Valideren (opdracht 7)
    titel("4. Valideren")
    print("Deel A: automatische controles op alle computers")
    fouten = valideer_dataset(rijen)
    print("\nDeel B: deze computer vergelijken met de werkelijke configuratie")
    rapport = valideer_eigen_computer(rijen)
    if rapport:
        rapport_pad = OUTPUT / "validatie_rapport.csv"
        schrijf_rapport(rapport, rapport_pad)
        print(f"Rapport opgeslagen in {OUTPUT.name}/{rapport_pad.name}")

    # 5. Openen
    titel("5. Klaar")
    print(f"Alle controles in deel A: {'geen fouten' if fouten == 0 else f'{fouten} probleem(en) gevonden'}")
    if args.no_open:
        print("Bestanden worden niet geopend (--no-open).")
    else:
        open_bestand(xlsx_pad)
        open_bestand(samengevoegd_xlsx)


if __name__ == "__main__":
    try:
        main()
    except PermissionError as exc:
        sys.exit(f"\nKan '{exc.filename}' niet schrijven. Staat het nog open in Excel? "
                 "Sluit het bestand en voer het programma opnieuw uit.")
                 
