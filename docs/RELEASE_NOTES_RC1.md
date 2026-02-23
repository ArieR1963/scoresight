# ScoreSight Release Candidate Notes (RC1)

Status: Draft (intern review)
Target release: TBD
Branch: `release/next-rc1`
Prepared by: ArieR1963 + contributors
Date: 2026-02-23

## 1. Scope van deze RC

Deze release candidate bundelt recente verbeteringen in OCR workflow, UI/stabiliteit en output-integraties, plus een update van de Tesseract runtime.

Doel van RC1:
- Technisch valideren op Windows, macOS (Intel + Apple Silicon) en Linux
- Functionele regressies vroeg detecteren
- OCR kwaliteit meten op echte scoreboard-cases

## 2. Belangrijkste wijzigingen

Vul deze sectie aan/controleer op relevantie:

- OCR workflow en veldkoppeling verbeterd
- Verbeteringen in vMix / vMix API+ outputflow
- UI/vertaling updates in meerdere talen
- OCR Training Dojo workflow-updates
- Tesseract runtime update: `5.5.1 -> 5.5.2`

## 3. Technische update: Tesseract

- Python bridge: `tesserocr 2.10.0`
- Gekoppelde Tesseract runtime: `5.5.2`
- Lokale smoke-validatie uitgevoerd:
  - App startup smoke test: geslaagd
  - OCR basisherkenningstest: geslaagd

Opmerking:
- Geen volledige hertraining vereist voor bestaande `.traineddata` bij deze patch-update binnen Tesseract 5.x.

## 4. Teststatus (in te vullen)

### 4.1 Platforms

- Windows: nog te valideren
- macOS Intel: nog te valideren
- macOS Apple Silicon (M1-M4): nog te valideren
- Linux: nog te valideren

### 4.2 Functionele checks

- Bronselectie / capture: nog te valideren
- OCR detectie op live scoreboard: nog te valideren
- Output naar vMix / API / CSV / JSON / XML: nog te valideren
- Performance bij langdurig draaien: nog te valideren

## 5. Bekende risico's / aandachtspunten

- Oude geannoteerde trainingsdataset is niet beschikbaar
- Nieuwe modelverbeteringen vereisen (her)annotatie op basis van beschikbare video's
- Cross-platform packaging moet nog volledig gevalideerd worden

## 6. Wat testers expliciet moeten beoordelen

- OCR nauwkeurigheid per type scoreboard
- Stabiliteit bij lange sessies
- UI regressies en vertaalfouten
- Output consistentie (vMix/API) zonder vertraging of gemiste updates

## 7. Feedbackvragen voor RC1

1. Welke use-cases werken aantoonbaar beter dan vorige release?
2. Welke regressies blokkeren een publieke release?
3. Welke platformen zijn productie-klaar?
4. Welke verbeteringen schuiven door naar RC2?

## 8. Release-go/no-go checklist

- [ ] Kernflows getest op alle target platforms
- [ ] Geen blocker bugs open
- [ ] Release notes inhoud definitief
- [ ] Build artifacts beschikbaar voor alle platforms
- [ ] PR klaar met duidelijke testevidence en changelog
