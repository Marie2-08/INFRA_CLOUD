"""Opdracht 7: de gegevens valideren tegen formaatregels en tegen de werkelijke configuratie."""
import csv
import ipaddress
import platform
import re
import socket
import subprocess

from .collect import clean_serial

GIB = 1024 ** 3
SCHEIDINGSTEKEN = ";"
MAC_PATROON = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------
def naar_getal(tekst):
    try:
        return float(str(tekst).strip().replace(",", "."))
    except ValueError:
        return None


def normaliseer_mac(tekst):
    """04-68-74-EC-66-79 / 04:68:... -> 04:68:74:ec:66:79"""
    cijfers = re.sub(r"[^0-9a-f]", "", (tekst or "").lower())
    return ":".join(cijfers[i:i + 2] for i in range(0, 12, 2)) if len(cijfers) == 12 else ""


def normaliseer_tekst(tekst):
    return " ".join((tekst or "").split()).lower()


# ---------------------------------------------------------------------------
# Deel A: automatische controles op de hele dataset (alle computers)
# ---------------------------------------------------------------------------
def valideer_rij(rij):
    """Geef (fouten, info) terug voor één computer."""
    fouten, info = [], []

    if not rij["computernaam"].strip():
        fouten.append("computernaam ontbreekt")
    if not rij["processor"].strip():
        fouten.append("processor ontbreekt")

    serie = rij["serienummer"].strip()
    if not serie:
        info.append("serienummer ontbreekt of is niet uitleesbaar "
                    "(normaal bij virtuele machines, zonder beheerdersrechten of in een bestand van voor opdracht 8)")
    elif clean_serial(serie) is None:
        fouten.append(f"serienummer is een placeholder van de fabrikant: {serie!r}")

    ram = naar_getal(rij["totaal_ram_gib"])
    if ram is None or not 1 <= ram <= 4096:
        fouten.append(f"RAM onwaarschijnlijk of ontbreekt: {rij['totaal_ram_gib']!r}")

    opslag = naar_getal(rij["opslagcapaciteit_gib"])
    if opslag is None or not 8 <= opslag <= 200_000:
        fouten.append(f"opslagcapaciteit onwaarschijnlijk of ontbreekt: {rij['opslagcapaciteit_gib']!r}")

    mac = rij["mac_adres"]
    if not MAC_PATROON.match(mac) or set(mac) <= {"0", ":"}:
        fouten.append(f"MAC-adres ongeldig of ontbreekt: {mac!r}")

    try:
        ip = ipaddress.IPv4Address(rij["ipv4_adres"])
        if ip.is_loopback or ip.is_unspecified or ip.is_link_local:
            fouten.append(f"IPv4-adres is niet bruikbaar (loopback of 169.254.x.x): {ip}")
    except ValueError:
        fouten.append(f"IPv4-adres ongeldig of ontbreekt: {rij['ipv4_adres']!r}")

    if rij["ipv6_adres"]:
        try:
            if not ipaddress.IPv6Address(rij["ipv6_adres"]).is_global:
                fouten.append(f"IPv6-adres is niet globaal: {rij['ipv6_adres']}")
        except ValueError:
            fouten.append(f"IPv6-adres ongeldig: {rij['ipv6_adres']!r}")
    else:
        info.append("geen globaal IPv6-adres (normaal op netwerken zonder IPv6)")

    if rij["ipv6_link_local_adres"]:
        try:
            if not ipaddress.IPv6Address(rij["ipv6_link_local_adres"]).is_link_local:
                fouten.append(f"IPv6 link-local-adres is geen fe80::-adres: {rij['ipv6_link_local_adres']}")
        except ValueError:
            fouten.append(f"IPv6 link-local-adres ongeldig: {rij['ipv6_link_local_adres']!r}")
    else:
        info.append("geen IPv6 link-local-adres")

    return fouten, info


