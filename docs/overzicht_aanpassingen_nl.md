# Overzicht Aanpassingen (NL)

Dit bestand bundelt het werkoverzicht van recente sessies, inclusief de updates van vandaag.

## 2026-02-15 / 2026-02-16

- `Apply Time Baseline` hernoemd en UI-volgorde aangepast rond Auto-Tune.
- Velden toevoegen aangepast naar crosshair-flow (eerst positioneren/trekken, dan fine-tune).
- Gedrag bij source wissel opgeschoond: lege start, handmatig velden toevoegen, toolvolgorde verbeterd.
- OCR Training Dojo folder-open probleem opgelost.
- Config export/import uitgebreid met four-corner data.
- Video testbediening toegevoegd voor videobronnen:
  - play/pause
  - rewind
  - forward
  - jump to start
- Shotclock presets toegevoegd en verfijnd:
  - Basketball / Waterpolo (24)
  - NCAA Basketball (30)
  - Korfball (25)
  - Roller Hockey (45)
  - Custom
- Shotclock-formaten en UI-plaatsing verbeterd (inclusief editbaarheid waar nodig).
- Sliders uitgebreid zodat waarde ook direct als getal ingevoerd kan worden.
- Stabiliteit verbeterd rond four-corner mode en bronwissels.

## 2026-02-16 (vMix API+ uitbreiding)

- Bestaande `vMix` optie behouden (legacy flow).
- Nieuwe aparte output-tab toegevoegd: `vMix API+` (naast `vMix`).
- `vMix API+` connectie werkt met host + API-poort (`/api`).
- Connectie-indicator toegevoegd (`Connected` / `Disconnected`).
- `Fetch Fields` leest alle `<text name="...">` velden uit vMix API.
- Popup toegevoegd met alle gevonden veldnamen voor mapping.
- OCR updatepad aangepast zodat legacy `vMix` en `vMix API+` beide ondersteund zijn.
- `vMix API+` vereenvoudigd:
  - geen aparte startknop
  - automatische connect-check bij host/poort wijziging
- Host parsing robuust gemaakt:
  - accepteert zowel `192.168.x.x` als `http://192.168.x.x`
  - voorkomt foutieve dubbele protocol-opbouw
- SetText route gebruikt veld/input-context uit discovered data.

## 2026-02-19 (stabiliteit, output-flow, UI)

- `vMix` en `vMix API+` startgedrag aangescherpt:
  - bij `Start` wordt eerst connectie geverifieerd
  - ongeldige host/poort geeft rode status `Disconnected`
  - geen onterechte groene `Running` status meer bij fout IP/poort
- `vMix API+` blijft na config-import handmatig te starten (niet auto-starten).
- Reconnect-flow verbeterd bij host/poort/input wissel:
  - mapping blijft behouden
  - running-state blijft behouden
  - force-send op start/restart toegevoegd
- Initiele output push verbeterd:
  - bij start van `vMix`/`vMix API+` worden actuele waarden direct verstuurd
  - ook als veldwaarde niet net is gewijzigd
- `vMix API+` latency/stotter opgelost met transportstabilisatie:
  - queue-gedrag verbeterd
  - TCP-fallback strategie toegevoegd
  - pacing/cooldown toegevoegd voor stabiele, vloeiende updates
  - debugtelemetrie ingebouwd voor bottleneck-analyse en daarna standaard uitgezet
- Logviewer-probleem opgelost:
  - actieve logbestanden worden niet meer per ongeluk opgeschoond
  - log cleanup nu op mtime i.p.v. bestandsnaam-sorting
- Overlay-visuals voor OCR-kaders verbeterd:
  - betere contrastkleuren voor non-binary (o.a. rode scoreborden)
  - selectie- en default-kleurlogica aangepast (geel/blauw gewisseld op verzoek)
  - char/extra boxes duidelijker zichtbaar gemaakt met aangepaste fill/outline

## 2026-02-20 (vertaalworkflow)

- Exportscript toegevoegd voor vertalingen naar Excel:
  - `scripts/export_translations_xlsx.py`
  - output: `translations/scoresight_translations.xlsx`
  - bevat `Base_EN` + aparte tab per taal
- Importscript toegevoegd van Excel terug naar `.ts`:
  - `scripts/import_translations_xlsx.py`
  - standaard `dry-run`, met `--apply` om wijzigingen te schrijven
  - match op `Context::Source` key
- Workflow gemaakt om vertalingen buiten Qt Linguist in één centraal spreadsheet te beheren.

## 2026-02-20 (overlay finetuning)

- Overlay-transparantie in meerdere stappen verhoogd voor beter contrast met behoud van doorkijk.
- Kleurvolgorde aangepast:
  - niet geselecteerd = geel
  - geselecteerd = blauw/cyaan
- OCR cijferkaders visueel herwerkt naar diep paarse stijl met duidelijkere fill/outline op non-binary beeld.
- Resultaattekst (onderin kader) voorzien van witte outline voor betere leesbaarheid op lichte/rode backgrounds.
