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

