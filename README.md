# EnergyHub - Home Assistant Integration

Verbinde deine Energiegemeinschaft mit Home Assistant. Diese Integration sendet automatisch alle Energiedaten (Leistung, Verbrauch, Spannung, Strom) an deine EnergyHub-Plattform.

## Installation via HACS

1. Oeffne HACS in Home Assistant
2. Klicke auf die drei Punkte oben rechts → **Benutzerdefinierte Repositories**
3. Fuege die URL dieses Repositories hinzu: `https://github.com/DEIN-USER/energyhub-ha`
4. Kategorie: **Integration**
5. Klicke **Hinzufuegen** und dann **Installieren**
6. Starte Home Assistant neu

## Einrichtung

1. Gehe zu **Einstellungen → Geraete & Dienste → Integration hinzufuegen**
2. Suche nach **EnergyHub**
3. Gib den **Kopplungscode** ein (aus deiner EnergyHub-App unter Geraete → Geraet verbinden → Home Assistant)
4. Fertig!

## Was passiert?

Die Integration sendet automatisch alle 30 Sekunden folgende Daten an EnergyHub:
- Leistung (W, kW)
- Energie (Wh, kWh)
- Spannung (V)
- Strom (A)
- Schalter-Status

Alle Sensoren und Schalter die von Shelly, Solar-Wechselrichtern oder anderen Energie-Geraeten stammen werden automatisch erkannt.

## Voraussetzungen

- Home Assistant 2024.1.0 oder neuer
- Ein aktives EnergyHub-Konto mit einer Energiegemeinschaft
