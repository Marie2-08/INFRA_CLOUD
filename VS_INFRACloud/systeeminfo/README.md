# Systeeminfo

Verzamelt de systeeminformatie van je computer, slaat die op als JSON, CSV en Excel,
voegt de bestanden van alle groepsleden samen en valideert het resultaat.

## Installeren

```
python -m venv .venv
.venv\Scripts\activate          (Windows PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

## Uitvoeren

```
python main.py             # alles in één keer en opent de Excel-bestanden
python main.py --no-open   # zonder de bestanden te openen
```

Sluit eerst de Excel-bestanden als ze nog open staan, anders kan Python ze niet overschrijven.

## Wat gebeurt er?

| Stap | Opdracht | Module |
|---|---|---|
| Systeeminformatie verzamelen en filteren | 1 en 2 | `sysinfo/collect.py` |
| Opslaan als JSON, CSV en XLSX en teruglezen | 3, 4 en 5 | `sysinfo/exporters.py` |
| CSV-bestanden van de groep samenvoegen | 6 | `sysinfo/merge.py` |
| Gegevens valideren | 7 | `sysinfo/validate.py` |
| Alles samen uitvoeren | | `main.py` |

Opdracht 8 (serienummer) is in alle modules verwerkt: het serienummer wordt verzameld, opgeslagen
(JSON, CSV, XLSX), samengevoegd en gevalideerd. Elk groepslid moet `main.py` opnieuw uitvoeren en het
nieuwe CSV-bestand delen, anders blijft de kolom `serienummer` leeg.

## Mappen

- `output/`: bestanden van je eigen computer (worden niet in Git bewaard).
- `groepsdata/`: de CSV-bestanden van alle groepsleden en het samengevoegde resultaat.

## Afspraken voor de groep

- Elk groepslid draait `main.py` op zijn eigen computer.
- Bestandsnaam: `systeeminfo_<computernaam>.csv`, in de map `groepsdata/`.
- Scheidingsteken `;`, decimaalteken `,`, codering UTF-8.
- Een nieuwe computer toevoegen: zet het CSV-bestand in `groepsdata/` en voer `main.py` opnieuw uit.

## Let op bij GitHub

De bestanden bevatten MAC- en IP-adressen en serienummers. Maak de repository daarom **privé**.