def zoek_dubbels(rijen, kolom):
    """Waarden die in meerdere rijen voorkomen (computernaam en MAC-adres moeten uniek zijn)."""
    gezien, dubbel = set(), set()
    for rij in rijen:
        waarde = rij[kolom].strip().lower()
        if waarde and waarde in gezien:
            dubbel.add(waarde)
        gezien.add(waarde)
    return sorted(dubbel)


def valideer_dataset(rijen):
    """Druk de resultaten van deel A af; geef het aantal gevonden fouten terug."""
    totaal = 0
    for rij in rijen:
        fouten, info = valideer_rij(rij)
        totaal += len(fouten)
        status = "OK" if not fouten else f"{len(fouten)} probleem(en)"
        print(f"- {rij['computernaam']}: {status}")
        for f_ in fouten:
            print(f"    FOUT: {f_}")
        for i_ in info:
            print(f"    info: {i_}")
    for kolom in ("computernaam", "mac_adres", "serienummer"):
        dubbels = zoek_dubbels(rijen, kolom)
        totaal += len(dubbels)
        print(f"Dubbele {kolom}: {', '.join(dubbels) if dubbels else 'geen'}")
    return totaal


# ---------------------------------------------------------------------------
# Deel B: eigen computer vergelijken met de werkelijke configuratie (Windows)
# ---------------------------------------------------------------------------
def powershell(script):
    """Voer een PowerShell-opdracht uit en geef de uitvoer terug (None bij een fout)."""
    for exe in ("powershell", "pwsh"):
        try:
            klaar = subprocess.run(
                [exe, "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        uitvoer = klaar.stdout.strip()
        if klaar.returncode == 0 and uitvoer:
            return uitvoer
    return None


def eerste_regel(tekst):
    return tekst.splitlines()[0].strip() if tekst else None


def als_getal(tekst):
    try:
        return float(eerste_regel(tekst))
    except (TypeError, ValueError):
        return None


def werkelijke_waarden():
    """Haal de waarden op uit het besturingssysteem (andere bron dan psutil)."""
    verbinding = (
        "$c = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } "
        "| Select-Object -First 1; "
    )
    return {
        "computernaam": eerste_regel(powershell("$env:COMPUTERNAME")),
        "ram_bytes": als_getal(powershell("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")),
        "ram_geinstalleerd_bytes": als_getal(powershell(
            "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum")),
        "processor": eerste_regel(powershell(
            "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")),
        # andere WMI-klasse dan in collect.py (Win32_BIOS), zodat het een onafhankelijke controle is
        "serienummer": eerste_regel(powershell(
            "(Get-CimInstance Win32_ComputerSystemProduct).IdentifyingNumber")),
        "ipv4": eerste_regel(powershell(verbinding + "$c.IPv4Address.IPAddress")),
        "mac": eerste_regel(powershell(
            verbinding + "(Get-NetAdapter -InterfaceIndex $c.InterfaceIndex).MacAddress")),
        "schijf_bytes": als_getal(powershell(
            "(Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -eq $env:SystemDrive }).Size")),
        "fysieke_schijf_bytes": als_getal(powershell(
            "(Get-PhysicalDisk | Measure-Object -Property Size -Sum).Sum")),
    }


def vergelijk(rij, w):
    """Vergelijk de CSV-rij met de werkelijke waarden; geef rapportregels terug."""
    rapport = []

    def toevoegen(controle, csv_waarde, werkelijk, ok, opmerking=""):
        if werkelijk in (None, ""):
            resultaat = "NIET OPGEHAALD"
        else:
            resultaat = "OK" if ok else "VERSCHIL"
        rapport.append({
            "controle": controle, "csv_waarde": csv_waarde,
            "werkelijke_waarde": "" if werkelijk is None else werkelijk,
            "resultaat": resultaat, "opmerking": opmerking,
        })

    toevoegen("computernaam", rij["computernaam"], w["computernaam"],
              rij["computernaam"].lower() == (w["computernaam"] or "").lower())

    ram_csv = naar_getal(rij["totaal_ram_gib"])
    ram_werk = w["ram_bytes"] / GIB if w["ram_bytes"] else None
    opm = ""
    if w["ram_geinstalleerd_bytes"]:
        opm = (f"geinstalleerd: {w['ram_geinstalleerd_bytes'] / GIB:.2f} GiB; beschikbaar is "
               "minder door hardwarereservering (o.a. geintegreerde grafische kaart)")
    toevoegen("RAM (GiB)", rij["totaal_ram_gib"],
              f"{ram_werk:.2f}".replace(".", ",") if ram_werk else None,
              ram_werk is not None and ram_csv is not None and abs(ram_csv - ram_werk) <= 0.1, opm)

    serie_werk = clean_serial(w["serienummer"])
    serie_ok = rij["serienummer"].strip().upper() == (serie_werk or "").upper()
    toevoegen("serienummer", rij["serienummer"], serie_werk, serie_ok,
              "" if serie_ok else ("kolom is leeg: het CSV-bestand is van voor opdracht 8, voer main.py opnieuw uit"
                                   if not rij["serienummer"].strip() else "serienummer komt niet overeen"))

    toevoegen("processor", rij["processor"], w["processor"],
              normaliseer_tekst(rij["processor"]) == normaliseer_tekst(w["processor"]))

    ip_ok = rij["ipv4_adres"] == w["ipv4"]
    toevoegen("IPv4-adres", rij["ipv4_adres"], w["ipv4"], ip_ok,
              "" if ip_ok else "dynamisch (DHCP): verandert bij een ander netwerk of na herstart")

    mac_ok = normaliseer_mac(rij["mac_adres"]) == normaliseer_mac(w["mac"])
    toevoegen("MAC-adres", rij["mac_adres"], normaliseer_mac(w["mac"]), mac_ok,
              "" if mac_ok else "andere adapter, of 'willekeurige hardwareadressen' staat aan")

    opslag_csv = naar_getal(rij["opslagcapaciteit_gib"])
    opslag_werk = w["schijf_bytes"] / GIB if w["schijf_bytes"] else None
    opm = ""
    if w["fysieke_schijf_bytes"]:
        opm = (f"fysieke schijf(ven): {w['fysieke_schijf_bytes'] / 1e9:.0f} GB "
               f"= {w['fysieke_schijf_bytes'] / GIB:.1f} GiB; systeempartitie is kleiner door "
               "herstel-/opstartpartities")
    toevoegen("opslagcapaciteit (GiB)", rij["opslagcapaciteit_gib"],
              f"{opslag_werk:.2f}".replace(".", ",") if opslag_werk else None,
              opslag_werk is not None and opslag_csv is not None and abs(opslag_csv - opslag_werk) <= 1, opm)
    return rapport


def valideer_eigen_computer(rijen):
    """Vergelijk de rij van deze computer met de werkelijke configuratie (alleen Windows)."""
    if platform.system() != "Windows":
        print("Deel B is voor Windows geschreven; vergelijk op dit systeem manueel.")
        return []
    eigen = socket.gethostname()
    rij = next((r for r in rijen if r["computernaam"].lower() == eigen.lower()), None)
    if rij is None:
        namen = ", ".join(r["computernaam"] for r in rijen)
        print(f"Deze computer ('{eigen}') staat niet in de dataset. Aanwezig: {namen}")
        return []
    rapport = vergelijk(rij, werkelijke_waarden())
    for r in rapport:
        print(f"  {r['controle']:24} CSV: {r['csv_waarde']:32} werkelijk: {str(r['werkelijke_waarde']):32} {r['resultaat']}")
        if r["opmerking"]:
            print(f"      -> {r['opmerking']}")
    return rapport


def schrijf_rapport(rapport, bestand):
    with open(bestand, "w", newline="", encoding="utf-8-sig") as f:
        schrijver = csv.DictWriter(
            f, fieldnames=["controle", "csv_waarde", "werkelijke_waarde", "resultaat", "opmerking"],
            delimiter=SCHEIDINGSTEKEN,
        )
        schrijver.writeheader()
        schrijver.writerows(rapport)
